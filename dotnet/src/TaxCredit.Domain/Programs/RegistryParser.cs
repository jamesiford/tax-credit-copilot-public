using TaxCredit.Domain.Calculation;
using TaxCredit.Domain.Numerics;

namespace TaxCredit.Domain.Programs;

/// <summary>
/// Parses and checks the manifest text (Python <c>tools/program_registry.parse_registry</c> and its <c>_parse_*</c> helpers). Every refusal is
/// a <see cref="RegistryError"/> naming the file, the entry and the field.
/// </summary>
public static class RegistryParser
{
    /// <summary>The manifest schema version this reader understands (Python <c>SCHEMA_VERSION</c>).</summary>
    public const long SchemaVersion = 1;

    /// <summary>Parses and checks manifest text.</summary>
    /// <param name="text">The manifest text.</param>
    /// <param name="sourceName">The manifest's file name as it appears in messages (Python <c>source.name</c>).</param>
    /// <param name="source">The rules folder, asked whether each entry's pack file exists.</param>
    /// <returns>The registry.</returns>
    /// <exception cref="RegistryError">When the manifest or an entry cannot be used.</exception>
    public static ProgramRegistry Parse(string text, string sourceName, IRulePackSource source)
    {
        ArgumentNullException.ThrowIfNull(text);
        ArgumentNullException.ThrowIfNull(sourceName);
        ArgumentNullException.ThrowIfNull(source);
        object? data;
        try
        {
            data = PyJson.Loads(text);
        }
        catch (Exception e) when (e is PyJsonDecodeError or PyValueError)
        {
            // Python catches ValueError (JSONDecodeError is one) and quotes str(exc): tools/program_registry.py parse_registry.
            throw Fail(sourceName, "file", $"not valid JSON ({e.Message})");
        }

        if (data is not PyDict top || !PyEquality.Equal(RuleTree.Get(top, "schema_version"), SchemaVersion))
        {
            throw Fail(sourceName, "file", $"schema_version must be {SchemaVersion}");
        }

        if (RuleTree.Get(top, "programs") is not List<object?> programs)
        {
            throw Fail(sourceName, "file", "programs must be a list");
        }

        var entries = new List<ProgramEntry>();
        for (var i = 0; i < programs.Count; i++)
        {
            entries.Add(ParseEntry(programs[i], i, sourceName, source));
        }

        var seen = new HashSet<string>(StringComparer.Ordinal);
        foreach (var entry in entries)
        {
            if (!seen.Add(entry.Code))
            {
                throw Fail(sourceName, $"program {entry.Code}", "code is listed twice");
            }
        }

        return new ProgramRegistry(entries, source.RulesDirectory, sourceName);
    }

    private static RegistryError Fail(string source, string where, string message) => new($"{source}: {where}: {message}");

    private static EngineProfile ParseProfile(object? raw, string source, string where)
    {
        if (raw is null)
        {
            return new EngineProfile();
        }

        if (raw is not PyDict profile)
        {
            throw Fail(source, where, "engine_profile must be an object");
        }

        var defaults = new EngineProfile();
        var result = new EngineProfile
        {
            CreditModel = RuleTree.Str(RuleTree.Get(profile, "credit_model", defaults.CreditModel)),
            HeadcountModel = RuleTree.Str(RuleTree.Get(profile, "headcount_model", defaults.HeadcountModel)),
        };
        if (!ProgramVocabulary.SupportedCreditModels.Contains(result.CreditModel))
        {
            throw Fail(source, where, $"credit_model {PyStr.Repr(result.CreditModel)} is not supported "
                + $"(supported: {string.Join(", ", ProgramVocabulary.SupportedCreditModels)}); a new model needs engine work");
        }

        if (!ProgramVocabulary.SupportedHeadcountModels.Contains(result.HeadcountModel))
        {
            throw Fail(source, where, $"headcount_model {PyStr.Repr(result.HeadcountModel)} is not supported "
                + $"(supported: {string.Join(", ", ProgramVocabulary.SupportedHeadcountModels)}); a new model needs engine work");
        }

        return result;
    }

    private static (string Level, string JurisdictionCode, string? State) ParseJurisdiction(PyDict raw, string source, string where)
    {
        var jurisdiction = raw["jurisdiction"];
        var level = jurisdiction is PyDict jd ? RuleTree.Get(jd, "level") : null;
        if (level is not string levelText || !ProgramVocabulary.JurisdictionLevels.Contains(levelText))
        {
            throw Fail(source, where, $"jurisdiction.level must be one of {string.Join(", ", ProgramVocabulary.JurisdictionLevels)}");
        }

        var jurisdictionDict = (PyDict)jurisdiction!;
        if (!RuleTree.Truthy(RuleTree.Get(jurisdictionDict, "code")))
        {
            throw Fail(source, where, "jurisdiction.code is missing");
        }

        var state = RuleTree.Get(raw, "state");
        if (levelText == "state" && !RuleTree.Truthy(state))
        {
            throw Fail(source, where, "a state-level program needs a state");
        }

        if (levelText == "federal" && RuleTree.Truthy(state))
        {
            throw Fail(source, where, "a federal program has no state key");
        }

        return (levelText, RuleTree.Str(jurisdictionDict["code"]), RuleTree.Truthy(state) ? PyStr.Upper(RuleTree.Str(state)) : null);
    }

    private static string ParseLifecycle(PyDict raw, string source, string where)
    {
        var lifecycle = RuleTree.Str(RuleTree.Get(raw, "lifecycle", "described"));
        if (lifecycle == "calculable")
        {
            throw Fail(source, where, "lifecycle 'calculable' cannot be typed: it is derived from authored year packs");
        }

        return ProgramVocabulary.StoredLifecycles.Contains(lifecycle)
            ? lifecycle
            : throw Fail(source, where, $"lifecycle must be one of {string.Join(", ", ProgramVocabulary.StoredLifecycles)}");
    }

    private static ProgramEntry ParseEntry(object? raw, int index, string source, IRulePackSource rules)
    {
        var where = $"programs[{index}]";
        if (raw is not PyDict entry)
        {
            throw Fail(source, where, "an entry must be an object");
        }

        foreach (var key in new[] { "code", "name", "jurisdiction", "pack_file" })
        {
            if (!RuleTree.Truthy(RuleTree.Get(entry, key)))
            {
                throw Fail(source, where, $"missing {key}");
            }
        }

        var code = RuleTree.Str(entry["code"]);
        where = $"program {code}";
        var (level, jurisdictionCode, state) = ParseJurisdiction(entry, source, where);
        var lifecycle = ParseLifecycle(entry, source, where);
        var packFile = RuleTree.Str(entry["pack_file"]);
        if (lifecycle != "draft" && !rules.IsFile(packFile))
        {
            throw Fail(source, where, $"pack_file {packFile} not found in {rules.RulesDirectory}");
        }

        return new ProgramEntry
        {
            Code = code,
            Name = RuleTree.Str(entry["name"]),
            Level = level,
            JurisdictionCode = jurisdictionCode,
            PackFile = packFile,
            State = state,
            Lifecycle = lifecycle,
            EngineProfile = ParseProfile(RuleTree.Get(entry, "engine_profile"), source, where),
            Notes = RuleTree.Str(RuleTree.Get(entry, "notes", string.Empty)),
        };
    }
}
