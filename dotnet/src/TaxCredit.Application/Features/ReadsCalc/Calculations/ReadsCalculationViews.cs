using System.Globalization;
using System.Text.Json;
using TaxCredit.Application.Features.ReadsCalc.Ingestion;
using TaxCredit.Application.Ports.Persistence;
using TaxCredit.Application.Ports.Sources;
using TaxCredit.Domain.Calculation;
using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Pipeline;
using TaxCredit.Domain.Programs;

namespace TaxCredit.Application.Features.ReadsCalc.Calculations;

/// <summary>Source-backed legacy reports and explicit what-ifs, never a replacement for accepted Gold reads.</summary>
public sealed partial class ReadsCalculationViews(
    RuleLibrary library,
    ProgramDefaults defaults,
    ClientRunResolver resolver,
    IClientPayrollSource source,
    ILookupStore lookups,
    IGoldReadPort gold,
    ClientCalculationConfig configuration,
    QcAnnotations qc)
{
    /// <summary>Allows mediator requests to reuse the already-bound operation arguments.</summary>
    public object Execute(string operation, ReadArguments args)
    {
        ArgumentNullException.ThrowIfNull(args);
        return Execute(operation, args.Parameters, args.Body);
    }

    /// <summary>Application-only transport seam shared by the API and deterministic capability callers.</summary>
    public object Execute(string operation, IReadOnlyDictionary<string, string?> parameters, JsonElement? body = null)
    {
        var args = new ReadArguments(parameters, body);
        try
        {
            return ReadValues.Transport(Dispatch(Operation(operation), args))!;
        }
        catch (PayrollDatasetNotGenerated e) { throw new ReadRefusalException(503, e.Message); }
        catch (NoPayrollForClient e) { throw new ReadRefusalException(404, e.Message); }
        catch (ClientRunNotAvailable e) { throw new ReadRefusalException(404, e.Message); }
        catch (ProgramNotRunnableError e) { throw new ReadRefusalException(422, e.Message); }
        catch (PyFileNotFoundError e) { throw new ReadRefusalException(404, e.Message); }
        catch (PyValueError e) { throw new ReadRefusalException(422, e.Message); }
    }

    private PyDict Dispatch(string operation, ReadArguments args) => operation switch
    {
        "forecast" => Forecast(args),
        "monthly_alerts" => MonthlyAlerts(args),
        "triggers" => Triggers(args),
        "performance" or "performance_dashboard" => Performance(args),
        "onezero" or "one_zero" => OneZero(args),
        "onezero_employee" or "one_zero_employee" => Employee(args),
        "review_employee" => ReviewEmployee(args),
        "designations" => Designations(args),
        "reconcile" or "reconcile_endpoint" => Reconcile(args),
        "qc" or "qc_exception_report" => Qc(args),
        "retroactive" or "one_zero_retroactive_scan" => Retroactive(args),
        "simulate_onezero" or "run_onezero_simulation" => SimulateOneZero(args),
        "simulate_portfolio" => SimulatePortfolio(args),
        "simulate_unit" or "run_unit_simulation" => SimulateUnit(args),
        "simulate_employee" or "run_employee_simulation" => SimulateEmployee(args),
        _ => throw new ReadRefusalException(404, "Unknown calculation view.")
    };

    private static string Operation(string value) => value switch
    {
        "GET /api/forecast/{tax_year}" => "forecast",
        "GET /api/alerts/monthly/{tax_year}" => "monthly_alerts",
        "GET /api/triggers" => "triggers",
        "GET /api/performance/{tax_year}" => "performance",
        "GET /api/onezero/{tax_year}" => "onezero",
        "GET /api/onezero/{tax_year}/employee/{employee_id}" => "onezero_employee",
        "POST /api/onezero/employee/{employee_id}/review" => "review_employee",
        "GET /api/designations/{state}" => "designations",
        "GET /api/reconcile/{tax_year}" => "reconcile",
        "GET /api/qc/{tax_year}" => "qc",
        "GET /api/onezero/retroactive/scan" => "retroactive",
        "GET /api/simulate/portfolio/{tax_year}" => "simulate_portfolio",
        "POST /api/simulate/unit" => "simulate_unit",
        "POST /api/simulate/employee" => "simulate_employee",
        "POST /api/simulate/onezero" => "simulate_onezero",
        _ => value
    };

    private string Today => configuration.Today().ToString("yyyy-MM-dd", CultureInfo.InvariantCulture);

    private IReadOnlyList<PayRow> Rows(ReadArguments args, bool dropQc = false, string clientKey = "account_id")
    {
        var client = args.Client(clientKey);
        var resolutions = dropQc ? qc.Resolutions(client) : new QcResolutionStore();
        return PayrollRows.RequirePayPeriods(source, resolutions, dropQc, client);
    }

    private static List<PayrollRow> EngineRows(IEnumerable<PayRow> rows) => rows.Select(r => r.Row).ToList();
    private static List<PyDict> Dictionaries(IEnumerable<PayRow> rows) => rows.Select(r => r.Dict).ToList();
    private static double Num(PyDict row, string key) => row.TryGetValue(key, out var value) && value is not null ? ReadValues.Number(value) : 0;
    private static string? Text(PyDict row, string key) => row.TryGetValue(key, out var value) ? value as string : null;
    private static PyDict Dict(params (string Key, object? Value)[] fields) =>
        fields.Aggregate(new PyDict(), (result, field) => result.Add(field.Key, field.Value));
    private static long Year(ReadArguments args, long fallback = 2025)
    {
        var year = args.WholeNumber("tax_year", (int)fallback);
        return year is >= 2 and <= 9998 ? year : throw new ReadRefusalException(422, "Tax year must be between 2 and 9998.");
    }

    private static List<PayRow> FiscalRows(IEnumerable<PayRow> rows, long year, long endMonth = 12) =>
        rows.Where(r => OneZeroCalendar.FiscalYearOf(DateOnly.ParseExact(r.PayDateText(), "yyyy-MM-dd", CultureInfo.InvariantCulture), endMonth) == year).ToList();

    private static List<PayRow> TaggedRows(IEnumerable<PayRow> rows, long year) =>
        rows.Where(r => r.Get("Tax_Year") is { } value && ReadValues.Number(value) == year).ToList();

    private static OneZeroResult Run(IReadOnlyList<PayRow> rows, long year, OneZeroPack pack, string method = "pay_period") =>
        method == "min_max"
            ? MinMaxMethod.Run(EngineRows(rows), year, OneZeroCalendar.FiscalWindowStart(year, 12), pack)
            : PayPeriodMethod.Run(EngineRows(rows), year, OneZeroCalendar.FiscalWindowStart(year, 12), pack);

    private static OneZeroResult RunClient(ClientRun run, IReadOnlyList<PayrollRow> rows, string method)
    {
        var args = run.EngineKwargs();
        return method == "min_max"
            ? MinMaxMethod.Run(rows, args.TaxYear, args.AnalysisStartMonth, args.Pack, fiscalWindow: args.FiscalWindow)
            : PayPeriodMethod.Run(rows, args.TaxYear, args.AnalysisStartMonth, args.Pack, fiscalWindow: args.FiscalWindow);
    }
}
