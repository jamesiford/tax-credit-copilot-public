using TaxCredit.Domain.Calculation;
using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Programs;
using TaxCredit.Domain.Qc;

namespace TaxCredit.Domain.Pipeline;

/// <summary>The in-memory store of human QC resolutions (Python <c>application/qc_resolutions.QC_RESOLUTIONS</c>): exception id to <c>{resolution, keep_worksite}</c>.</summary>
public sealed class QcResolutionStore
{
    private readonly List<KeyValuePair<string, PyDict>> _items = [];

    /// <summary>True when nothing is resolved (Python <c>not QC_RESOLUTIONS</c>).</summary>
    public bool IsEmpty => _items.Count == 0;

    /// <summary>Python <c>QC_RESOLUTIONS[id] = resolution</c>.</summary>
    /// <param name="exceptionId">The exception id.</param>
    /// <param name="resolution">The resolution (<c>resolution</c> and optionally <c>keep_worksite</c>).</param>
    public void Set(string exceptionId, PyDict resolution)
    {
        var at = _items.FindIndex(kv => kv.Key == exceptionId);
        if (at >= 0)
        {
            _items[at] = new KeyValuePair<string, PyDict>(exceptionId, resolution);
        }
        else
        {
            _items.Add(new KeyValuePair<string, PyDict>(exceptionId, resolution));
        }
    }

    /// <summary>Python <c>reset_qc_resolutions</c>.</summary>
    public void Clear() => _items.Clear();

    /// <summary>The entries in insertion order.</summary>
    public IReadOnlyList<KeyValuePair<string, PyDict>> Items => _items;
}

/// <summary>Human resolutions of QC exceptions and how they reach the calculation (Python <c>application/qc_resolutions.py</c>).</summary>
public static class QcResolutions
{
    /// <summary>Python <c>exception_id</c>: a deterministic id so a resolution sticks to the same anomaly across reloads.</summary>
    /// <param name="anomaly">The anomaly (<c>type</c>, <c>employee_id</c>, <c>month</c>, <c>line_key</c>).</param>
    /// <returns>The id.</returns>
    public static string ExceptionId(PyDict anomaly)
    {
        ArgumentNullException.ThrowIfNull(anomaly);
        if (anomaly.TryGetValue("type", out var type) && type is string t && t == "test_of_twos")
        {
            return $"t2:{Text(anomaly, "employee_id")}:{Text(anomaly, "month")}";
        }

        return $"pp:{Text(anomaly, "line_key")}";
    }

    /// <summary>
    /// Python <c>apply_calc_drops</c>: filter pay-period rows per the human QC resolutions, so a resolved exception flows into the calculation. A
    /// test-of-twos <c>assign</c> keeps one worksite for an (employee, month); a scraggly <c>drop</c> removes one payroll LINE; <c>accept</c> and
    /// <c>flag</c> are annotations and never change the rows.
    /// </summary>
    /// <param name="store">The resolutions.</param>
    /// <param name="rows">The rows.</param>
    /// <returns>The same list when nothing drops, else the kept rows.</returns>
    public static IReadOnlyList<PayRow> ApplyCalcDrops(QcResolutionStore store, IReadOnlyList<PayRow> rows)
    {
        ArgumentNullException.ThrowIfNull(store);
        ArgumentNullException.ThrowIfNull(rows);
        if (store.IsEmpty)
        {
            return rows;
        }

        var (keep, drop) = DropRules(store);
        if (keep.Count == 0 && drop.Count == 0)
        {
            return rows;
        }

        var keys = drop.Count > 0 ? PayLineKeys.Keys(rows.Select(r => r.Dict)) : null;
        return rows.Where((r, i) => !IsDropped(r.Dict, keys?[i], keep, drop)).ToList();
    }

    private static string Text(PyDict d, string key) => d.TryGetValue(key, out var v) ? ProximityCoerce.Str(v) : "None";

    private static (Dictionary<(string, string), string> Keep, HashSet<string> Drop) DropRules(QcResolutionStore store)
    {
        var keep = new Dictionary<(string, string), string>();
        var drop = new HashSet<string>(StringComparer.Ordinal);
        foreach (var (id, res) in store.Items)
        {
            var parts = id.Split(':');
            var resolution = res.TryGetValue("resolution", out var r) ? r as string : null;
            if (id.StartsWith("t2:", StringComparison.Ordinal) && resolution == "assign" && res.TryGetValue("keep_worksite", out var kw) && ProximityCoerce.Truthy(kw))
            {
                if (parts.Length >= 3)
                {
                    keep[(parts[1], parts[2])] = (string)kw!;
                }
            }
            else if (id.StartsWith("pp:", StringComparison.Ordinal) && resolution == "drop")
            {
                drop.Add(id[3..]);
            }
        }

        return (keep, drop);
    }

    // Python `str(row.get(key, ""))`: an absent key is "", a present None is "None".
    private static string Or(PyDict row, string key) => row.TryGetValue(key, out var v) ? ProximityCoerce.Str(v) : string.Empty;

    private static bool IsDropped(PyDict row, string? lineKey, Dictionary<(string, string), string> keep, HashSet<string> drop)
    {
        var employee = Or(row, "Employee_ID");
        var worksite = Or(row, "Worksite_ID");
        var month = PyStr.Prefix(Or(row, "Pay_Date"), 7);
        if (keep.TryGetValue((employee, month), out var keepWorksite) && worksite != keepWorksite)
        {
            return true; // a double-count reassigned away from this unit
        }

        return lineKey is not null && drop.Contains(lineKey);
    }
}

/// <summary>Loading pay-period rows and walking the rule packs, without a web framework (Python <c>application/payroll_rows.py</c>).</summary>
/// <param name="library">The rule library.</param>
/// <param name="defaults">The program defaults (the programs a state prices).</param>
public sealed class PayrollRows(RuleLibrary library, ProgramDefaults defaults)
{
    /// <summary>Python <c>NOT_GENERATED_DETAIL</c>.</summary>
    public const string NotGeneratedDetail = "Pay-period dataset not generated. Run `python data/generate_pay_periods.py`.";

    /// <summary>Python <c>require_pay_periods</c>: the rows, or <see cref="PayrollNotAvailable"/> when there are none.</summary>
    /// <param name="source">Where rows come from.</param>
    /// <param name="qc">The QC resolutions applied when <paramref name="dropQc"/>.</param>
    /// <param name="dropQc">Whether calc reads apply the human resolutions.</param>
    /// <param name="accountId">The tenant; <c>null</c> keeps the configured default.</param>
    /// <returns>The rows.</returns>
    /// <exception cref="NoPayrollForClient">When a named client has no rows.</exception>
    /// <exception cref="PayrollDatasetNotGenerated">When the default dataset has none.</exception>
    public static IReadOnlyList<PayRow> RequirePayPeriods(IPayrollSource source, QcResolutionStore qc, bool dropQc = false, long? accountId = null)
    {
        ArgumentNullException.ThrowIfNull(source);
        var rows = source.LoadPayPeriods(accountId);
        if (rows.Count == 0)
        {
            throw accountId is { } id
                ? new NoPayrollForClient($"No payroll for client {id} in the active data source.")
                : new PayrollDatasetNotGenerated(NotGeneratedDetail);
        }

        return dropQc ? QcResolutions.ApplyCalcDrops(qc, rows) : rows;
    }

    /// <summary>Python <c>program_rows</c>: the rows a state-level program prices, those whose work state is the program's state. The ONE definition of "which rows does a program see". [F04c.5]</summary>
    /// <param name="rows">The rows.</param>
    /// <param name="programState">The program's state.</param>
    /// <returns>The rows, in order.</returns>
    public static IReadOnlyList<PayRow> ProgramRows(IEnumerable<PayRow> rows, string programState)
    {
        ArgumentNullException.ThrowIfNull(rows);
        var state = PyStr.Upper(programState);
        return rows.Where(r => Headcount.RowState(r.Row) == state).ToList();
    }

    /// <summary>Python <c>states_present</c>: every work state appearing in these rows, sorted.</summary>
    /// <param name="rows">The rows.</param>
    /// <returns>The states.</returns>
    public static IReadOnlyList<string> StatesPresent(IEnumerable<PayRow> rows) => Headcount.StatesPresent(rows.Select(r => r.Row).ToList());

    /// <summary>Python <c>unauthored_state_years</c>: which <c>(tax year, state)</c> pairs have no authored statute, so a sweep can DECLINE them by name.</summary>
    /// <param name="taxYears">The years.</param>
    /// <param name="state">One state, or <c>null</c> for every registry state.</param>
    /// <returns>Year to (state or program code to the error text); insertion order is first gap found.</returns>
    public PyDict UnauthoredStateYears(IEnumerable<long> taxYears, string? state = null)
    {
        var states = !string.IsNullOrEmpty(state) ? [PyStr.Upper(state)] : library.StateToPack.SortedKeys();
        var gaps = new PyDict();
        foreach (var year in taxYears)
        {
            foreach (var st in states)
            {
                var codes = defaults.ProgramsToPrice(st);
                for (var i = 0; i < (codes.Count > 0 ? codes.Count : 1); i++)
                {
                    var code = codes.Count > 0 ? codes[i] : st;
                    try
                    {
                        library.LoadPackOneZero(code, year);
                    }
                    catch (PyFileNotFoundError e)
                    {
                        var key = year.ToString(System.Globalization.CultureInfo.InvariantCulture);
                        var perYear = gaps.TryGetValue(key, out var existing) ? (PyDict)existing! : new PyDict();
                        gaps.Set(key, perYear.Set(i == 0 ? st : code, e.Message));
                    }
                }
            }
        }

        return gaps;
    }

    /// <summary>One program of a state with rows: Python <c>StatePack</c> (<c>(state, pack, state_rows)</c> plus the program it belongs to).</summary>
    /// <param name="State">The state.</param>
    /// <param name="Pack">The One/Zero pack.</param>
    /// <param name="Rows">The state's rows (programs of a state share them).</param>
    /// <param name="ProgramCode">The program the pack belongs to.</param>
    public sealed record StatePack(string State, OneZeroPack Pack, IReadOnlyList<PayRow> Rows, string ProgramCode);

    /// <summary>Python <c>iter_state_packs</c>: one item per PROGRAM that has rows, with its rule pack for <paramref name="taxYear"/>. [ADR-005]</summary>
    /// <param name="rows">The payroll.</param>
    /// <param name="taxYear">The year.</param>
    /// <param name="state">One state, or <c>null</c> for every registry state.</param>
    /// <param name="onUnauthored"><c>raise</c> (default) or <c>skip</c>: what an unauthored year does.</param>
    /// <returns>The items, lazily (an error surfaces when the sequence is enumerated, as with a Python generator).</returns>
    /// <exception cref="PyValueError">For any other <paramref name="onUnauthored"/>, when enumerated.</exception>
    public IEnumerable<StatePack> IterStatePacks(IReadOnlyList<PayRow> rows, long taxYear, string? state = null, string onUnauthored = "raise")
    {
        if (onUnauthored is not ("raise" or "skip"))
        {
            throw new PyValueError("on_unauthored must be 'raise' or 'skip'");
        }

        foreach (var st in !string.IsNullOrEmpty(state) ? [PyStr.Upper(state)] : library.StateToPack.SortedKeys())
        {
            var stateRows = ProgramRows(rows, st);
            var codes = defaults.ProgramsToPrice(st);
            foreach (var code in codes.Count > 0 ? codes : [st])
            {
                OneZeroPack? pack;
                try
                {
                    pack = library.LoadPackOneZero(code, taxYear);
                }
                catch (PyFileNotFoundError) when (onUnauthored != "raise")
                {
                    pack = null;
                }

                if (pack is not null && stateRows.Count > 0)
                {
                    yield return new StatePack(st, pack, stateRows, code);
                }
            }
        }
    }
}
