namespace TaxCredit.Application.Features.Ai.Streams;

/// <summary>An application event without HTTP framing or buffering.</summary>
public sealed record AiFrame(string Event, object Data);

/// <summary>A controlled, safe failure of a trusted fact read.</summary>
public sealed class AiFactException(string detail, string dependency = "page_facts") : Exception(detail)
{
    /// <summary>The owning application collaborator, not a server or connection name.</summary>
    public string Dependency { get; } = dependency;
}
