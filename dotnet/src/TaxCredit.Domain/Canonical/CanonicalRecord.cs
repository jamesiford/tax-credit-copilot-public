using TaxCredit.Domain.Numerics;

namespace TaxCredit.Domain.Canonical;

/// <summary>
/// Python <c>tools/canonical.py</c> <c>CanonicalRecord</c>: one employee, one pay period, the grain every downstream calculation needs.
/// </summary>
/// <param name="TaxYear">The calendar year of the pay date (cash basis: the year PAID, not earned).</param>
/// <param name="EmployeeId">Surrogate employee id.</param>
/// <param name="WorksiteId">Worksite id.</param>
/// <param name="LegalEntityFein">The legal entity's FEIN.</param>
/// <param name="PayFrequency">Frequency inferred from the period span.</param>
/// <param name="PayPeriodStart">First day of the pay period.</param>
/// <param name="PayPeriodEnd">Last day of the pay period.</param>
/// <param name="PayDate">The pay date (the cash-basis anchor).</param>
/// <param name="HoursWorked">Hours worked.</param>
/// <param name="GrossWages">Gross wages.</param>
/// <param name="PayCode">Pay code; Python's default is <c>Regular</c>.</param>
/// <param name="JobTitle">Job title (empty when absent).</param>
/// <param name="WorksiteAddress">Address from the worksite join, or <c>null</c>.</param>
/// <param name="UnitNumber">Unit number from the worksite join.</param>
/// <param name="Includable">Whether the pay code counts towards the wage base.</param>
public sealed record CanonicalRecord(
    long TaxYear,
    string EmployeeId,
    string WorksiteId,
    string LegalEntityFein,
    string PayFrequency,
    DateOnly PayPeriodStart,
    DateOnly PayPeriodEnd,
    DateOnly PayDate,
    double HoursWorked,
    double GrossWages,
    string PayCode = "Regular",
    string JobTitle = "",
    string? WorksiteAddress = null,
    string? UnitNumber = null,
    bool Includable = true)
{
    /// <summary>The record as the tree Python's <c>golden_rec.enc</c> writes for the dataclass (field order, dates as <c>{"$date"}</c>).</summary>
    /// <returns>The tree.</returns>
    public PyDict ToTree() => new PyDict()
        .Add("tax_year", TaxYear)
        .Add("employee_id", EmployeeId)
        .Add("worksite_id", WorksiteId)
        .Add("legal_entity_fein", LegalEntityFein)
        .Add("pay_frequency", PayFrequency)
        .Add("pay_period_start", Tag(PayPeriodStart))
        .Add("pay_period_end", Tag(PayPeriodEnd))
        .Add("pay_date", Tag(PayDate))
        .Add("hours_worked", HoursWorked)
        .Add("gross_wages", GrossWages)
        .Add("pay_code", PayCode)
        .Add("job_title", JobTitle)
        .Add("worksite_address", WorksiteAddress)
        .Add("unit_number", UnitNumber)
        .Add("includable", Includable);

    private static PyDict Tag(DateOnly d) => new PyDict().Add("$date", d.ToString("yyyy-MM-dd", System.Globalization.CultureInfo.InvariantCulture));
}
