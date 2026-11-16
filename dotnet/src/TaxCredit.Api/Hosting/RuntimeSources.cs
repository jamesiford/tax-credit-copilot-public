using System.Buffers.Binary;
using System.Security.Cryptography;
using TaxCredit.Application.Ports.Contract;

namespace TaxCredit.Api.Hosting;

/// <summary>Test seams are immutable at startup; an environment hook cannot turn them on in production.</summary>
public sealed class RuntimeSources(bool deterministic) : IClock, IIdSource, ISecretSource
{
    private long _ids;
    private long _secrets;

    /// <inheritdoc />
    public DateTimeOffset UtcNow => deterministic
        ? new DateTimeOffset(2026, 1, 15, 12, 0, 0, TimeSpan.Zero)
        : DateTimeOffset.UtcNow;

    /// <inheritdoc />
    public Guid NewId()
    {
        if (!deterministic)
        {
            return Guid.NewGuid();
        }

        var n = Interlocked.Increment(ref _ids);
        return Guid.Parse("40000000-0000-4000-8000-" + n.ToString("x12", System.Globalization.CultureInfo.InvariantCulture));
    }

    /// <inheritdoc />
    public byte[] NextBytes(int count)
    {
        ArgumentOutOfRangeException.ThrowIfNegative(count);
        if (!deterministic)
        {
            return RandomNumberGenerator.GetBytes(count);
        }

        var bytes = new byte[count];
        Span<byte> word = stackalloc byte[8];
        BinaryPrimitives.WriteInt64BigEndian(word, Interlocked.Increment(ref _secrets));
        for (var i = 0; i < count; i++)
        {
            bytes[i] = word[i % word.Length];
        }

        return bytes;
    }

    /// <summary>Resets both counter families at a scenario boundary.</summary>
    public void Reset()
    {
        Interlocked.Exchange(ref _ids, 0);
        Interlocked.Exchange(ref _secrets, 0);
    }
}
