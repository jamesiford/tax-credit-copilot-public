using TaxCredit.Application.Ports.Persistence;

namespace TaxCredit.Infrastructure.Persistence.Sql;

/// <summary>Host commands wrap ClientCalculation.Run in this boundary; every adapter must share the configured database instance.</summary>
public sealed class PersistenceUnitOfWork(PersistenceDatabase database) : IPersistenceUnitOfWork
{
    /// <inheritdoc />
    public T Execute<T>(Func<T> operation)
    {
        ArgumentNullException.ThrowIfNull(operation);
        return database.Transact(_ => operation());
    }
}
