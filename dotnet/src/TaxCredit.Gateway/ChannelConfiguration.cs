using System.Globalization;
using TaxCredit.Application.Ports.Contract;

namespace TaxCredit.Gateway;

internal static class ChannelConfiguration
{
    internal static void Validate(IRuntimeConfiguration settings)
    {
        _ = Rate(settings, 60);
        var fixture = settings.Get("CONTRACT_HOOKS") == "1";
        var tenant = settings.Get("TENANT_ID") ?? settings.Get("AUTH_TENANT_ID") ??
            (fixture ? "00000000-0000-0000-0000-0000000000aa" : "");
        if (!Guid.TryParseExact(tenant, "D", out _) ||
            string.IsNullOrWhiteSpace(settings.Get("GATEWAY_AUDIENCE") ?? (fixture ? "api://contract-gateway" : null)))
        { throw new InvalidOperationException("The gateway needs a tenant GUID and gateway audience."); }
        foreach (var app in Parts(settings.Get("CHANNEL_ALLOWED_CALLER_APP_IDS"), ','))
        {
            if (!Guid.TryParseExact(app, "D", out _))
            { throw new InvalidOperationException("A gateway caller application identifier is not a GUID."); }
        }
        var registered = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        foreach (var binding in Parts(settings.Get("CHANNEL_CALLER_CHANNELS"), ','))
        {
            var pair = binding.Split('=');
            if (pair is not [var app, var channels] || !Guid.TryParseExact(app, "D", out _) ||
                !registered.Add(app) || Parts(channels, '|') is not { Length: > 0 } allowed ||
                allowed.Any(channel => channel is not ("teams" or "m365-copilot")))
            { throw new InvalidOperationException("The gateway caller/channel registry is invalid."); }
        }
    }

    internal static int Rate(IRuntimeConfiguration settings, int fallback)
    {
        var raw = settings.Get("CHANNEL_RATE_LIMIT_PER_MINUTE");
        if (raw is null) { return fallback; }
        return int.TryParse(raw, NumberStyles.Integer, CultureInfo.InvariantCulture, out var rate) && rate is >= 1 and <= 6000 ? rate :
            throw new InvalidOperationException("The channel rate must be between 1 and 6000 calls per minute.");
    }

    private static string[] Parts(string? value, char separator) =>
        (value ?? "").Split(separator, StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries);
}
