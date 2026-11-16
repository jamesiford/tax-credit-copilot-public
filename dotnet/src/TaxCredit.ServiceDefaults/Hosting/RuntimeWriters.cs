using TaxCredit.Application.Ports.Auth;
using TaxCredit.Application.Ports.Contract;
using TaxCredit.Application.Ports.Persistence;
using TaxCredit.Infrastructure.Auth;

namespace TaxCredit.ServiceDefaults.Hosting;

/// <summary>Repository checks stay live; immutable group/cache snapshots are discarded at scenario boundaries.</summary>
public sealed class RuntimeWriters(IRuntimeConfiguration settings, IChannelStateRepository repository,
    IAuthEvents events, TimeProvider clock, IServiceProvider services) : IWriterEntitlement
{
    private IWriterEntitlement? _source;
    private string? _key;
    private readonly object _lock = new();

    /// <inheritdoc />
    public ValueTask<bool> IsWriterAsync(string userOid, CancellationToken cancellationToken = default)
    {
        IWriterEntitlement source;
        lock (_lock)
        {
            var mode = settings.Get("CHANNEL_WRITER_SOURCE") ?? "allowlist";
            var group = settings.Get("CHANNEL_WRITER_GROUP_ID");
            var key = mode + ":" + group;
            if (_source is null || key != _key) { _source = Build(mode, group); _key = key; }
            source = _source;
        }
        return source.IsWriterAsync(userOid, cancellationToken);
    }

    /// <summary>Called after active requests and streams have ended.</summary>
    public void Reset()
    {
        lock (_lock) { _source = null; _key = null; }
    }

    private IWriterEntitlement Build(string mode, string? group)
    {
        var allow = new DenyOnFailure(new RepositoryWriters(repository), "allowlist", events);
        if (mode == "allowlist") { return allow; }
        if (mode is not ("entra_group" or "either") || !Guid.TryParse(group, out _))
        {
            throw new InvalidOperationException("Invalid CHANNEL_WRITER_SOURCE or CHANNEL_WRITER_GROUP_ID.");
        }
        var groups = services.GetService(typeof(IGroupMembershipProvider)) as IGroupMembershipProvider
            ?? throw new InvalidOperationException("Group writer policy requires an explicit IGroupMembershipProvider.");
        var entitlement = new EntraGroupEntitlement(group!, groups, events, clock);
        return mode == "entra_group" ? entitlement : new EitherEntitlement([("allowlist", allow), ("entra_group", entitlement)], events);
    }
}
