namespace TaxCredit.Orchestrator.Boundary;

/// <summary>Configured first-source precedence refuses invalid assertions instead of downgrading trust.</summary>
public static class IdentityResolver
{
    /// <summary>Flatten platform signals last so caller headers cannot override the platform subject.</summary>
    public static IReadOnlyDictionary<string, string> SignalsOf(IdentityContext context)
    {
        ArgumentNullException.ThrowIfNull(context);
        var signals = new Dictionary<string, string>(StringComparer.Ordinal);
        foreach (var (key, value) in context.ClientHeaders ?? new Dictionary<string, string>())
        {
            signals[key.ToLowerInvariant()] = value;
        }
        Add("x-ms-original-subject-oid", context.OriginalSubject?.Oid);
        Add("x-ms-original-subject-tid", context.OriginalSubject?.Tid);
        Add("x-ms-original-subject-idtype", context.OriginalSubject?.IdType);
        Add("x-agent-user-id", context.AgentUserId);
        return signals;

        void Add(string name, string? value)
        {
            if (!string.IsNullOrEmpty(value))
            {
                signals[name] = value;
            }
        }
    }

    /// <summary>A response identifier is not a conversation; only a stable conversation/chain may hold state.</summary>
    public static string? ConversationOf(IdentityContext context)
    {
        ArgumentNullException.ThrowIfNull(context);
        return !string.IsNullOrEmpty(context.ConversationId) ? context.ConversationId : context.ConversationChainId;
    }

    /// <summary>Resolve without credentials, SDK objects, defaults, network access or mutable caller state.</summary>
    public static IdentityResolution Resolve(IdentityContext context, IdentityOptions settings)
    {
        ArgumentNullException.ThrowIfNull(settings);
        var signals = SignalsOf(context);
        var conversation = ConversationOf(context);
        if (string.IsNullOrWhiteSpace(conversation))
        {
            return Refuse("no conversation id");
        }
        if (conversation.Length > 256 || conversation.Any(char.IsControl))
        {
            return Refuse("invalid conversation id");
        }
        foreach (var source in settings.Sources)
        {
            var found = Read(source, signals);
            if (found is null)
            {
                continue;
            }
            var (oid, tenant) = found.Value;
            if (!Guid.TryParseExact(oid, "D", out var objectId))
            {
                return Refuse($"{source} gave an object id that is not a GUID");
            }
            if (tenant is not null && !string.Equals(tenant, settings.TenantId, StringComparison.OrdinalIgnoreCase))
            {
                return Refuse($"{source} names a different tenant");
            }
            var name = Clean(signals, "x-client-acting-user-name") ?? "(name not provided)";
            if (name.Any(char.IsControl))
            {
                return Refuse("invalid display name");
            }
            return new IdentityResolution(new ActingIdentity(objectId.ToString("D"), name, settings.TenantId,
                settings.Channel, conversation, CorrelationOf(context.ResponseId), source));
        }
        return Refuse("no configured source carried an Entra object id: " + string.Join(", ", settings.Sources));
    }

    /// <summary>Only ASCII safe correlation characters survive; an absent identifier is newly attributed.</summary>
    public static string CorrelationOf(string? responseId)
    {
        var safe = new string((responseId ?? "").Where(character => char.IsAsciiLetterOrDigit(character) ||
            character is '.' or '_' or '-').Take(64).ToArray());
        return safe.Length == 0 ? Guid.NewGuid().ToString("N") : safe;
    }

    private static (string Oid, string? Tenant)? Read(string source, IReadOnlyDictionary<string, string> signals)
    {
        var header = source switch
        {
            "original-subject" => "x-ms-original-subject-oid",
            "platform" => "x-ms-user-identity",
            "client-headers" => "x-client-acting-user-oid",
            "agent-user-id" => "x-agent-user-id",
            _ => throw new InvalidOperationException("Unrecognized configured identity source."),
        };
        var oid = Clean(signals, header);
        if (oid is null || source == "agent-user-id" && !Guid.TryParseExact(oid, "D", out _))
        {
            return null;
        }
        return (oid, source switch
        {
            "original-subject" => Clean(signals, "x-ms-original-subject-tid"),
            "agent-user-id" => null,
            _ => Clean(signals, "x-client-tenant"),
        });
    }

    private static string? Clean(IReadOnlyDictionary<string, string> signals, string name)
    {
        var text = signals.TryGetValue(name, out var value) ? value.Trim() : "";
        return text.Length == 0 ? null : text[..Math.Min(text.Length, 256)];
    }

    private static IdentityResolution Refuse(string reason) => new(new IdentityRefusal(reason));
}
