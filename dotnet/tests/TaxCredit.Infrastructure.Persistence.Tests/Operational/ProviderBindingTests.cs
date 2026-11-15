using TaxCredit.Domain.Claims;
using TaxCredit.Infrastructure.Persistence.Operational;
using TaxCredit.Infrastructure.Persistence.Sql;
using TaxCredit.Infrastructure.Persistence.Tests.Sql;

namespace TaxCredit.Infrastructure.Persistence.Tests.Operational;

public sealed class ProviderBindingTests
{
    [Fact]
    public void WarehouseClaimsBindTypedDatesAndUtcInstantsWithoutScalingMoney()
    {
        using var connection = new RecordingConnection();
        var database = new PersistenceDatabase(() => connection, new SqlServerDialect());
        var instant = RunBatchRepositoryTests.At(0) with { OffsetMinutes = 330, Microsecond = 123456 };
        var claim = ProgramClaim.Create(ClaimRepositoryTests.Claim(11, "typed").ToSpec() with { DecidedAt = instant, EffectiveFrom = instant });
        new ClaimRepository(database).Record(claim);
        var insert = connection.Commands.Last();
        Assert.Contains("INSERT INTO", insert.Sql, StringComparison.Ordinal);
        Assert.Equal("1234.50", insert.Values[7]);
        var timestamp = Assert.IsType<DateTime>(insert.Values[20]);
        Assert.Equal(new DateTime(2026, 1, 1, 6, 30, 0, DateTimeKind.Utc).AddTicks(1234560), timestamp);
        Assert.Equal(DateTimeKind.Utc, timestamp.Kind);
        Assert.Equal(new DateTime(2026, 1, 1), Assert.IsType<DateTime>(insert.Values[22]));
        Assert.Equal(1, connection.Commits);
    }

    [Fact]
    public void WarehouseLeasePredicatesAndUpdatesShareTypedUtcClock()
    {
        using var connection = new RecordingConnection();
        var database = new PersistenceDatabase(() => connection, new SqlServerDialect());
        var now = RunBatchRepositoryTests.At(0) with { OffsetMinutes = 330 };
        Assert.True(new RunBatchRepository(database).Heartbeat(11, "item", "owner", 120, now));
        var command = Assert.Single(connection.Commands);
        Assert.Equal(new DateTime(2026, 1, 1, 6, 30, 0, DateTimeKind.Utc), Assert.IsType<DateTime>(command.Values[0]));
        Assert.Equal(new DateTime(2026, 1, 1, 6, 32, 0, DateTimeKind.Utc), Assert.IsType<DateTime>(command.Values[1]));
        Assert.Equal(command.Values[0], command.Values[^1]);
    }
}
