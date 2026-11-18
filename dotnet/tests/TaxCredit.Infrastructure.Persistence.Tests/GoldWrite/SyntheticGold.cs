using System.Globalization;
using TaxCredit.Domain.Gold;
using TaxCredit.Domain.Pipeline;

namespace TaxCredit.Infrastructure.Persistence.Tests.GoldWrite;

/// <summary>
/// A Gold payload of the requested size built from the committed golden run, so cell kinds and value shapes are the real ones.
/// Only the employee-grain tables grow; the unit-level tables stay as they are, as they do for a real client.
/// </summary>
internal static class SyntheticGold
{
    /// <summary>Roughly the ratio of pay-period rows to employees in the measured client (384,418 periods, about 10,000 employees).</summary>
    private const int PeriodsPerEmployee = 38;

    internal static GoldRunPayload Payload(int periodRows, string runId, long clientId = 1001)
    {
        var template = GoldenPayload.Reidentify(GoldenPayload.Read(GoldenPayload.Scenario("csv-ty2025-ga")), runId, clientId);
        var employees = Math.Max(1, periodRows / PeriodsPerEmployee);
        return template with
        {
            EmployeePeriodFact = Scale(template.EmployeePeriodFact, periodRows),
            EmployeeEligibility = Scale(template.EmployeeEligibility, employees),
            OneZeroMatrix = Scale(template.OneZeroMatrix, employees),
        };
    }

    private static GoldRow[] Scale(IReadOnlyList<GoldRow> source, int count)
    {
        var rows = new GoldRow[count];
        for (var i = 0; i < count; i++)
        {
            var row = source[i % source.Count];
            var cells = row.Cells.ToArray();
            for (var c = 0; c < cells.Length; c++)
            {
                cells[c] = row.Columns[c] switch
                {
                    "employee_id" => GoldCell.OfText("E" + (i / PeriodsPerEmployee).ToString(CultureInfo.InvariantCulture)),
                    "record_token" => GoldCell.OfText(i.ToString("x24", CultureInfo.InvariantCulture)),
                    _ => cells[c],
                };
            }

            rows[i] = new GoldRow(row.Table, row.Columns, cells);
        }

        return rows;
    }
}
