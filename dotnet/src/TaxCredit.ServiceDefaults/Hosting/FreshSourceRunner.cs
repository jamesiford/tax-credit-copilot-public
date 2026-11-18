using TaxCredit.Application.Ports.Persistence;
using TaxCredit.Application.Ports.Sources;
using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Pipeline;

namespace TaxCredit.ServiceDefaults.Hosting;

/// <summary>
/// Every calculation run, synchronous or queued, reads its payroll under a require-fresh scope, so a cached projection is reused
/// only after a fingerprint taken for this run matches. The Domain's own payroll reads inside the run are covered without editing it.
/// </summary>
public sealed class FreshSourceRunner(IClientCalculationRunner inner, IPayrollFreshness freshness) : IClientCalculationRunner
{
    /// <inheritdoc />
    public PyDict Run(RunClientCalculationCommand command)
    {
        using var fresh = freshness.RequireFresh();
        return inner.Run(command);
    }
}
