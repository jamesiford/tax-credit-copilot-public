using System.Runtime.CompilerServices;
using System.Text;
using System.Text.Json;
using TaxCredit.Application.Features.Ai.Briefs;
using TaxCredit.Application.Features.Ai.Numeric;
using TaxCredit.Application.Ports.Ai;
using TaxCredit.Application.Ports.Auth;

namespace TaxCredit.Application.Features.Ai.Streams;

/// <summary>The request owns its upstream iterator until completion or disconnect.</summary>
public sealed class SummaryHandler(PageBriefBuilder briefs, IAiNarrator narrator,
    IApiPrincipalAccessor principals, IAiTelemetry telemetry)
{
    private const string Agent = "PageSummaryAgent";

    /// <summary>Defers execution so the HTTP request owns the complete stream lifetime.</summary>
    public ValueTask<IAsyncEnumerable<AiFrame>> Handle(SummaryQuery request, CancellationToken cancellationToken) =>
        ValueTask.FromResult(Stream(request, cancellationToken));

    private async IAsyncEnumerable<AiFrame> Stream(SummaryQuery query, [EnumeratorCancellation] CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        PageBrief? brief = null;
        string? failure = null;
        try { brief = await briefs.BuildAsync(query, cancellationToken).ConfigureAwait(false); }
        catch (AiFactException error) { failure = error.Message; }
#pragma warning disable CA1031 // A failed summary must leave the page usable; only a safe classification is exposed.
        catch (Exception error) when (error is not OperationCanceledException)
        {
            telemetry.Count("ai.page_brief_failed", scope: error.GetType().Name);
            failure = "The figures for this summary could not be read.";
        }
#pragma warning restore CA1031
        if (brief is null)
        {
            yield return new("error", new { detail = failure });
            yield return new("done", new { });
            yield break;
        }
        yield return new("brief", new { page = brief.Page, headline = brief.Headline, caveats = brief.Caveats });
        if (query.Page == "employee" || !narrator.Available([Agent]))
        {
            yield return Fallback(brief, "Copilot is not connected; these are the computed facts.");
            yield return new("done", new { });
            yield break;
        }
        var trusted = TrustedBrief(brief);
        var prompt = $"Summarise the {brief.Page} page for {brief.Subject}.\n\nJSON:\n{trusted.GetRawText()}";
        yield return new("agent_start", new { agent = Agent });
        var written = new StringBuilder();
        var upstreamFailed = false;
        await using (var events = ModelStream.Open(() => narrator.StreamAsync(Agent, prompt,
            principals.Current?.Actor ?? "anonymous", trusted, cancellationToken), telemetry, cancellationToken))
        {
            upstreamFailed = events is null;
            while (events is not null)
            {
                var next = await ModelStream.MoveAsync(events, telemetry, cancellationToken).ConfigureAwait(false);
                if (next.Failed) { upstreamFailed = true; break; }
                if (!next.HasValue) { break; }
                if (events.Current is TextDelta { Text.Length: > 0 } delta)
                {
                    written.Append(delta.Text);
                    yield return new("token", new { agent = Agent, content = delta.Text });
                }
            }
        }
        yield return new("agent_end", new { agent = Agent });
        if (upstreamFailed)
        {
            yield return Fallback(brief, "Copilot could not answer; these are the computed facts.");
        }
        else
        {
            yield return new("check", new { unsupported = PageFigureCheck.UnsupportedFigures(written.ToString(), trusted) });
        }
        yield return new("done", new { });
    }

    private static AiFrame Fallback(PageBrief brief, string note) => new("fallback", new { facts = brief.Facts, note });

    private static JsonElement TrustedBrief(PageBrief brief) => JsonSerializer.SerializeToElement(new
    {
        page = brief.Page,
        subject = brief.Subject,
        headline = brief.Headline,
        facts = brief.Facts.Where(f => !f.StartsWith("Employee ", StringComparison.Ordinal)).ToArray(),
        caveats = brief.Caveats,
        data = brief.Data
    });
}
