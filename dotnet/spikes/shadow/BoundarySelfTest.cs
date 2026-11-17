namespace TaxCredit.Shadow;

internal static class BoundarySelfTest
{
    public static int Cleanup()
    {
        var shared = new Dictionary<string, long>(StringComparer.Ordinal) { ["shared"] = 1 };
        var invocation = Guid.NewGuid();
        var ownership = new ScratchOwnership(invocation, shared.Keys);
        var name = ownership.Reserve();
        shared.Add(name, 2);
        ownership.AcknowledgeCreated(name, 2);
        int removed;
        try { throw new IOException("Synthetic interruption."); }
        catch (IOException) { }
        finally
        {
            removed = ownership.Cleanup(key => shared.GetValueOrDefault(key), key => shared.Remove(key));
        }

        if (removed != 1 || shared.Count != 1 || !shared.ContainsKey("shared"))
        {
            throw new InvalidOperationException("Ownership cleanup self-test failed.");
        }

        name = ownership.Reserve();
        ownership.AcknowledgeCreated(name, 3);
        try
        {
            ownership.Cleanup(_ => 3, _ => throw new IOException("Synthetic drop failure."));
            throw new InvalidOperationException("Failed drop was not retained.");
        }
        catch (IOException) { }
        ownership = ScratchOwnership.Recover(invocation, shared.Keys, ownership.RecoveryLedger);
        Refuses(() => ownership.Cleanup(_ => 4, _ => throw new IOException("Unowned drop.")));
        Refuses(() => ScratchOwnership.Recover(Guid.NewGuid(), [], ownership.RecoveryLedger));
        if (ownership.Cleanup(_ => 3, _ => { }) != 1 || ownership.RecoveryLedger.Count != 0)
        {
            throw new InvalidOperationException("Ownership recovery self-test failed.");
        }

        return 3;
    }

    private static void Refuses(Action operation)
    {
        try { operation(); }
        catch (InvalidOperationException) { return; }
        throw new IOException("Ownership refusal self-test failed.");
    }
}
