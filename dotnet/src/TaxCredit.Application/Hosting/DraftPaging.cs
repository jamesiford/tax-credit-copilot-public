using System.Numerics;
using TaxCredit.Domain.Programs;

namespace TaxCredit.Application.Hosting;

/// <summary>Paging quantities are not storage identities; arbitrarily large offsets are legitimate empty pages.</summary>
public static class DraftPaging
{
    /// <summary>Keeps the real unfiltered total without narrowing a huge integer or allocating an offset-sized collection.</summary>
    public static (IReadOnlyList<ProgramDraft> Items, long Total) ListPage(
        this IProgramDraftRepository repository, string? status, long limit, BigInteger offset)
    {
        ArgumentNullException.ThrowIfNull(repository);
        ArgumentOutOfRangeException.ThrowIfNegative(offset);
        return repository.ListDrafts(status, limit, offset > long.MaxValue ? long.MaxValue : (long)offset);
    }
}
