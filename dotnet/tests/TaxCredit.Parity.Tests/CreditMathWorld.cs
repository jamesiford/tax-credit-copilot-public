using TaxCredit.Domain.Calculation;
using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Programs;
using TaxCredit.Infrastructure.Rules;

namespace TaxCredit.Parity.Tests;

/// <summary>
/// The rules folders of the credit-math golden, rebuilt in memory: the SAME <c>backend/rules</c> files read through the Infrastructure adapter, plus the
/// overlay the exporter recorded in the golden's meta line (a file mapped to <c>null</c> is deleted). No rule file is copied.
/// </summary>
internal sealed class OverlayRulePackSource : IRulePackSource
{
    private readonly JsonRulePackSource _real;
    private readonly Dictionary<string, string?> _files = new(StringComparer.Ordinal);
    private readonly string _registryRelative;
    private long? _stamp;

    public OverlayRulePackSource(PyDict spec)
    {
        _real = new JsonRulePackSource(new RulePackOptions { RulesDirectory = CreditMathHarness.RulesDirectory });
        foreach (var kv in (PyDict)spec["files"]!)
        {
            _files[kv.Key] = (string?)kv.Value;
        }

        _registryRelative = (string?)spec["registry_file"] ?? "registry/programs.json";
        HasCustomRegistry = spec["registry_file"] is not null;
    }

    public bool HasCustomRegistry { get; }

    public string RulesDirectory => _real.RulesDirectory;

    public string RegistryFile => Path.Combine(_real.RulesDirectory, _registryRelative.Replace('/', Path.DirectorySeparatorChar));

    public void Set(string relativePath, string? text) => _files[relativePath] = text;

    public void SetStamp(long stamp) => _stamp = stamp;

    public bool Exists(string relativePath) => IsFile(relativePath) || IsDirectory(relativePath);

    public bool IsFile(string relativePath) => _files.TryGetValue(relativePath, out var text) ? text is not null : _real.IsFile(relativePath);

    public bool IsDirectory(string relativePath)
    {
        var prefix = relativePath.Length == 0 ? string.Empty : relativePath + "/";
        return relativePath.Length == 0 || _files.Any(kv => kv.Value is not null && kv.Key.StartsWith(prefix, StringComparison.Ordinal)) || _real.IsDirectory(relativePath);
    }

    public string ReadText(string relativePath) =>
        _files.TryGetValue(relativePath, out var text)
            ? text ?? throw new PyFileNotFoundError("deleted in the overlay: " + relativePath)
            : _real.ReadText(relativePath);

    public IReadOnlyList<string> ListJsonStems(string relativeFolder)
    {
        var prefix = relativeFolder.Length == 0 ? string.Empty : relativeFolder + "/";
        var stems = new List<string>();
        foreach (var stem in _real.ListJsonStems(relativeFolder))
        {
            if (!_files.TryGetValue(prefix + stem + ".json", out var text) || text is not null)
            {
                stems.Add(stem);
            }
        }

        foreach (var kv in _files.Where(kv => kv.Value is not null && kv.Key.StartsWith(prefix, StringComparison.Ordinal)))
        {
            var rest = kv.Key[prefix.Length..];
            if (!rest.Contains('/', StringComparison.Ordinal) && rest.EndsWith(".json", StringComparison.OrdinalIgnoreCase))
            {
                stems.Add(Path.GetFileNameWithoutExtension(rest));
            }
        }

        return stems.Distinct(StringComparer.Ordinal).ToList();
    }

    public long? RegistryStamp() =>
        _files.TryGetValue(_registryRelative, out var text) ? (text is null ? null : _stamp ?? 1) : (_real.IsFile(_registryRelative) ? _stamp ?? 1 : null);

    public string ReadRegistryText() => ReadText(_registryRelative);
}

/// <summary>The ingestion hook the golden replaced: records every call, then answers nothing, raises, or returns a recorded value.</summary>
internal sealed class RecordingIngestion(IIngestedOneZeroSource real) : IIngestedOneZeroSource
{
    public string Mode { get; set; } = "real";

    public PyDict? Value { get; set; }

    public List<object?> Calls { get; } = [];

    public PyDict? IngestedOneZero(string programOrState, long? taxYear)
    {
        if (Mode == "real")
        {
            return real.IngestedOneZero(programOrState, taxYear);
        }

        Calls.Add(new List<object?> { programOrState, taxYear });
        return Mode == "raises" ? throw new InvalidOperationException("ingestion is down") : Value;
    }
}

/// <summary>The wage lookups the golden recorded (Python read <c>data/payroll.csv</c>, which is not ported): serves the recorded value for a key and records the call.</summary>
internal sealed class RecordedWages : IProgramWageSource
{
    public Dictionary<string, double> Values { get; } = new(StringComparer.Ordinal);

    public List<object?> Calls { get; } = [];

    public double AverageProgramWage(string programOrState)
    {
        var value = Values.TryGetValue(programOrState, out var v) ? v : throw new PyUnsupportedException("no recorded wage for " + programOrState);
        Calls.Add(new List<object?> { programOrState, value });
        return value;
    }
}

/// <summary>An exception carrying Python's type name and a path-normalised message, so the shared replay compares it like any recorded exception.</summary>
internal sealed class NormalisedException(string pythonType, string message) : PyException(pythonType, message);
