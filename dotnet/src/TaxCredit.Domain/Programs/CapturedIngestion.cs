using System.Globalization;
using TaxCredit.Domain.Numerics;

namespace TaxCredit.Domain.Programs;

/// <summary>
/// The offline half of Python <c>tools/rules_ingestion.py</c>: the captured, cited config (<c>data/rules_ingested/&lt;program&gt;.json</c>) resolved into
/// the flat <c>one_zero</c> shape <see cref="RuleLibrary.LoadPackOneZero"/> reads (<c>ingested_one_zero</c>). Web retrieval, live refresh and the
/// per-value provenance report are NOT ported: <c>load_pack_one_zero</c> reads none of them.
/// </summary>
/// <remarks>Only GA and TN are ingested; every other key answers <c>null</c> so callers fall back to the static pack.</remarks>
public sealed class CapturedIngestion(IIngestedConfigFiles files) : IIngestedOneZeroSource
{
    // Python `_PROGRAM_FILE`: program code or state to the ingested config's file name.
    private static readonly Dictionary<string, string> ProgramFile = new(StringComparer.Ordinal)
    {
        ["GA_JTC"] = "ga_jtc.json",
        ["GA"] = "ga_jtc.json",
        ["TN_JTC"] = "tn_jtc.json",
        ["TN"] = "tn_jtc.json",
    };

    /// <inheritdoc />
    public PyDict? IngestedOneZero(string programOrState, long? taxYear)
    {
        ArgumentNullException.ThrowIfNull(programOrState);
        var cfg = Load(programOrState);
        if (cfg is null)
        {
            return null;
        }

        var parameters = RuleTree.Get(cfg, "parameters", new PyDict());
        var minHours = Floor(parameters, "min_weekly_hours");
        var minWages = Floor(parameters, "min_weekly_wages");
        if (taxYear is not null)
        {
            // [CALC-03] Year-specific override (for example the GA 2025 wage floor).
            var byYear = RuleTree.Truthy(RuleTree.Get(cfg, "thresholds_by_year")) ? RuleTree.AsMapping(RuleTree.Get(cfg, "thresholds_by_year")) : new PyDict();
            if (RuleTree.Get(byYear, taxYear.Value.ToString(CultureInfo.InvariantCulture)) is PyDict yearBlock)
            {
                minWages = yearBlock.ContainsKey("min_weekly_wages") ? RuleTree.Float(yearBlock["min_weekly_wages"]) : minWages;
                minHours = yearBlock.ContainsKey("min_weekly_hours") ? RuleTree.Float(yearBlock["min_weekly_hours"]) : minHours;
            }
        }

        var wageNode = RuleTree.Get(RuleTree.AsMapping(parameters), "wage_basis") is PyDict node ? node : new PyDict();
        return new PyDict()
            .Add("min_weekly_hours", minHours)
            .Add("min_weekly_wages", minWages)
            .Add("wage_basis", Value(parameters, "wage_basis", "all_remuneration"))
            .Add("measuring_date", Value(parameters, "measuring_date", "last_day"))
            .Add("included_pay_codes", RuleTree.Get(wageNode, "included_pay_codes"))
            .Add("excluded_pay_codes", RuleTree.Get(wageNode, "excluded_pay_codes"))
            .Add("source", "rules_ingested");
    }

    // load_ingested_config: `_PROGRAM_FILE.get(key.upper())`, then the file when it exists.
    private PyDict? Load(string programOrState)
    {
        if (!ProgramFile.TryGetValue(PyStr.Upper(programOrState), out var fileName))
        {
            return null;
        }

        var text = files.ReadText(fileName);
        return text is null ? null : PyJson.Loads(text) as PyDict ?? throw new PyUnsupportedException("an ingested config that is not an object is not modelled");
    }

    // `float(_val(name, 0.0) or 0.0)`
    private static double Floor(object? parameters, string name)
    {
        var value = Value(parameters, name, 0.0);
        return RuleTree.Truthy(value) ? RuleTree.Float(value) : 0.0;
    }

    // `_val`: `node.get("value") if isinstance(node, dict) else default`
    private static object? Value(object? parameters, string name, object? fallback) =>
        RuleTree.Get(RuleTree.AsMapping(parameters), name) is PyDict node ? RuleTree.Get(node, "value") : fallback;
}
