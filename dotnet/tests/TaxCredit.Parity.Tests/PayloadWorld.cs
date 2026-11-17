using System.IO.Compression;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using TaxCredit.Domain.Calculation;
using TaxCredit.Domain.Claims;
using TaxCredit.Domain.Designations;
using TaxCredit.Domain.Gold;
using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Pipeline;
using TaxCredit.Domain.Programs;
using TaxCredit.Infrastructure.Payroll;
using TaxCredit.Infrastructure.Rules;

namespace TaxCredit.Parity.Tests;

/// <summary>The golden files of stage CAP: <c>gold_payload.jsonl.gz</c> (meta, helper calls, runs) and <c>gold_payload_input.jsonl.gz</c> (the synthetic clients' payroll).</summary>
internal static class PayloadGolden
{
    public const string Main = "gold_payload.jsonl.gz";
    public const string Input = "gold_payload_input.jsonl.gz";

    /// <summary>Streams the lines of a golden whose kind (<c>"k"</c>) is <paramref name="kind"/>, without parsing the others.</summary>
    public static IEnumerable<string> Lines(string file, string kind)
    {
        GoldenFiles.AssertOracleStamp(file);
        var prefix = "{\"k\":\"" + kind + "\"";
        using var stream = File.OpenRead(Path.Combine(GoldenFiles.ParityDirectory, "goldens", file));
        using var gz = new GZipStream(stream, CompressionMode.Decompress);
        using var reader = new StreamReader(gz, Encoding.ASCII);
        string? line;
        while ((line = reader.ReadLine()) is not null)
        {
            if (line.StartsWith(prefix, StringComparison.Ordinal))
            {
                yield return line;
            }
        }
    }

    public static PyDict Meta() => (PyDict)PyJson.Loads(Lines(Main, "meta").Single())!;
}

/// <summary>Everything a replay needs that Python got from its surroundings: the real rules, the designation registry, the assumption files and the payroll sources.</summary>
internal sealed class PayloadWorld
{
    private static readonly Lazy<PayloadWorld> Shared = new(() => new PayloadWorld());
    private readonly Lazy<Dictionary<long, IReadOnlyList<PayRow>>> _synthetic = new(ReadSynthetic);

    private PayloadWorld()
    {
        var root = Directory.GetParent(GoldenFiles.ParityDirectory)!.FullName;
        Meta = PayloadGolden.Meta();
        Library = new RuleLibrary(
            new JsonRulePackSource(new RulePackOptions { RulesDirectory = CreditMathHarness.RulesDirectory }),
            new CapturedIngestion(new JsonIngestedConfigFiles(CreditMathHarness.IngestedDirectory)));
        Csv = new CsvPayrollSource(Path.Combine(root, "backend", "data", "payroll_pay_periods.csv"), 1001);
        Assumptions = AssumptionFiles.Read(Path.Combine(CreditMathHarness.RulesDirectory, "methodology"));
        Designations = Registry((PyDict)Meta["designations"]!);
    }

    public static PayloadWorld Instance => Shared.Value;

    public PyDict Meta { get; }

    public RuleLibrary Library { get; }

    public CsvPayrollSource Csv { get; }

    public IReadOnlyList<AssumptionIdentity> Assumptions { get; }

    public DesignationRegistry Designations { get; }

    public IReadOnlyDictionary<long, IReadOnlyList<PayRow>> Synthetic => _synthetic.Value;

    /// <summary>The payroll of a run's source: the committed CSV, or one synthetic client served as the lakehouse serves it.</summary>
    public IPayrollSource SourceOf(JsonElement source) => source.GetProperty("kind").GetString() == "csv"
        ? Csv
        : new InMemoryPayrollSource(new Dictionary<long, IReadOnlyList<PayRow>> { [source.GetProperty("client").GetInt64()] = Synthetic[source.GetProperty("client").GetInt64()] });

    public ProgramDefaults DefaultsOver(IPayrollSource source) => new(Library, id => PayrollRows.StatesPresent(source.LoadPayPeriods(id)));

    /// <summary>The pipeline over one source, with the golden's frozen clock and ids.</summary>
    public (ClientCalculation Pipeline, CapturingWriter Writer, CapturingClaims Claims, ProgramDefaults Defaults) Pipeline(
        string runName, IPayrollSource source, IReadOnlyDictionary<(long Client, string Program), IReadOnlyDictionary<string, long>> baseYears, IEnumerable<ProgramClaim> seed)
    {
        var freezes = (PyDict)Meta["freezes"]!;
        var today = PyDate.FromIsoFormat((string)freezes["open_year_today"]!);
        var reads = 0;
        var start = PyDateTime.FromIsoFormat(((string)freezes["utc_now"]!).Split(' ')[0]);
        PyDateTime Clock() => start with { Second = start.Second + reads++ };
        var defaults = DefaultsOver(source);
        var fiscal = new FiscalSource(Library, new NoFiscalRules());
        var writer = new CapturingWriter();
        var claims = new CapturingClaims(seed);
        var assessment = new ClientAssessment(Library, fiscal, () => today, Clock, () => "claim-id");
        var parts = new ClientCalculationParts(
            Library, defaults, new ClientRunResolver(Library, defaults, fiscal, source), new RunFingerprint(Library, fiscal), Designations, source,
            new SavedBaseYears(baseYears), assessment, claims, writer);
        var runId = Convert.ToHexStringLower(SHA256.HashData(Encoding.UTF8.GetBytes("run:" + runName)))[..32];
        var config = new ClientCalculationConfig((string)freezes["git_commit"]!, Assumptions, (long)Meta["section_9_query_count"]!, () => today, Clock, () => runId);
        return (new ClientCalculation(parts, config), writer, claims, defaults);
    }

    private static DesignationRegistry Registry(PyDict spec)
    {
        var legacy = ((List<object?>)spec["legacy"]!).Cast<List<object?>>()
            .Select(p => new KeyValuePair<string, IReadOnlyList<PyDict>>((string)p[0]!, Rows(p[1]))).ToList();
        var source = ((List<object?>)spec["source"]!).Cast<List<object?>>().Select(p => new SourceDesignation((long)p[0]!, (string)p[1]!, Rows(p[2]))).ToList();
        // DATA_CLASSIFICATION=synthetic is one of the exporter's recorded freezes.
        return new DesignationRegistry(legacy, source, Rows(spec["synthetic_ga_default"]), () => true);
    }

    private static List<PyDict> Rows(object? v) => ((List<object?>)v!).Cast<PyDict>().ToList();

    private static Dictionary<long, IReadOnlyList<PayRow>> ReadSynthetic()
    {
        var output = new Dictionary<long, IReadOnlyList<PayRow>>();
        foreach (var line in PayloadGolden.Lines(PayloadGolden.Input, "rows"))
        {
            var tree = (PyDict)PyJson.Loads(line)!;
            var columns = ((List<object?>)tree["columns"]!).Select(c => (string)c!).ToList();
            output[(long)tree["client"]!] = ((List<object?>)tree["rows"]!)
                .Select(r => PayRow.Of(((List<object?>)r!).Select((v, i) => (Key: columns[i], Value: v)).Aggregate(new PyDict(), (d, kv) => d.Add(kv.Key, kv.Value)))).ToList();
        }

        return output;
    }
}

/// <summary>The writer a run hands its payload to: keeps it and returns the rows-per-table counts.</summary>
internal sealed class CapturingWriter : IGoldWriter
{
    public GoldRunPayload? Payload { get; private set; }

    public IReadOnlyList<KeyValuePair<string, long>> WriteRun(GoldRunPayload payload)
    {
        Payload = payload;
        return payload.Tables.Select(t => new KeyValuePair<string, long>(t.Key, t.Value.Count)).ToList();
    }

    public IReadOnlyList<(string Query, long RowCount)> Validate() => [];
}

/// <summary>The claim repository of a run: records what the assessment writes; seeded claims are what a cell already holds.</summary>
internal sealed class CapturingClaims(IEnumerable<ProgramClaim> seed) : IClaimSink
{
    private readonly List<ProgramClaim> _seed = [.. seed];

    public List<ProgramClaim> Recorded { get; } = [];

    public ProgramClaim? Current(long clientId, string programCode, long taxYear) =>
        _seed.FirstOrDefault(c => c.ClientId == clientId && c.ProgramCode == programCode && c.TaxYear == taxYear);

    public void Record(ProgramClaim claim) => Recorded.Add(claim);
}

/// <summary>The saved base years of a run (Python <c>get_override_repository().base_years</c>).</summary>
internal sealed class SavedBaseYears(IReadOnlyDictionary<(long Client, string Program), IReadOnlyDictionary<string, long>> years) : IBaseYearOverrides
{
    public IReadOnlyDictionary<string, long> BaseYears(long clientId, string programCode) =>
        years.TryGetValue((clientId, programCode), out var saved) ? saved : new Dictionary<string, long>();
}
