using System.Security.Cryptography;
using TaxCredit.Application.Ports.Contract;

namespace TaxCredit.Application.Features.Ai.Capabilities.Bindings;

internal sealed class CapabilityRandomSources : IIdSource, ISecretSource
{
    public Guid NewId() => Guid.NewGuid();
    public byte[] NextBytes(int count) => RandomNumberGenerator.GetBytes(count);
}
