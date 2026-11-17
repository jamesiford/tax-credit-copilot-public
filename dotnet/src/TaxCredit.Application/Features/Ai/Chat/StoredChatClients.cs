using System.Globalization;
using TaxCredit.Application.Features.Ai.Briefs;
using TaxCredit.Application.Ports.Auth;
using TaxCredit.Application.Ports.Persistence;

namespace TaxCredit.Application.Features.Ai.Chat;

/// <summary>Priority-cell years belong to the book owner; a latest run is an explicitly narrower fallback.</summary>
public sealed class StoredChatClients(AiClientBook sources, IGoldReadPort gold,
    IApiPrincipalAccessor principals, IClientAuthorizer authorizer) : IChatClientSource
{
    /// <inheritdoc />
    public async ValueTask<IReadOnlyList<ChatClient>> ReadAsync(CancellationToken cancellationToken)
    {
        var clients = new List<ChatClient>();
        foreach (var account in sources.Entries())
        {
            if (!await authorizer.IsAuthorizedAsync(principals.Current ?? ApiPrincipal.Anonymous, account.AccountId, cancellationToken).ConfigureAwait(false)) { continue; }
            var run = gold.LatestRun(account.AccountId);
            int? year = run?.GetValueOrDefault("tax_year") is { } held ? Convert.ToInt32(held, CultureInfo.InvariantCulture) : null;
            clients.Add(new(account.AccountId, account.Name, year));
        }
        return clients;
    }
}

/// <summary>Only authored pack metadata contributes caveats.</summary>
public sealed class StoredPageScope(AiClientBook sources, TaxCredit.Domain.Programs.RuleLibrary rules) : IPageScope
{
    /// <inheritdoc />
    public string ClientName(long clientId) => sources.Entries().FirstOrDefault(c => c.AccountId == clientId)?.Name
        ?? "Account " + clientId.ToString(CultureInfo.InvariantCulture);

    /// <inheritdoc />
    public IReadOnlyList<int> PlaceholderYears(string state)
    {
        var program = rules.ProgramsForState(state).SingleOrDefault();
        if (program is null) { return []; }
        return rules.AuthoredYears(program.PackFile).Where(year =>
            rules.ResolveStatutoryFloors(program.Code, year).PrototypeVerify)
            .Select(year => checked((int)year)).ToArray();
    }
}
