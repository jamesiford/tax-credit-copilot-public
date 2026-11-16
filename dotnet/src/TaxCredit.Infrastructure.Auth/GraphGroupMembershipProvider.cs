using System.Net;
using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Text.Json;
using TaxCredit.Application.Ports.Auth;

namespace TaxCredit.Infrastructure.Auth;

/// <summary>Graph transport and credentials are fakeable; failures expose classifications, never upstream payloads.</summary>
public sealed class GraphGroupMembershipProvider(HttpClient client, IAuthAccessTokenProvider tokens, TimeProvider? clock = null) : IGroupMembershipProvider
{
    private readonly TimeProvider _clock = clock ?? TimeProvider.System;
    private readonly object _refreshGate = new();
    private long? _lastRefresh;
    /// <summary>Gateway delegated scopes are not accepted for Graph or API trust.</summary>
    public const string Scope = "https://graph.microsoft.com/.default";

    /// <inheritdoc />
    public async ValueTask<bool> IsMemberAsync(string userOid, string groupId, CancellationToken cancellationToken = default)
    {
        if (!Guid.TryParse(userOid, out var user) || !Guid.TryParse(groupId, out var group))
        {
            throw new ArgumentException("Group membership needs GUID identifiers.");
        }
        using var deadline = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        deadline.CancelAfter(TimeSpan.FromSeconds(5));
        try { return await AskAsync(user, group, deadline.Token).ConfigureAwait(false); }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested) { throw; }
        catch (OperationCanceledException) { throw new AuthDependencyException("graph_timeout"); }
        catch (AuthDependencyException) { throw; }
        catch (Exception ex) when (ex is JsonException or InvalidOperationException) { throw new AuthDependencyException("graph_malformed"); }
        catch (Exception) { throw new AuthDependencyException("graph_unavailable"); }
    }

    private async ValueTask<bool> AskAsync(Guid user, Guid group, CancellationToken cancellationToken)
    {
        for (var attempt = 0; attempt < 2; attempt++)
        {
            using var request = new HttpRequestMessage(HttpMethod.Post, $"https://graph.microsoft.com/v1.0/users/{user}/checkMemberGroups");
            var token = await tokens.GetTokenAsync(Scope, cancellationToken).ConfigureAwait(false);
            if (string.IsNullOrWhiteSpace(token)) { throw new AuthDependencyException("graph_credential_unavailable"); }
            request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", token);
            request.Content = JsonContent.Create(new { groupIds = new[] { group.ToString() } });
            using var response = await client.SendAsync(request, HttpCompletionOption.ResponseHeadersRead, cancellationToken).ConfigureAwait(false);
            if (attempt == 0 && await IsStaleDenialAsync(response, cancellationToken).ConfigureAwait(false) && Invalidate()) { continue; }
            if (!response.IsSuccessStatusCode) { throw new AuthDependencyException("graph_refused"); }
            using var json = JsonDocument.Parse(await ReadBoundedAsync(response, cancellationToken).ConfigureAwait(false));
            return Membership(json.RootElement, group);
        }
        return false;
    }

    private static bool Membership(JsonElement json, Guid group)
    {
        if (json.ValueKind != JsonValueKind.Object || json.EnumerateObject().GroupBy(p => p.Name, StringComparer.Ordinal).Any(g => g.Count() > 1)
            || !json.TryGetProperty("value", out var values) || values.ValueKind != JsonValueKind.Array ||
            values.EnumerateArray().Any(v => v.ValueKind != JsonValueKind.String || !Guid.TryParse(v.GetString(), out _)))
        {
            throw new JsonException("Invalid group response.");
        }
        return values.EnumerateArray().Any(v => Guid.Parse(v.GetString()!) == group);
    }

    private bool Invalidate()
    {
        lock (_refreshGate)
        {
            var now = _clock.GetTimestamp();
            if (_lastRefresh.HasValue && _clock.GetElapsedTime(_lastRefresh.Value, now) < TimeSpan.FromMinutes(1)) { return false; }
            if (!tokens.Invalidate(Scope)) { return false; }
            _lastRefresh = now;
            return true;
        }
    }

    private static async ValueTask<bool> IsStaleDenialAsync(HttpResponseMessage response, CancellationToken cancellationToken)
    {
        if (response.StatusCode == HttpStatusCode.Unauthorized) { return true; }
        if (response.StatusCode != HttpStatusCode.Forbidden) { return false; }
        try
        {
            using var json = JsonDocument.Parse(await ReadBoundedAsync(response, cancellationToken).ConfigureAwait(false));
            if (json.RootElement.ValueKind != JsonValueKind.Object || !json.RootElement.TryGetProperty("error", out var error)) { return false; }
            var text = error.ToString();
            return text.Contains("authorization_requestdenied", StringComparison.OrdinalIgnoreCase)
                || text.Contains("insufficient privileges", StringComparison.OrdinalIgnoreCase);
        }
        catch (JsonException) { return false; }
    }

    private static async ValueTask<ReadOnlyMemory<byte>> ReadBoundedAsync(HttpResponseMessage response, CancellationToken cancellationToken)
    {
        await using var stream = await response.Content.ReadAsStreamAsync(cancellationToken).ConfigureAwait(false);
        var bytes = new byte[65_537];
        var count = 0;
        int read;
        while (count < bytes.Length && (read = await stream.ReadAsync(bytes.AsMemory(count), cancellationToken).ConfigureAwait(false)) > 0) { count += read; }
        if (count == bytes.Length) { throw new JsonException("Group response exceeds bound."); }
        return bytes.AsMemory(0, count);
    }

    /// <summary>Host reset forgets credential-refresh cooldown without changing a person's entitlement.</summary>
    public void Reset()
    {
        lock (_refreshGate) { _lastRefresh = null; }
    }
}
