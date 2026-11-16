using TaxCredit.Application.Ports.Sources;
using TaxCredit.Domain.Pipeline;

namespace TaxCredit.Application.Features.Ai.Chat;

/// <summary>Preserves the application's fixture display name without teaching transport adapters presentation copy.</summary>
public sealed class AiClientBook(ISourceReader source, IEnumerable<IClientPayrollSource> payrollSources)
{
    /// <summary>A fixture's portfolio label is application metadata; real account names remain source facts.</summary>
    public IReadOnlyList<SourceAccount> Entries()
    {
        var fixture = payrollSources.Select(p => p.FixtureAccountId).FirstOrDefault(id => id is not null);
        return source.ListAccounts().Select(account => account.AccountId == fixture
            ? account with { Name = "Reference Dataset Client" } : account).ToArray();
    }
}
