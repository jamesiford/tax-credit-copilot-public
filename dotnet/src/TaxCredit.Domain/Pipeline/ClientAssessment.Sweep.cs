using System.Globalization;
using TaxCredit.Domain.Calculation;
using TaxCredit.Domain.Numerics;

namespace TaxCredit.Domain.Pipeline;

public sealed partial class ClientAssessment
{
    /// <summary>Average Headcount per (PROGRAM, year), and what could not be computed and why (Python <c>_Sweep</c>).</summary>
    private sealed class Sweep(ClientAssessment owner, long clientId, IReadOnlyList<PayRow> rows, IReadOnlyList<long> requested, IReadOnlyList<long> years, string? wanted)
    {
        public long ClientId { get; } = clientId;

        public IReadOnlyList<long> Requested { get; } = requested;

        public Dictionary<(string Code, long Year), double> Averages { get; } = [];

        public List<PyDict> Declined { get; } = [];

        private Dictionary<(string Code, long Year), string> Assumed { get; } = [];

        public void Run(IReadOnlyList<string> states)
        {
            foreach (var state in states)
            {
                foreach (var entry in owner._library.ProgramsForState(state))
                {
                    if (wanted is null || entry.Code == wanted)
                    {
                        Program(state, entry.Code, entry.PackFile);
                    }
                }
            }
        }

        private void Decline(string code, long? year, string reason, string detail, bool onlyIfRequested = true)
        {
            if (onlyIfRequested && (year is null || !Requested.Contains(year.Value)))
            {
                return;
            }

            Declined.Add(new PyDict().Add("program_code", code).Add("tax_year", year).Add("reason", reason).Add("detail", detail));
        }

        // [ADR-005] A program with no authored years is describable, not calculable.
        private void Program(string state, string code, string packFile)
        {
            var priceable = owner._library.AuthoredYears(packFile).ToHashSet();
            if (priceable.Count == 0)
            {
                Decline(
                    code, null, "program_not_year_scoped",
                    $"{code} has no year-scoped rule packs. ADR-005: a figure computed without a year-resolved statute is not a statutory figure.",
                    onlyIfRequested: false);
                return;
            }

            foreach (var year in years)
            {
                if (priceable.Contains(year))
                {
                    Year(state, code, year);
                }
                else
                {
                    Decline(
                        code, year, "no_authored_statute",
                        $"No rule pack for {code} tax year {year.ToString(CultureInfo.InvariantCulture)}. "
                        + $"Authored: {string.Join(", ", priceable.Order().Select(y => y.ToString(CultureInfo.InvariantCulture)))}.");
                }
            }
        }

        private void Year(string state, string code, long year)
        {
            var pack = owner._library.LoadPackOneZero(code, year);
            if (pack is null)
            {
                return;
            }

            // The CLIENT's twelve months, not January to December: a non-calendar filer measured over the calendar year scores every month before its first pay date as zero.
            var resolution = owner._fiscal.FiscalWindowForStateYear(ClientId, code, year);
            (DateOnly Begin, DateOnly End)? window = resolution is null ? null : (resolution.Begin, resolution.End);
            if (resolution is { Assumed: true })
            {
                Assumed[(code, year)] = resolution.Note;
            }

            var yearRows = Headcount.RowsForStateYear(rows.Select(r => r.Row).ToList(), state, year, window);
            if (yearRows.Count < MinRowsToAssess)
            {
                return;
            }

            // An OPEN year is never claimed: pricing eight months over twelve would re-rank the book on a fraction of a year.
            if (window is { } w && OpenYear.IsOpen(w.End, today: owner._today))
            {
                Decline(
                    code, year, "year_in_progress",
                    $"TY{year.ToString(CultureInfo.InvariantCulture)} is still open (its fiscal year ends {w.End.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture)}). "
                    + "It is read in-year on How am I doing, and claimed once it closes.");
                return;
            }

            var months = yearRows.Select(r => r.PayDate).Where(c => c.Kind == CellKind.Text && c.Text!.Length > 0).Select(c => PyStr.Prefix(c.Text!, 7)).Distinct(StringComparer.Ordinal).Count();
            if (months < MinMonthsToAssess)
            {
                Decline(
                    code, year, "payroll_too_thin",
                    $"Payroll covers {months.ToString(CultureInfo.InvariantCulture)} month(s) of the {year.ToString(CultureInfo.InvariantCulture)} fiscal year. A twelve-month average would be mostly zeroes.");
                return;
            }

            Averages[(code, year)] = Headcount.AverageHeadcount(rows.Select(r => r.Row).ToList(), state, year, pack, window);
        }
    }
}
