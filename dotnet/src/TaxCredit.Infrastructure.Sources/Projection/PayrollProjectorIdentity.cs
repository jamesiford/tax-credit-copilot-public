using System.Globalization;

namespace TaxCredit.Infrastructure.Sources.Projection;

public sealed partial class PayrollProjector
{
    private string? _cacheIdentity;

    /// <summary>
    /// Every process-constant input that changes a projection (the mapping's transforms and the pay-code policy and seed), as one string.
    /// A cached projection is only ever served to a projector with the same identity.
    /// </summary>
    public string CacheIdentity => _cacheIdentity ??= string.Join('|', mapping.WorksiteMode, mapping.NullPayDateMode,
        mapping.CaseInsensitive.ToString(CultureInfo.InvariantCulture), lookups.Options.EffectivePayCodePolicy,
        lookups.Options.CustomerClassified.ToString(CultureInfo.InvariantCulture), lookups.SeedIdentity);

    /// <summary>The digest of the pay-code lookup entries that would project this client's rows today.</summary>
    public string LookupDigest(long accountId) => lookups.PayCodeDigest(accountId);
}
