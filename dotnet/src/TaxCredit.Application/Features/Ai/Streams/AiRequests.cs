using TaxCredit.Application.Messaging;

namespace TaxCredit.Application.Features.Ai.Streams;

/// <summary>History supplies referents and routing context, never trusted figures.</summary>
public sealed record ChatTurn(string Role, string Text);

/// <summary>The portal's selected scope is explicit; there is no default client.</summary>
public sealed record ChatQuery(
    string Message, string? State = null, long? ClientId = null, int? TaxYear = null,
    string Method = "min_max", IReadOnlyList<ChatTurn>? History = null, bool ClientConfirmed = false)
    : IQuery<IAsyncEnumerable<AiFrame>>;

/// <summary>Only the four routed pages have summaries.</summary>
public sealed record SummaryQuery(
    string Page, long? ClientId = null, int? TaxYear = null, string State = "GA",
    string Method = "min_max", string? WorksiteId = null, int? Month = null, string? RecordToken = null)
    : IQuery<IAsyncEnumerable<AiFrame>>
{
    /// <summary>Opaque handles must not appear through an accidental diagnostic.</summary>
    public override string ToString() => $"SummaryQuery({Page})";
}
