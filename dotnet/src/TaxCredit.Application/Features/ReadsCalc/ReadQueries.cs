using Microsoft.Extensions.DependencyInjection;
using TaxCredit.Application.Features.ReadsCalc.Ingestion;
using TaxCredit.Application.Features.ReadsCalc.Scope;
using TaxCredit.Application.Features.ReadsCalc.Stored;
using TaxCredit.Application.Messaging;
using TaxCredit.Application.Ports.Auth;
using TaxCredit.Application.Ports.Contract;

namespace TaxCredit.Application.Features.ReadsCalc;

/// <summary>Stored accepted-result views share transport selection but never replay the payroll engine.</summary>
public sealed record StoredReadQuery(string View, ReadArguments Arguments) : IQuery<object>;

/// <summary>Dispatches accepted-result reads through the mediator pipeline.</summary>
public sealed class StoredReadHandler(IServiceScopeFactory scopes) : IRequestHandler<StoredReadQuery, object>
{
    /// <inheritdoc />
    public ValueTask<object> Handle(StoredReadQuery request, CancellationToken cancellationToken)
    {
        ArgumentNullException.ThrowIfNull(request);
        cancellationToken.ThrowIfCancellationRequested();
        return ValueTask.FromResult(request.View switch
        {
            "eligibility" => ReadHandlerScope.Execute<StoredEligibility>(scopes, view => view.Read(request.Arguments)),
            "matrix" => ReadHandlerScope.Execute<StoredMatrix>(scopes, view => view.Read(request.Arguments)),
            "units" => ReadHandlerScope.Execute<StoredUnits>(scopes, view => view.Page(request.Arguments)),
            "unit" => ReadHandlerScope.Execute<StoredUnits>(scopes, view => view.Detail(request.Arguments)),
            "employee" => ReadHandlerScope.Execute<StoredEmployees>(scopes, view => view.Detail(request.Arguments)),
            "drill" => ReadHandlerScope.Execute<StoredEmployees>(scopes, view => view.Drill(request.Arguments)),
            "proximity" => ReadHandlerScope.Execute<ProximityViews>(scopes, view => view.Cohort(request.Arguments)),
            "progress" => ReadHandlerScope.Execute<ProximityViews>(scopes, view => view.Progress(request.Arguments)),
            _ => throw new InvalidOperationException("Unknown accepted-result view."),
        });
    }
}

/// <summary>Source dimensions, independently of whether a client has been assessed.</summary>
public sealed record ScopeReadQuery(ReadArguments Arguments, bool Client = false) : IQuery<object>;

/// <summary>Queries the source catalogue and materialized statutory years.</summary>
public sealed class ScopeReadHandler(IServiceScopeFactory scopes) : IRequestHandler<ScopeReadQuery, object>
{
    /// <inheritdoc />
    public ValueTask<object> Handle(ScopeReadQuery request, CancellationToken cancellationToken)
    {
        ArgumentNullException.ThrowIfNull(request);
        cancellationToken.ThrowIfCancellationRequested();
        return ValueTask.FromResult(ReadHandlerScope.Execute<ScopeViews>(scopes,
            views => request.Client ? views.Client(request.Arguments.Client()!.Value) : views.Options()));
    }
}

/// <summary>Ingestion views inspect the selected source and its persisted human annotations.</summary>
public sealed record IngestionReadQuery(ReadArguments Arguments, bool Rows = false) : IQuery<object>;

/// <summary>Dispatches overview and source browsing without silently selecting another dataset.</summary>
public sealed class IngestionReadHandler(IServiceScopeFactory scopes) : IRequestHandler<IngestionReadQuery, object>
{
    /// <inheritdoc />
    public ValueTask<object> Handle(IngestionReadQuery request, CancellationToken cancellationToken)
    {
        ArgumentNullException.ThrowIfNull(request);
        cancellationToken.ThrowIfCancellationRequested();
        return ValueTask.FromResult(ReadHandlerScope.Execute<IngestionViews>(scopes,
            views => request.Rows ? views.Rows(request.Arguments) : views.Overview(request.Arguments)));
    }
}

/// <summary>Current verified identity, never an identity supplied in a request body.</summary>
public sealed record IdentityReadQuery : IQuery<object>;

/// <summary>Reports the shared authentication adapter's principal without private context.</summary>
public sealed class IdentityReadHandler(IApiPrincipalAccessor principals, IRuntimeConfiguration configuration) : IRequestHandler<IdentityReadQuery, object>
{
    /// <inheritdoc />
    public ValueTask<object> Handle(IdentityReadQuery request, CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        var principal = principals.Current ?? ApiPrincipal.Anonymous;
        return ValueTask.FromResult<object>(ReadValues.Map(("authenticated", principal.Authenticated),
            ("auth_mode", configuration.Get("AUTH_MODE") ?? "entra"), ("upn", principal.Upn), ("oid", principal.Oid),
            ("name", principal.Name), ("roles", principal.Roles ?? []), ("principal_type", principal.PrincipalType),
            ("acting_for", principal.ActingFor is null ? null : new
            {
                oid = principal.ActingFor.Oid,
                name = principal.ActingFor.Name,
                upn = principal.ActingFor.Upn,
                assurance = principal.ActingFor.Assurance,
                channel = principal.ActingFor.Channel,
            })));
    }
}
