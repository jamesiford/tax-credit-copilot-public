using TaxCredit.Application.Ports.Contract;
using TaxCredit.Application.Ports.Sources;
using TaxCredit.Domain.Calculation;
using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Pipeline;
using TaxCredit.Domain.Programs;
using static TaxCredit.Application.Features.ReadsCalc.ReadValues;

namespace TaxCredit.Application.Features.ReadsCalc.Scope;

/// <summary>Source-backed dimensions and fiscal coverage, independent of whether a client has been calculated.</summary>
public sealed class ScopeViews(ISourceReader source, ISourceCatalogue catalogue, IClientPayrollSource payroll,
    RuleLibrary library, IRuntimeConfiguration configuration, IClock clock)
{
    /// <summary>The whole source book; an unavailable source is not an empty successful book.</summary>
    public IReadOnlyList<Dictionary<string, object?>> Clients()
    {
        if (payroll.FixtureAccountId is { } fixture)
        {
            return [Map(("account_id", fixture), ("name", "Reference Dataset Client"), ("billing_state", "GA"),
                ("employees", null), ("synthetic", false), ("industry", null))];
        }
        return source.ListAccounts().Select(account => Map(("account_id", account.AccountId),
            ("name", string.IsNullOrEmpty(account.Name) ? FormattableString.Invariant($"Account {account.AccountId}") : account.Name),
            ("billing_state", account.BillingState ?? ""), ("employees", account.ActualNumberOfEmployees),
            ("synthetic", configuration.Get("DATA_CLASSIFICATION") == "synthetic"), ("industry", Industry(account.IndustryTypeId))))
            .OrderBy(row => Bool(row["synthetic"])).ThenBy(row => Text(row["name"]), PyStr.Comparer).ToArray();
    }

    /// <summary>The authored-year catalogue is derived from the same materialized packs used by the engine.</summary>
    public IReadOnlyList<Dictionary<string, object?>> Programs() =>
        library.CodeToPack.Items().OrderBy(item => item.Key, PyStr.Comparer).Select(item => Program(item.Key, item.Value)).ToArray();

    /// <summary>All selector dimensions in one response.</summary>
    public object Options()
    {
        var programs = Programs();
        var years = programs.SelectMany(Years).Distinct().Order().ToArray();
        return Map(("clients", Clients()), ("programs", programs),
            ("years", Map(("authored", years), ("latest", years.Length > 0 ? years[^1] : null),
                ("window_years", 6), ("default_window", years.Where(y => y > years[^1] - 6).ToArray()))),
            ("data_source", payroll.FixtureAccountId is null ? "lakehouse" : configuration.Get("DATA_SOURCE") ?? "csv"));
    }

    /// <summary>Counts pay dates inside statutory fiscal windows, never calendar buckets for a noncalendar filer.</summary>
    public object Client(long client)
    {
        using var shared = catalogue.SharedScope();
        if (!Clients().Any(row => Convert.ToInt64(row["account_id"], System.Globalization.CultureInfo.InvariantCulture) == client))
        {
            throw new ReadRefusalException(404, "Unknown client.");
        }
        var scope = catalogue.PayrollScope(client);
        if (scope.TotalRows == 0)
        {
            throw new ReadRefusalException(404, "No payroll for this client in the active source.");
        }
        if (scope.States.Count == 0)
        {
            throw new ReadRefusalException(422, "Payroll exists but has no resolvable work state.");
        }
        var programs = Programs().Where(p => p["jurisdiction"] is Dictionary<string, object?> jurisdiction
            && (scope.States.Contains(Text(jurisdiction["code"]), StringComparer.Ordinal) || Text(jurisdiction["level"]) == "federal")).ToArray();
        var priceable = programs.SelectMany(Years).Distinct().Order().ToArray();
        var coverage = new Dictionary<string, int>(StringComparer.Ordinal);
        var ends = new Dictionary<long, DateOnly>();
        foreach (var year in priceable)
        {
            var program = programs.First(p => Years(p).Contains(year));
            var convention = Text(library.ResolveTaxYearConvention(Text(program["program_code"]), year)["label"]);
            var window = payroll.ClientFiscalWindow(client, year, convention);
            ends[year] = window.End;
            var months = scope.PayDates.Where(day => string.CompareOrdinal(Iso(window.Begin), day) <= 0
                && string.CompareOrdinal(day, Iso(window.End)) <= 0).Select(day => day[..7]).Distinct().Count();
            if (months > 0)
            {
                coverage[year.ToString(System.Globalization.CultureInfo.InvariantCulture)] = Math.Min(months, 12);
            }
        }
        var calculable = priceable.Where(y => scope.TaxYears.Contains(y) && coverage.ContainsKey(Text(y))).ToArray();
        var complete = calculable.Where(y => coverage[Text(y)] >= 12).ToArray();
        var today = DateOnly.FromDateTime(clock.UtcNow.UtcDateTime);
        return Map(("account_id", client), ("states", scope.States), ("programs", programs), ("payroll_years", scope.TaxYears),
            ("calculable_years", calculable), ("payroll_without_statute", scope.TaxYears.Except(priceable).ToArray()),
            ("months_of_payroll", coverage), ("complete_years", complete), ("open_years", calculable.Where(y => ends[y] > today).ToArray()),
            ("default_year", complete.Length > 0 ? complete[^1] : calculable.Length > 0 ? calculable[^1] : null), ("rows", scope.TotalRows));
    }

    private Dictionary<string, object?> Program(string code, string file)
    {
        var pack = library.LoadPack(file);
        var credit = pack["credit"] as PyDict ?? new PyDict();
        var jurisdiction = pack["jurisdiction"] as PyDict ?? new PyDict();
        var name = StatutoryFloors.ProgramName(file);
        var years = library.AuthoredYears(file);
        var federal = jurisdiction.TryGetValue("level", out var level) && Text(level) == "federal";
        return Map(("program_code", code), ("name", credit.TryGetValue("name", out var title) ? title : code),
            ("citation", credit.TryGetValue("statutory_citation", out var citation) ? citation : ""),
            ("jurisdiction", Map(("level", level ?? "state"), ("code", jurisdiction.TryGetValue("code", out var state) ? state : ""),
                ("name", jurisdiction.TryGetValue("name", out var display) ? display : ""))),
            ("authored_years", years), ("placeholder_years", years.Where(y => library.ResolveStatutoryFloors(code, y).PrototypeVerify).ToArray()),
            ("year_scoped", years.Count > 0), ("calculable", years.Count > 0 && !federal),
            ("not_calculable_reason", years.Count > 0 ? federal
                ? "A federal program has no state, and a run prices a state's payroll rows: federal programs are described, not calculable." : ""
                : $"No year-scoped rule packs authored for {name}. ADR-005: statute is not inherited across years."));
    }

    private static IEnumerable<long> Years(Dictionary<string, object?> program) => (IEnumerable<long>)program["authored_years"]!;

    private static string? Industry(long? sector) => sector switch
    {
        31 => "Manufacturing",
        44 => "Retail",
        48 => "Transportation & warehousing",
        62 => "Health care",
        72 => "Food service",
        _ => null,
    };
}
