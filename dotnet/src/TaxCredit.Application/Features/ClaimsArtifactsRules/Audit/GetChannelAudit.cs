using System.Globalization;
using TaxCredit.Application.Messaging;
using TaxCredit.Application.Ports.Auth;
using TaxCredit.Application.Ports.Persistence;
using TaxCredit.Domain.Numerics;

namespace TaxCredit.Application.Features.ClaimsArtifactsRules.Audit;

/// <summary>Reads one person's metadata trail, never the channel agent's own history.</summary>
public sealed record GetChannelAudit(string UserOid, string? Since, string? Until, string? Tool, int Limit, ApiPrincipal Principal) : IQuery<object>;

internal sealed class GetChannelAuditHandler(IChannelAuditRepository repository) : IRequestHandler<GetChannelAudit, object>
{
    public ValueTask<object> Handle(GetChannelAudit request, CancellationToken cancellationToken)
    {
        if (request.Principal.IsAgent) { throw new FeatureRefusalException(403, "The channel agent may not read the channel audit trail."); }
        if (string.IsNullOrWhiteSpace(request.UserOid) || request.Limit is < 1 or > 500) { throw new FeatureRefusalException(422, "user_oid is required; limit must be 1..500."); }
        var events = repository.ForUser(request.UserOid, Parse(request.Since), Parse(request.Until), request.Tool, request.Limit)
            .Select(e => Event(e.Fields)).ToArray();
        var entries = events.OrderBy(e => Moment(e["occurred_at"])).ThenBy(e => Convert.ToInt64(e["event_seq"], CultureInfo.InvariantCulture))
            .GroupBy(e => (string)e["audit_id"]!, StringComparer.Ordinal).Select(Collapse)
            .OrderByDescending(e => Moment(e["begun_at"])).ToArray();
        return ValueTask.FromResult<object>(new PyDict().Add("user_oid", request.UserOid).Add("events", events).Add("entries", entries).Add("limit", request.Limit));
    }

    private static PyDict Event(IReadOnlyDictionary<string, object?> fields)
    {
        var row = new PyDict();
        foreach (var (key, value) in fields)
        {
            row.Add(key, key == "is_deterministic_path" && value is not null ? Convert.ToBoolean(value, CultureInfo.InvariantCulture) : FeatureValues.Wire(value));
        }
        return row;
    }

    private static PyDict Collapse(IGrouping<string, PyDict> group)
    {
        var rows = group.ToArray();
        var last = rows[^1];
        var closing = rows.LastOrDefault(e => e["phase"] is "end" or "single");
        return new PyDict().Add("audit_id", group.Key).Add("outcome", closing?["outcome"] ?? "pending")
            .Add("begun_at", rows[0]["occurred_at"]).Add("finished_at", closing?["occurred_at"])
            .Add("tool_name", last["tool_name"]).Add("action_kind", last["action_kind"]).Add("user_oid", last["user_oid"])
            .Add("client_id", last["client_id"]).Add("tax_year", last["tax_year"]).Add("correlation_id", last["correlation_id"]).Add("events", rows.Length);
    }

    private static DateTimeOffset Moment(object? value) => DateTimeOffset.Parse(
        value is PyDateTime date ? date.IsoFormat() : Convert.ToString(value, CultureInfo.InvariantCulture)!,
        CultureInfo.InvariantCulture, DateTimeStyles.AssumeUniversal);

    private static PyDateTime? Parse(string? text)
    {
        if (text is null) { return null; }
        if (!DateTimeOffset.TryParse(text, CultureInfo.InvariantCulture, DateTimeStyles.AssumeUniversal, out var date))
        {
            throw new FeatureRefusalException(422, "Invalid ISO date-time.");
        }
        return new PyDateTime(DateOnly.FromDateTime(date.DateTime), date.Hour, date.Minute, date.Second,
            (int)(date.Ticks % TimeSpan.TicksPerSecond / 10), (int)date.Offset.TotalMinutes);
    }
}
