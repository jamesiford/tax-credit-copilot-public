using System.IO.Compression;
using TaxCredit.Domain.Calculation;
using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Programs;
using TaxCredit.Infrastructure.Rules;

namespace TaxCredit.Parity.Tests;

/// <summary>
/// Replays one call of <c>credit_math.jsonl.gz</c> against the C# port: it builds the recorded world (the real <c>backend/rules</c> through the
/// Infrastructure adapter plus the recorded overlay), dispatches by function name, and returns the same tree shape the exporter recorded.
/// </summary>
internal sealed class CreditMathHarness
{
    public const string File = "credit_math.jsonl.gz";

    private readonly Dictionary<string, RuleLibrary> _libraries = [];
    private readonly Dictionary<string, OverlayRulePackSource> _sources = [];
    private readonly Dictionary<string, PyDict> _specs;
    private readonly RecordingIngestion _ingestion = new(new CapturedIngestion(new JsonIngestedConfigFiles(IngestedDirectory)));
    private readonly RecordedWages _wages = new();

    public CreditMathHarness() => _specs = Worlds();

    public static string RulesDirectory { get; } = Path.Combine(Directory.GetParent(GoldenFiles.ParityDirectory)!.FullName, "backend", "rules");

    public static string IngestedDirectory { get; } = Path.Combine(Directory.GetParent(GoldenFiles.ParityDirectory)!.FullName, "backend", "data", "rules_ingested");

    /// <summary>The wage lookups the last call made (compared with what the golden recorded).</summary>
    public List<object?> LastWageCalls => _wages.Calls;

    /// <summary>The overlay recorded for each world in the golden's meta line.</summary>
    public static PyDict Meta()
    {
        GoldenFiles.AssertOracleStamp(File);
        using var stream = System.IO.File.OpenRead(Path.Combine(GoldenFiles.ParityDirectory, "goldens", File));
        using var gz = new GZipStream(stream, CompressionMode.Decompress);
        using var reader = new StreamReader(gz);
        return (PyDict)PyJson.Loads(reader.ReadLine()!)!;
    }

    private static Dictionary<string, PyDict> Worlds() =>
        ((PyDict)Meta()["worlds"]!).ToDictionary(kv => kv.Key, kv => (PyDict)kv.Value!, StringComparer.Ordinal);

    public OverlayRulePackSource Source(string world)
    {
        if (!_sources.TryGetValue(world, out var source))
        {
            source = new OverlayRulePackSource(_specs[world]);
            _sources[world] = source;
        }

        return source;
    }

    public RuleLibrary Library(string world)
    {
        if (!_libraries.TryGetValue(world, out var lib))
        {
            lib = new RuleLibrary(Source(world), _ingestion, _wages);
            _libraries[world] = lib;
        }

        return lib;
    }

    /// <summary>Replaces machine paths in a message by the placeholders the exporter used.</summary>
    public string Normalise(string message, string world)
    {
        var source = Source(world);
        if (source.HasCustomRegistry)
        {
            message = message.Replace(source.RegistryFile, "<REGISTRY>", StringComparison.Ordinal);
        }

        return message.Replace(source.RulesDirectory, "<RULES>", StringComparison.Ordinal);
    }

    /// <summary>Runs a call; a Python-type exception comes back with its message normalised, anything else (an unmodelled input) propagates.</summary>
    public object? Invoke(PyDict call)
    {
        var args = (PyDict)call["args"]!;
        var world = (string)args["world"]!;
        _wages.Calls.Clear();
        try
        {
            return Dispatch((string)call["fn"]!, args, world);
        }
        catch (NormalisedException)
        {
            throw;
        }
        catch (PyException e)
        {
            throw new NormalisedException(e.PythonType, Normalise(e.Message, world));
        }
    }

    private object? Dispatch(string fn, PyDict a, string world)
    {
        var lib = Library(world);
        return fn switch
        {
            "parse_registry" => Summary(RegistryParser.Parse((string)a["text"]!, "programs.json", Source(world))),
            "load_registry" => Summary(lib.LoadRegistry()),
            "registry_views" => Views(lib),
            "registry_get" => EntryTree(lib.LoadRegistry().Get(a["code"] as string)),
            "registry_for_state" => List(lib.LoadRegistry().ForState(a["state"] as string).Select(EntryTree)),
            "programs_for_state" => List(lib.ProgramsForState((string)a["state"]!).Select(EntryTree)),
            "program_for_code" => EntryTree(lib.ProgramForCode((string)a["code"]!)),
            "view_lookup" => ViewLookup(lib, (string)a["view"]!, (string)a["key"]!),
            "pack_file_for" => lib.PackFileFor(a["key"] as string),
            "state_of" => lib.StateOf((a["key"] as string) ?? string.Empty),
            "credit_key" => RuleLibrary.CreditKey(a["program_code"] as string, (string)a["state"]!),
            "registry_sequence" => Sequence(a, world),
            _ => PackFunctions.Contains(fn) ? Packs(fn, a, lib) : Credit(fn, a, lib),
        };
    }

    private static readonly HashSet<string> PackFunctions =
    [
        "authored_years", "is_year_scoped", "load_pack_flat", "load_year_pack", "resolve_statutory_floors", "resolve_tax_year_convention",
        "load_pack_one_zero", "ingested_one_zero", "pack_from_document", "build_one_zero_pack", "from_pack_json",
    ];

    private object? Packs(string fn, PyDict a, RuleLibrary lib) => fn switch
    {
        "authored_years" => List(lib.AuthoredYears((string)a["pack_file"]!).Select(y => (object?)y)),
        "is_year_scoped" => lib.IsYearScoped((string)a["pack_file"]!),
        "load_pack_flat" => lib.LoadPack((string)a["pack_file"]!),
        "load_year_pack" => YearPack(lib.LoadYearPack((string)a["pack_file"]!, (long?)a["tax_year"])),
        "resolve_statutory_floors" => FloorsTree(lib.ResolveStatutoryFloors((string)a["program_code"]!, (long?)a["tax_year"])),
        "resolve_tax_year_convention" => lib.ResolveTaxYearConvention((string)a["program_code"]!, (long?)a["tax_year"]),
        "load_pack_one_zero" => OneZero(a, lib),
        "ingested_one_zero" => new CapturedIngestion(new JsonIngestedConfigFiles(IngestedDirectory)).IngestedOneZero((string)a["key"]!, (long?)a["tax_year"]),
        "pack_from_document" => PackTree(OneZeroPackBuilder.FromDocument((PyDict)a["doc"]!, (long?)a["tax_year"])),
        "build_one_zero_pack" => PackTree(OneZeroPackBuilder.Build((PyDict)a["pack"]!, (PyDict)a["resolved"]!, ((List<object?>)a["pay_codes"]!)[0], ((List<object?>)a["pay_codes"]!)[1], (long?)a["tax_year"])),
        "from_pack_json" => MethodologyTree(OneZeroMethodologyJson.FromPackJson(a["block"])),
        _ => throw new PyUnsupportedException("unknown function " + fn),
    };

    private object? Credit(string fn, PyDict a, RuleLibrary lib)
    {
        switch (fn)
        {
            case "program_per_job_usd":
                return lib.ProgramPerJobUsd((string)a["key"]!);
            case "state_per_job_usd":
                return lib.StatePerJobUsd((string)a["key"]!);
            case "apply_one_zero_program_credit":
                return Traced(a, () => lib.ApplyOneZeroProgramCredit((string)a["key"]!, a["average_headcount"], a["prior"], a["threshold_override"]));
            case "apply_one_zero_state_credit":
                return Traced(a, () => lib.ApplyOneZeroStateCredit((string)a["key"]!, a["average_headcount"], a["prior"], a["threshold_override"]));
            case "combine_program_entity_credits":
                return Traced(a, () => lib.CombineProgramEntityCredits((string)a["key"]!, (PyDict)a["fein_breakdown"]!));
            case "combine_entity_credits":
                return Traced(a, () => lib.CombineEntityCredits((string)a["key"]!, (PyDict)a["fein_breakdown"]!));
            case "credit_from_pack":
                var names = ((List<object?>)a["names"]!).Cast<string>().ToList();
                return Traced(a, () => lib.CreditFromPack((PyDict)a["doc"]!, (names[0], names[1], names[2]), a["average_headcount"], a["prior"], a["threshold_override"]));
            default:
                throw new PyUnsupportedException("unknown function " + fn);
        }
    }

    // The exporter's `traced`: the call inside the recorder and wage lookups its arguments ask for, as {"result", "trail"?}.
    private PyDict Traced(PyDict a, Func<PyDict> body)
    {
        _wages.Values.Clear();
        foreach (var pair in ((List<object?>)a["wage_calls"]!).Cast<List<object?>>())
        {
            _wages.Values[(string)pair[0]!] = (double)pair[1]!;
        }

        var spec = a["trail"] as PyDict;
        var recorder = spec is null ? null : new TrailRecorder((string)spec["title"]!, (string)spec["citation"]!);
        PyDict result;
        using (recorder is null ? null : TrailContext.Use(recorder))
        {
            result = body();
        }

        var tree = new PyDict().Add("result", result);
        return recorder is null ? tree : tree.Add("trail", recorder.ToDict());
    }

    private PyDict OneZero(PyDict a, RuleLibrary lib)
    {
        var spec = a["ingestion"] as PyDict;
        _ingestion.Calls.Clear();
        _ingestion.Mode = spec is null ? "real" : spec.ContainsKey("raises") ? "raises" : "none";
        _ingestion.Value = null;
        if (spec is not null && spec.TryGetValue("value", out var value))
        {
            _ingestion.Mode = "value";
            _ingestion.Value = (PyDict?)value;
        }

        var pack = lib.LoadPackOneZero((string)a["key"]!, (long?)a["tax_year"]);
        return new PyDict().Add("pack", pack is null ? null : PackTree(pack)).Add("ingestion_calls", new List<object?>(_ingestion.Calls));
    }

    private static PyDict Views(RuleLibrary lib)
    {
        var state = lib.StateToPack.Items();
        return new PyDict()
            .Add("state", Pairs(state))
            .Add("code", Pairs(lib.CodeToPack.Items()))
            .Add("state_len", (long)lib.StateToPack.Count)
            .Add("code_len", (long)lib.CodeToPack.Count)
            .Add("state_equals", true);
    }

    private static PyDict ViewLookup(RuleLibrary lib, string view, string key)
    {
        var v = view == "state" ? lib.StateToPack : lib.CodeToPack;
        var contains = v.Contains(key);
        var get = v.TryGet(key, out var found) ? found : null;
        return new PyDict().Add("contains", contains).Add("get", get).Add("item", v[key]);
    }

    private List<object?> Sequence(PyDict a, string world)
    {
        var source = new OverlayRulePackSource(_specs[world]);
        var lib = new RuleLibrary(source);
        ProgramRegistry? previous = null;
        var output = new List<object?>();
        foreach (var step in ((List<object?>)a["steps"]!).Cast<List<object?>>())
        {
            switch ((string)step[0]!)
            {
                case "stamp":
                    source.SetStamp((long)step[1]!);
                    output.Add(new PyDict().Add("op", "stamp"));
                    break;
                case "set":
                    source.Set("registry/programs.json", (string)step[1]!);
                    source.SetStamp((long)step[2]!);
                    output.Add(new PyDict().Add("op", "set"));
                    break;
                case "file":
                    source.Set((string)step[1]!, (string)step[2]!);
                    output.Add(new PyDict().Add("op", "file"));
                    break;
                case "delete":
                    source.Set("registry/programs.json", null);
                    output.Add(new PyDict().Add("op", "delete"));
                    break;
                default:
                    try
                    {
                        var reg = lib.LoadRegistry();
                        output.Add(new PyDict().Add("op", "load").Add("registry", Summary(reg)).Add("same_as_previous", ReferenceEquals(reg, previous)));
                        previous = reg;
                    }
                    catch (PyException e)
                    {
                        output.Add(new PyDict().Add("op", "load").Add("err", e.PythonType).Add("msg", source.RulesDirectory.Length == 0 ? e.Message : e.Message.Replace(source.RulesDirectory, "<RULES>", StringComparison.Ordinal)));
                    }

                    break;
            }
        }

        return output;
    }

    private static List<object?> List(IEnumerable<object?> items) => items.ToList();

    private static List<object?> Pairs(IEnumerable<KeyValuePair<string, string>> items) =>
        items.Select(kv => (object?)new List<object?> { kv.Key, kv.Value }).ToList();

    private static PyDict? EntryTree(ProgramEntry? e) => e is null ? null : new PyDict()
        .Add("code", e.Code).Add("name", e.Name).Add("level", e.Level).Add("jurisdiction_code", e.JurisdictionCode).Add("pack_file", e.PackFile)
        .Add("state", e.State).Add("lifecycle", e.Lifecycle)
        .Add("engine_profile", new PyDict().Add("credit_model", e.EngineProfile.CreditModel).Add("headcount_model", e.EngineProfile.HeadcountModel))
        .Add("notes", e.Notes);

    private static PyDict Summary(ProgramRegistry r) => new PyDict()
        .Add("entries", List(r.Entries.Select(e => (object?)EntryTree(e))))
        .Add("active", List(r.Active().Select(e => (object?)e.Code)))
        .Add("code_to_pack", Pairs(r.CodeToPack()))
        .Add("state_to_pack", Pairs(r.StateToPack()))
        .Add("federal", List(r.Federal().Select(e => (object?)e.Code)))
        .Add("rules_dir", "<RULES>")
        .Add("source", Path.GetFileName(r.Source));

    private static PyDict YearPack((PyDict Pack, bool YearResolved) r) => new PyDict().Add("pack", r.Pack).Add("year_resolved", r.YearResolved);

    private static PyDict FloorsTree(StatutoryFloors f) => new PyDict()
        .Add("fields", new PyDict().Add("program_code", f.ProgramCode).Add("tax_year", f.TaxYear).Add("min_weekly_hours", TrailValues.Of(f.MinWeeklyHours))
            .Add("min_weekly_wages", TrailValues.Of(f.MinWeeklyWages)).Add("basis", f.Basis).Add("provenance", f.Provenance).Add("pack_file", f.PackFile))
        .Add("as_dict", f.AsDict())
        .Add("prototype_verify", f.PrototypeVerify);

    private static PyDict MethodologyTree(OneZeroMethodology m) => new PyDict()
        .Add("minimum_pay_period_days", m.MinimumPayPeriodDays)
        .Add("short_periods_excluded_from_numerator", m.ShortPeriodsExcludedFromNumerator)
        .Add("pay_period_denominator_mode", m.PayPeriodDenominatorMode)
        .Add("min_max_span_mode", m.MinMaxSpanMode)
        .Add("count_zero_hour_periods", m.CountZeroHourPeriods)
        .Add("average_decimals", (long)m.AverageDecimals)
        .Add("maximum_weeks_without_review", TrailValues.Of(m.MaximumWeeksWithoutReview))
        .Add("exclude_off_cycle_periods", m.ExcludeOffCyclePeriods);

    internal static PyDict PackTree(OneZeroPack p) => new PyDict()
        .Add("min_weekly_hours", TrailValues.Of(p.MinWeeklyHours))
        .Add("min_weekly_wages", TrailValues.Of(p.MinWeeklyWages))
        .Add("wage_basis", p.WageBasis)
        .Add("geographic_granularity", p.GeographicGranularity)
        .Add("pt_aggregation", p.PtAggregation)
        .Add("headcount_unit_field", p.HeadcountUnitField)
        .Add("citation", p.Citation)
        .Add("pt_band_hours", p.PtBandHours is { } b ? new List<object?> { TrailValues.Of(b.Low), TrailValues.Of(b.High) } : null)
        .Add("pt_weight", p.PtWeight is { } w ? TrailValues.Of(w) : null)
        .Add("measuring_date", p.MeasuringDate)
        .Add("entity_combination", p.EntityCombination)
        .Add("included_pay_codes", p.IncludedPayCodes?.Cast<object?>().ToList())
        .Add("excluded_pay_codes", p.ExcludedPayCodes?.Cast<object?>().ToList())
        .Add("tax_year", p.TaxYear)
        .Add("methodology", MethodologyTree(p.Methodology));
}
