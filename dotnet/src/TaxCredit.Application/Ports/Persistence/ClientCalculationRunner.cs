using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Pipeline;

namespace TaxCredit.Application.Ports.Persistence;

/// <summary>Runs calculation, Gold publication and claim assessment as one durable use case.</summary>
public interface IClientCalculationRunner
{
    /// <summary>A failed assessment cannot leave a successful partial calculation behind.</summary>
    PyDict Run(RunClientCalculationCommand command);
}
