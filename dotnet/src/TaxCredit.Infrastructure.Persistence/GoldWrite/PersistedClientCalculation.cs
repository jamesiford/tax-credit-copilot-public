using TaxCredit.Application.Hosting;
using TaxCredit.Application.Ports.Persistence;
using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Pipeline;

namespace TaxCredit.Infrastructure.Persistence;

/// <summary>W2 consumes this runner instead of invoking the domain pipeline outside its persistence transaction.</summary>
public sealed class PersistedClientCalculation(ClientCalculation calculation, IPersistenceUnitOfWork unitOfWork) : IClientCalculationRunner
{
    /// <inheritdoc />
    public PyDict Run(RunClientCalculationCommand command)
    {
        using var span = RunSpans.Start("run.calculation");
        return unitOfWork.Execute(() => calculation.Run(command));
    }
}
