using System.Buffers.Binary;
using System.Diagnostics;
using System.Globalization;
using System.Security.Cryptography;
using TaxCredit.Application.Ports.Contract;

namespace TaxCredit.ServiceDefaults.Hosting;

/// <summary>Test seams are immutable at startup; an environment hook cannot turn them on in production.</summary>
public sealed class RuntimeSources(bool deterministic) : TimeProvider, IClock, IIdSource, ISecretSource
{
    private long _ids;
    private long _secrets;
    private long _ticks;

    /// <inheritdoc />
    public override DateTimeOffset GetUtcNow() => UtcNow;

    /// <inheritdoc />
    public override long GetTimestamp() => deterministic ? 0 : base.GetTimestamp();

    /// <summary>Elapsed calculation timers are deterministic independently of identity draws.</summary>
    public double ElapsedSeconds() => deterministic ? Interlocked.Increment(ref _ticks) / 1000.0
        : (double)Stopwatch.GetTimestamp() / Stopwatch.Frequency;

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
        return Guid.Parse("40000000-0000-4000-8000-" + n.ToString("x12", CultureInfo.InvariantCulture));
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
    public void Reset(long consumedIds = 0)
    {
        ArgumentOutOfRangeException.ThrowIfNegative(consumedIds);
        Interlocked.Exchange(ref _ids, consumedIds);
        Interlocked.Exchange(ref _secrets, 0);
        Interlocked.Exchange(ref _ticks, 0);
    }
}
