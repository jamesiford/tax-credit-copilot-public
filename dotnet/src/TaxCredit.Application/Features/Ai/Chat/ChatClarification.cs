using TaxCredit.Application.Features.Ai.Streams;

namespace TaxCredit.Application.Features.Ai.Chat;

internal static class ChatClarification
{
    internal static IEnumerable<AiFrame> Frames(ChatQuery query, ChatReferent referent, IReadOnlyList<ChatClient> clients)
    {
        var choices = referent.Candidates.Select(id =>
        {
            var client = clients.Single(c => c.ClientId == id);
            return new
            {
                client_id = id,
                name = client.Name,
                tax_year = query.ClientId == id && query.TaxYear is not null ? query.TaxYear : client.TaxYear
            };
        }).ToArray();
        var names = choices.Select(c => c.name).ToArray();
        var listed = names.Length switch
        {
            0 => "a client",
            1 => names[0],
            _ => string.Join(", ", names[..^1]) + " or " + names[^1]
        };
        var text = referent.Reason == "names a different client from the one this chat is about"
            ? $"You asked about **{names[0]}**, but this chat is about **{names[1]}**. Which one should I answer for?"
            : names.Length == 1
                ? $"Do you mean **{names[0]}**? No client is selected on the page, and I won't guess \u2014 confirm and I'll answer for them."
                : referent.Reason == "no client is selected"
                    ? $"Which client do you mean \u2014 {listed}? No client is selected on the page, and I won't guess."
                    : $"Which client do you mean \u2014 {listed}? I answer about one client at a time, and I won't pick one for you.";
        yield return new("status", new { phase = 1, echo = query.Message, clarify = true, reason = referent.Reason });
        yield return new("agent_start", new { agent = "OrchestratorAgent" });
        yield return new("token", new { agent = "OrchestratorAgent", content = text });
        yield return new("clarify", new { message = query.Message, reason = referent.Reason, choices });
        yield return new("agent_end", new { agent = "OrchestratorAgent" });
    }

    internal static IEnumerable<AiFrame> MissingScope(ChatQuery query)
    {
        const string text = "This answer needs the selected client and tax year from the page. I will not guess against the default tenant or silently answer for the wrong scope.";
        yield return new("status", new { phase = 1, echo = query.Message, scope_missing = true, note = text });
        yield return new("agent_start", new { agent = "OrchestratorAgent" });
        yield return new("token", new { agent = "OrchestratorAgent", content = text });
        yield return new("agent_end", new { agent = "OrchestratorAgent" });
    }
}
