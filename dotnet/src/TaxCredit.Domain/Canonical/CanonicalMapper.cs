using TaxCredit.Domain.Calculation;
using TaxCredit.Domain.Numerics;

namespace TaxCredit.Domain.Canonical;

/// <summary>
/// Python <c>tools/canonical.py</c>: raw source rows to <see cref="CanonicalRecord"/>s with the DATA-03..06 pipeline (map, worksite join, pay-code
/// classification, cash-basis trim by pay date) and the collapse to one row per employee and pay period.
/// </summary>
/// <param name="ingested">The ingested-config port (<c>null</c> is 'none').</param>
/// <param name="sites">The worksite registry port (<c>null</c> models the registry being unavailable).</param>
public sealed class CanonicalMapper(IIngestedConfigSource? ingested = null, IWorksiteRegistry? sites = null)
{
    /// <summary>Python <c>_infer_frequency</c>: the pay frequency from the inclusive span of the period (at most 7 days weekly, 14 biweekly, 16 semimonthly, else monthly).</summary>
    /// <param name="start">First day.</param>
    /// <param name="end">Last day (a period that ends before it starts has a non-positive span and reads weekly).</param>
    /// <returns>The frequency name.</returns>
    public static string InferFrequency(DateOnly start, DateOnly end)
    {
        var span = end.DayNumber - start.DayNumber + 1;
        return span <= 7 ? "weekly" : span <= 14 ? "biweekly" : span <= 16 ? "semimonthly" : "monthly";
    }

    /// <summary>
    /// Python <c>_worksite_join</c>: the worksite's address and unit number.
    /// </summary>
    /// <remarks>
    /// Why this is always the placeholder against production's registry: the lookup calls <c>s.get(...)</c> on <c>Site</c> dataclass instances,
    /// which have no <c>get</c>; the <c>AttributeError</c> is swallowed and every worksite gets <c>(None, worksite_id)</c> (finding CQ-01).
    /// </remarks>
    /// <param name="worksiteId">The worksite id.</param>
    /// <returns>The address (or <c>null</c>) and the unit number.</returns>
#pragma warning disable CA1031 // Python's `except Exception` around the registry lookup; "registry is optional"
    public (string? Address, string UnitNumber) WorksiteJoin(string worksiteId)
    {
        try
        {
            foreach (var entry in sites?.Sites ?? [])
            {
                var s = entry as PyDict ?? throw new PyAttributeError("object has no attribute 'get'");
                if (Equals(Get(s, "worksite_id"), worksiteId) || Equals(Get(s, "id"), worksiteId))
                {
                    return (Address(s), worksiteId);
                }
            }
        }
        catch (PyAttributeError)
        {
            // fall through to the placeholder
        }

        return (null, worksiteId);
    }
#pragma warning restore CA1031

    /// <summary>
    /// Python <c>to_canonical</c>: maps the adapter's rows. A row with a missing or unparseable date is skipped; <paramref name="taxYear"/> trims by PAY DATE (DATA-06).
    /// </summary>
    /// <param name="adapter">The row source (Python defaults to the local CSV, which is an infrastructure adapter).</param>
    /// <param name="taxYear">When set, keep only rows paid in that calendar year.</param>
    /// <param name="program">Selects the pay-code classifier.</param>
    /// <returns>The canonical records in source order.</returns>
    public List<CanonicalRecord> ToCanonical(ISourceAdapter adapter, long? taxYear = null, string program = "GA_JTC")
    {
        ArgumentNullException.ThrowIfNull(adapter);
        var classifier = PayCodeClassifier.For(program, ingested);
        var records = new List<CanonicalRecord>();
        foreach (var r in adapter.Rows())
        {
            if (!TryDate(r, "Pay_Period_Start", out var start) || !TryDate(r, "Pay_Period_End", out var end) || !TryDate(r, "Pay_Date", out var payDate))
            {
                continue;
            }

            if (taxYear is not null && payDate.Year != taxYear)
            {
                continue;
            }

            var worksiteId = Text(r, "Worksite_ID", string.Empty);
            var join = WorksiteJoin(worksiteId);
            var payCode = Text(r, "Pay_Code", "Regular");
            records.Add(new CanonicalRecord(
                payDate.Year,
                Text(r, "Employee_ID", string.Empty),
                worksiteId,
                Text(r, "Entity_FEIN", string.Empty),
                InferFrequency(start, end),
                start,
                end,
                payDate,
                ProximityCoerce.FloatOrZero(r, "Hours_Worked"),
                ProximityCoerce.FloatOrZero(r, "Gross_Wages"),
                payCode,
                Text(r, "Job_Title", string.Empty),
                join.Address,
                join.UnitNumber,
                classifier.IsIncludable(payCode)));
        }

        return records;
    }

    /// <summary>
    /// Python <c>collapse_to_employee_period</c>: sums includable hours and wages per (employee, worksite, pay period end); non-includable lines are dropped.
    /// The first line of a bucket supplies its other fields, and each running total is rounded to 2 places after every addition (Python <c>round</c>, half to even).
    /// </summary>
    /// <param name="records">The canonical records.</param>
    /// <returns>One tree per bucket in first-seen order.</returns>
    public static List<PyDict> CollapseToEmployeePeriod(IEnumerable<CanonicalRecord> records)
    {
        ArgumentNullException.ThrowIfNull(records);
        var buckets = new Dictionary<(string, string, string), (PyDict Tree, double Hours, double Wages)>();
        var order = new List<(string, string, string)>();
        foreach (var rec in records)
        {
            if (!rec.Includable)
            {
                continue;
            }

            var key = (rec.EmployeeId, rec.WorksiteId, Iso(rec.PayPeriodEnd));
            if (!buckets.TryGetValue(key, out var b))
            {
                b = (NewBucket(rec), 0.0, 0.0);
                order.Add(key);
            }

            buckets[key] = (b.Tree, PyRound.Round(b.Hours + rec.HoursWorked, 2), PyRound.Round(b.Wages + rec.GrossWages, 2));
        }

        return order.Select(k => buckets[k]).Select(b => b.Tree.Set("hours_worked", b.Hours).Set("gross_wages", b.Wages)).ToList();
    }

    private static PyDict NewBucket(CanonicalRecord rec) => new PyDict()
        .Add("tax_year", rec.TaxYear)
        .Add("employee_id", rec.EmployeeId)
        .Add("worksite_id", rec.WorksiteId)
        .Add("legal_entity_fein", rec.LegalEntityFein)
        .Add("pay_frequency", rec.PayFrequency)
        .Add("pay_period_start", Iso(rec.PayPeriodStart))
        .Add("pay_period_end", Iso(rec.PayPeriodEnd))
        .Add("pay_date", Iso(rec.PayDate))
        .Add("hours_worked", 0.0)
        .Add("gross_wages", 0.0);

    private static string Iso(DateOnly d) => d.ToString("yyyy-MM-dd", System.Globalization.CultureInfo.InvariantCulture);

    private static object? Get(PyDict row, string key) => row.TryGetValue(key, out var v) ? v : null;

    // Python `str(r.get(key, default))`.
    private static string Text(PyDict row, string key, string fallback) => row.TryGetValue(key, out var v) ? ProximityCoerce.Str(v) : fallback;

    // Python `date.fromisoformat(str(r[key])[:10])` inside `except (KeyError, ValueError): continue`.
    private static bool TryDate(PyDict row, string key, out DateOnly date)
    {
        date = default;
        return row.TryGetValue(key, out var v) && PyDate.TryFromIsoFormat(PyStr.Prefix(ProximityCoerce.Str(v), 10), out date);
    }

    // Python `s.get("address") or f"{s.get('city', '')}, {s.get('state', '')}".strip(", ")`.
    private static string? Address(PyDict s)
    {
        var address = Get(s, "address");
        if (ProximityCoerce.Truthy(address))
        {
            return address as string ?? throw new PyUnsupportedException("a non-string worksite address is not modelled");
        }

        var city = s.TryGetValue("city", out var c) ? ProximityCoerce.Str(c) : string.Empty;
        var state = s.TryGetValue("state", out var st) ? ProximityCoerce.Str(st) : string.Empty;
        return (city + ", " + state).Trim(',', ' ');
    }
}
