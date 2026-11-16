using System.Text.RegularExpressions;
using TaxCredit.Application.Features.Ai.Streams;

namespace TaxCredit.Application.Features.Ai.Chat;

/// <summary>A source-book entry with a concrete, application-selected button year.</summary>
public sealed record ChatClient(long ClientId, string Name, int? TaxYear);

/// <summary>A clarification never silently changes the selected client.</summary>
public sealed record ChatReferent(bool Clarify, IReadOnlyList<long> Candidates, string Reason);

/// <summary>The book owner can provide priority-cell years without coupling chat to HTTP routes.</summary>
public interface IChatClientSource
{
    /// <summary>Only authorized clients may be offered as choices.</summary>
    ValueTask<IReadOnlyList<ChatClient>> ReadAsync(CancellationToken cancellationToken);
}

/// <summary>History identifies a referent, not a population or a numeric fact.</summary>
public static partial class ChatReferents
{
    private static readonly HashSet<string> Generic = new(StringComparer.Ordinal)
    {
        "the", "first", "national", "american", "united", "general", "global", "north", "south",
        "east", "west", "new", "great", "account", "client"
    };

    /// <summary>Preserves the Python precedence for conflicting names, history and page scope.</summary>
    public static ChatReferent Resolve(ChatQuery request, IReadOnlyList<ChatClient> clients)
    {
        ArgumentNullException.ThrowIfNull(request);
        ArgumentNullException.ThrowIfNull(clients);
        if (request.ClientConfirmed) { return new(false, [], ""); }
        var named = Named(request.Message, clients);
        var scope = clients.Any(c => c.ClientId == request.ClientId) ? request.ClientId : null;
        if (named.Length >= 2) { return new(true, named, "names more than one client"); }
        if (named.Length == 1)
        {
            if (scope == named[0]) { return new(false, [], ""); }
            return scope is { } id
                ? new(true, [named[0], id], "names a different client from the one this chat is about")
                : new(true, named, "no client is selected");
        }
        var earlier = (request.History ?? []).Reverse().Select(t => Named(t.Text, clients)).FirstOrDefault(n => n.Length > 0) ?? [];
        if (ReferentPattern().IsMatch(request.Message))
        {
            if (earlier.Length > 0 && !(earlier.Length == 1 && earlier[0] == scope))
            {
                return new(true, earlier.Concat(scope is { } id ? [id] : Array.Empty<long>()).Distinct().ToArray(), "does not say which client it means");
            }
            return scope is null
                ? new(true, clients.Select(c => c.ClientId).ToArray(), "does not say which client it means")
                : new(false, [], "");
        }
        return scope is null
            ? new(true, earlier.Length > 0 ? earlier : clients.Select(c => c.ClientId).ToArray(), "no client is selected")
            : new(false, [], "");
    }

    private static long[] Named(string text, IReadOnlyList<ChatClient> clients)
    {
        var found = new List<(int Position, long Id)>();
        foreach (var client in clients)
        {
            var full = client.Name.Trim().ToLowerInvariant();
            if (full.Length == 0) { continue; }
            var first = full.Split(' ', StringSplitOptions.RemoveEmptyEntries)[0];
            var aliases = first.Length >= 4 && first != full && !Generic.Contains(first) ? new[] { full, first } : [full];
            var positions = aliases.Select(a => Regex.Match(text, @"\b" + Regex.Escape(a) + @"\b", RegexOptions.IgnoreCase | RegexOptions.CultureInvariant))
                .Where(m => m.Success).Select(m => m.Index).ToArray();
            if (positions.Length > 0) { found.Add((positions.Min(), client.ClientId)); }
        }
        return found.OrderBy(f => f.Position).ThenBy(f => f.Id).Select(f => f.Id).ToArray();
    }

    [GeneratedRegex(@"\b(their|theirs|them|they|they'?re|this client|that client|this one|that one|these|those|the client|same client)\b", RegexOptions.IgnoreCase | RegexOptions.CultureInvariant)]
    private static partial Regex ReferentPattern();
}
