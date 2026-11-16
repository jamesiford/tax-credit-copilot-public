using System.Globalization;
using TaxCredit.Api.Wire;
using TaxCredit.Application.Features.ReadsCalc;
using TaxCredit.Application.Messaging;
using TaxCredit.Application.Ports.Auth;
using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Pipeline;

namespace TaxCredit.Api.Endpoints.ReadsCalc;

/// <summary>The decided ReadsCalc operation set. Exact method/templates replace only this group's inherited stubs.</summary>
public sealed class ReadsCalcEndpoints : IEndpointGroup
{
    private static readonly (string Method, string Path, string View)[] Operations =
    [
        ("GET", "/api/me", "me"),
        ("GET", "/api/eligibility/{tax_year}", "eligibility"),
        ("GET", "/api/progress/{tax_year}", "progress"),
        ("GET", "/api/forecast/{tax_year}", ""),
        ("GET", "/api/alerts/monthly/{tax_year}", ""),
        ("GET", "/api/triggers", ""),
        ("GET", "/api/performance/{tax_year}", ""),
        ("GET", "/api/onezero/matrix/{tax_year}", "matrix"),
        ("GET", "/api/onezero/{tax_year}", ""),
        ("GET", "/api/onezero/{tax_year}/employee/{employee_id}", ""),
        ("POST", "/api/onezero/employee/{employee_id}/review", "review"),
        ("GET", "/api/designations/{state}", ""),
        ("GET", "/api/reconcile/{tax_year}", ""),
        ("GET", "/api/qc/{tax_year}", ""),
        ("GET", "/api/onezero/retroactive/scan", ""),
        ("GET", "/api/simulate/portfolio/{tax_year}", ""),
        ("POST", "/api/simulate/unit", ""),
        ("POST", "/api/simulate/employee", ""),
        ("POST", "/api/simulate/onezero", ""),
        ("GET", "/api/ingestion/{tax_year}", "ingestion"),
        ("POST", "/api/ingestion/{tax_year}/exceptions/{exception_id}/resolve", "resolve"),
        ("GET", "/api/ingestion/{tax_year}/rows", "source_rows"),
        ("GET", "/api/proximity/{tax_year}", "proximity"),
        ("GET", "/api/scope", "scope"),
        ("GET", "/api/scope/client/{account_id}", "client_scope"),
        ("GET", "/api/v2/clients/{client_id}/units", "units"),
        ("GET", "/api/v2/clients/{client_id}/units/{unit_id}", "unit"),
        ("GET", "/api/v2/employees/{record_token}", "employee"),
        ("POST", "/api/employee/drill", "drill"),
    ];

    /// <inheritdoc />
    public void Map(IEndpointRouteBuilder endpoints)
    {
        ArgumentNullException.ThrowIfNull(endpoints);
        var defaults = new ReadEndpointFallbacks(endpoints);
        foreach (var operation in Operations)
        {
            defaults.MapMethods(operation.Path, [operation.Method], (HttpContext context, IMediator mediator,
                IApiPrincipalAccessor principals) => Execute(context, mediator, principals, operation));
        }
        endpoints.DataSources.Add(defaults);
    }

    private static async Task<IResult> Execute(HttpContext context, IMediator mediator, IApiPrincipalAccessor principals,
        (string Method, string Path, string View) operation)
    {
        try
        {
            var parameters = context.Request.Query.ToDictionary(item => item.Key, item => item.Value.LastOrDefault(), StringComparer.Ordinal);
            foreach (var item in context.Request.RouteValues)
            {
                parameters[item.Key] = Convert.ToString(item.Value, CultureInfo.InvariantCulture);
            }
            var principal = principals.Current ?? ApiPrincipal.Anonymous;
            var args = new ReadArguments(parameters, RequestValidator.Body(context));
            if (operation.View == "review")
            {
                parameters["reviewer"] = principal.Attributed(args.Text("reviewer"), "Reviewer");
            }
            var request = Request(operation, args, principal);
            var response = await mediator.Send(request, context.RequestAborted).ConfigureAwait(false);
            return Results.Json(ReadValues.Transport(response));
        }
        catch (ReadRefusalException exception)
        {
            return ApiErrors.Detail(exception.StatusCode, exception.Message);
        }
        catch (Exception exception) when (exception is ClientRunNotAvailable or NoPayrollForClient)
        {
            return ApiErrors.Detail(404, "The selected source or accepted run cannot answer this client-program-year.");
        }
        catch (ProgramNotRunnableError)
        {
            return ApiErrors.Detail(409, "Choose an authored, calculable program.");
        }
        catch (Exception exception) when (exception is ProgramStateConflict or PyValueError or ArgumentException)
        {
            return ApiErrors.Detail(422, "Invalid calculation selection or input.");
        }
        catch (Exception exception) when (exception is FileNotFoundException or PayrollDatasetNotGenerated)
        {
            return ApiErrors.Dependency("payroll_or_statute", "required data is not available", "Configure the source and author the selected year pack.");
        }
    }

    private static IRequest<object> Request((string Method, string Path, string View) operation, ReadArguments args, ApiPrincipal principal) =>
        operation.View switch
        {
            "me" => new IdentityReadQuery(),
            "scope" => new ScopeReadQuery(args),
            "client_scope" => new ScopeReadQuery(args, true),
            "ingestion" => new IngestionReadQuery(args),
            "source_rows" => new IngestionReadQuery(args, true),
            "resolve" => new ResolveIngestionException(args, principal.Attributed(args.Text("reviewer") ?? args.Text("actor"), "Reviewer")),
            "review" => new ReviewOneZeroEmployee(args),
            "" => new CalculateViewQuery($"{operation.Method} {operation.Path}", args),
            _ => new StoredReadQuery(operation.View, args),
        };
}
