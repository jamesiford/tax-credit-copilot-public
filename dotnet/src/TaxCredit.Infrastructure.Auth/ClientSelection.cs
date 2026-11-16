using System.Globalization;
using System.Text;
using System.Text.Json;
using TaxCredit.Application.Ports.Auth;

namespace TaxCredit.Infrastructure.Auth;

/// <summary>Normalization is independent of transport; validation errors remain the handler's responsibility.</summary>
public static class ClientSelection
{
    /// <summary>Extracts path/query/body scalars and top-level/nested scope lists, deduplicated in authorization order.</summary>
    public static IReadOnlyList<long> Extract(
        IEnumerable<KeyValuePair<string, object?>>? path = null,
        IEnumerable<KeyValuePair<string, string?>>? query = null, JsonElement? body = null)
    {
        var result = new SortedSet<long>();
        foreach (var pair in path ?? [])
        {
            if (IsKey(pair.Key))
            {
                Add(result, pair.Value);
            }
        }

        foreach (var pair in query ?? [])
        {
            if (IsKey(pair.Key))
            {
                Add(result, pair.Value);
            }
        }

        if (body is { ValueKind: JsonValueKind.Object } obj)
        {
            foreach (var key in new[] { "client_id", "account_id" })
            {
                if (obj.TryGetProperty(key, out var value))
                {
                    Add(result, value);
                }
            }

            Lists(result, obj);
            if (obj.TryGetProperty("scope", out var scope) && scope.ValueKind == JsonValueKind.Object)
            {
                Lists(result, scope);
            }
        }
        return result.ToArray();
    }

    private static bool IsKey(string key) => key is "client_id" or "account_id";
    private static void Lists(SortedSet<long> result, JsonElement body)
    {
        foreach (var key in new[] { "client_ids", "account_ids" })
        {
            if (body.TryGetProperty(key, out var values) && values.ValueKind == JsonValueKind.Array)
            {
                foreach (var value in values.EnumerateArray())
                {
                    Add(result, value);
                }
            }
        }
    }

    private static void Add(SortedSet<long> result, object? value)
    {
        switch (value)
        {
            case int i: result.Add(i); break;
            case long l: result.Add(l); break;
            case string text:
                var normalized = new StringBuilder();
                foreach (var rune in text.Trim().EnumerateRunes())
                {
                    if (Rune.GetUnicodeCategory(rune) != UnicodeCategory.DecimalDigitNumber) { return; }
                    normalized.Append((char)('0' + (int)Rune.GetNumericValue(rune)));
                }
                if (long.TryParse(normalized.ToString(), NumberStyles.None, CultureInfo.InvariantCulture, out var textId))
                {
                    result.Add(textId);
                }
                break;
            case JsonElement element when element.ValueKind == JsonValueKind.Number && element.TryGetInt64(out var id):
                // Decimal JSON numbers are not Python int client selections.
                if (!element.GetRawText().Contains('.', StringComparison.Ordinal) && !element.GetRawText().Contains('e', StringComparison.OrdinalIgnoreCase))
                {
                    result.Add(id);
                }

                break;
            case JsonElement element when element.ValueKind == JsonValueKind.String: Add(result, element.GetString()); break;
        }
    }
}

/// <summary>A copied fixed map cannot be mutated by a concurrent caller.</summary>
public sealed class AllowListClientAuthorizer : IClientAuthorizer
{
    private readonly Dictionary<string, HashSet<long>> _allowed;
    /// <summary>Client visibility always uses the original caller oid, not acting-user rights.</summary>
    public AllowListClientAuthorizer(IReadOnlyDictionary<string, IEnumerable<long>> allowed) =>
        _allowed = allowed.ToDictionary(p => p.Key, p => p.Value.ToHashSet(), StringComparer.Ordinal);
    /// <inheritdoc />
    public ValueTask<bool> IsAuthorizedAsync(ApiPrincipal principal, long clientId, CancellationToken cancellationToken = default) =>
        ValueTask.FromResult(_allowed.TryGetValue(principal.Oid ?? "", out var ids) && ids.Contains(clientId));
}

/// <summary>Preserves the internal-analyst default; deployments may replace this port with tenant binding.</summary>
public sealed class AllClientsAuthorizer : IClientAuthorizer
{
    /// <inheritdoc />
    public ValueTask<bool> IsAuthorizedAsync(ApiPrincipal principal, long clientId, CancellationToken cancellationToken = default) =>
        ValueTask.FromResult(true);
}

/// <summary>Batch handlers look up existence first, then filter before computing counters or paging.</summary>
public static class ClientVisibility
{
    /// <summary>Unknown and wholly invisible batches are both 404; artifact handlers record denial themselves.</summary>
    public static async ValueTask<IReadOnlyList<long>> VisibleBatchClientsAsync(
        IReadOnlyList<long>? existingClients, ApiPrincipal principal, IClientAuthorizer authorizer,
        CancellationToken cancellationToken = default)
    {
        if (existingClients is null)
        {
            throw new AuthRefusalException(404, "unknown_batch", "batch not found");
        }

        var visible = new List<long>();
        foreach (var id in existingClients)
        {
            if (await authorizer.IsAuthorizedAsync(principal, id, cancellationToken).ConfigureAwait(false))
            {
                visible.Add(id);
            }
        }

        if (visible.Count == 0)
        {
            throw new AuthRefusalException(404, "unknown_batch", "batch not found");
        }

        return visible;
    }
}
