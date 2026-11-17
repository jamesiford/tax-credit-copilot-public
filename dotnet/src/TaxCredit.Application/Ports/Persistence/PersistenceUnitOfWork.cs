namespace TaxCredit.Application.Ports.Persistence;

/// <summary>Coordinates the Gold write and the assessment's claim side effects without changing the certified Domain pipeline.</summary>
public interface IPersistenceUnitOfWork
{
    /// <summary>Publishes all writes together, or rolls them all back on an assessment or validation failure.</summary>
    T Execute<T>(Func<T> operation);
}
