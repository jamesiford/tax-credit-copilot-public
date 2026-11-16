namespace TaxCredit.Application.Ports.Contract;

/// <summary>Explicitly empty walking-skeleton worker; it makes no claim to have reset a real store.</summary>
public sealed class NoContractWork : IContractWork
{
    /// <inheritdoc />
    public ValueTask<int> Drain(CancellationToken cancellationToken) => ValueTask.FromResult(0);

    /// <inheritdoc />
    public ValueTask Reset(string profile, CancellationToken cancellationToken) => ValueTask.CompletedTask;

    /// <inheritdoc />
    public ValueTask EnvironmentChanged(CancellationToken cancellationToken) => ValueTask.CompletedTask;
}
