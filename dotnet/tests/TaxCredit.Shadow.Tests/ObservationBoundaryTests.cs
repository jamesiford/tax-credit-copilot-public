using TaxCredit.Shadow;

namespace TaxCredit.Shadow.Tests;

public sealed class ObservationBoundaryTests
{
    [Theory]
    [InlineData("DROP TABLE tcc_ops.run_manifest")]
    [InlineData("SELECT * FROM OPENROWSET(BULK 'file', SINGLE_CLOB) AS x")]
    [InlineData("SELECT 1; SELECT 2")]
    [InlineData("CREATE TABLE tcc_scratch_dotnet.example (id int)")]
    [InlineData("DELETE FROM tcc_source.Payroll")]
    public void Refuses_before_dispatch(string statement)
    {
        var dispatched = false;
        Assert.Throws<InvalidOperationException>(() =>
        {
            ObservationGuard.Check(statement, ["SELECT 1"]);
            dispatched = true;
        });
        Assert.False(dispatched);
    }

    [Fact]
    public void Recovery_cleans_only_acknowledged_invocation_objects_in_finally()
    {
        var shared = new Dictionary<string, long>(StringComparer.Ordinal) { ["pre_existing"] = 1 };
        var ownership = new ScratchOwnership(Guid.NewGuid(), shared.Keys);
        var owned = ownership.Reserve();
        shared.Add(owned, 2);
        ownership.AcknowledgeCreated(owned, 2);
        try
        {
            throw new IOException("Synthetic interruption.");
        }
        catch (IOException)
        {
            Assert.Single(ownership.RecoveryLedger);
        }
        finally
        {
            Assert.Equal(1, ownership.Cleanup(name => shared.GetValueOrDefault(name), name => shared.Remove(name)));
        }

        Assert.Single(shared);
        Assert.True(shared.ContainsKey("pre_existing"));
        Assert.Equal(0, ownership.Cleanup(name => shared.GetValueOrDefault(name), name => shared.Remove(name)));
        Assert.Throws<InvalidOperationException>(() => ownership.AcknowledgeCreated("pre_existing", 1));
    }

    [Fact]
    public void Recovery_retains_failed_drops_and_refuses_replaced_objects()
    {
        var invocation = Guid.NewGuid();
        var ownership = new ScratchOwnership(invocation, []);
        var name = ownership.Reserve();
        ownership.AcknowledgeCreated(name, 2);
        Assert.Throws<IOException>(() => ownership.Cleanup(_ => 2, _ => throw new IOException("Synthetic outage.")));
        Assert.Single(ownership.RecoveryLedger);
        ownership = ScratchOwnership.Recover(invocation, [], ownership.RecoveryLedger);
        Assert.Throws<InvalidOperationException>(() => ownership.Cleanup(_ => 3, _ => Assert.Fail("Must not delete another invocation's object.")));
        Assert.Equal(1, ownership.Cleanup(_ => 2, _ => { }));
        Assert.Throws<InvalidOperationException>(() => ScratchOwnership.Recover(Guid.NewGuid(), [], new Dictionary<string, long> { [name] = 2 }));
    }
}
