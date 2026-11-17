using TaxCredit.Application.Ports.Auth;
using TaxCredit.Infrastructure.Auth;

namespace TaxCredit.ServiceDefaults.Hosting;

/// <summary>These public fixture identities are enabled only by immutable, explicit local replay startup.</summary>
internal static class SyntheticPolicy
{
    internal const string Tenant = "00000000-0000-0000-0000-0000000000aa";
    internal const string Audience = "11111111-2222-3333-4444-555555555555";
    internal const string Writer = "00000000-0000-0000-0000-0000000000a2";

    internal static IClientAuthorizer Clients() => new AllowListClientAuthorizer(
        new Dictionary<string, IEnumerable<long>>(StringComparer.Ordinal)
        {
            ["00000000-0000-0000-0000-0000000000a1"] = [1001, 2001, 2002, 2003, 2004],
            [Writer] = [1001, 2001, 2002, 2003, 2004],
            ["00000000-0000-0000-0000-0000000000a3"] = [999],
            ["00000000-0000-0000-0000-0000000000b1"] = [1001, 2001, 2002, 2003, 2004],
        });
}
