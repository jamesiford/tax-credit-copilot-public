using TaxCredit.Domain.Numerics;

namespace TaxCredit.Domain.Pipeline;

/// <summary>Python <c>ClientRunNotAvailable</c> (a <c>LookupError</c>): the question cannot be answered, and why. An empty population would read as "nobody qualifies".</summary>
/// <param name="message">The reason.</param>
public sealed class ClientRunNotAvailable(string message) : PyException("ClientRunNotAvailable", message);

/// <summary>Python <c>PayrollNotAvailable</c> (a <c>LookupError</c>): there is no payroll to answer from; the subclasses say which kind of absence.</summary>
/// <param name="pythonType">The Python class name of the concrete subclass.</param>
/// <param name="message">The reason.</param>
public abstract class PayrollNotAvailable(string pythonType, string message) : PyException(pythonType, message);

/// <summary>Python <c>NoPayrollForClient</c>: a named client has no rows (different from an absent dataset).</summary>
/// <param name="message">The reason.</param>
public sealed class NoPayrollForClient(string message) : PayrollNotAvailable("NoPayrollForClient", message);

/// <summary>Python <c>PayrollDatasetNotGenerated</c>: the default dataset has not been generated at all.</summary>
/// <param name="message">The reason.</param>
public sealed class PayrollDatasetNotGenerated(string message) : PayrollNotAvailable("PayrollDatasetNotGenerated", message);

/// <summary>Python <c>ProgramStateConflict</c> (a <c>ValueError</c>): a request named a program and a state that are not the same program's.</summary>
/// <param name="message">The reason.</param>
public sealed class ProgramStateConflict(string message) : PyException("ProgramStateConflict", message);

/// <summary>
/// The family of Python's <c>ProgramNotRunnable</c> (a <c>LookupError</c>): no run can be priced for the program. Python's <c>ProgramChoiceRequired</c> is a
/// subclass of it, so a handler that catches the base catches both; here the two concrete errors share this abstract base (the layering rule seals every public class).
/// </summary>
/// <param name="pythonType">The Python class name of the concrete error.</param>
/// <param name="message">The reason.</param>
public abstract class ProgramNotRunnableError(string pythonType, string message) : PyException(pythonType, message);

/// <summary>Python <c>ProgramNotRunnable</c>: the program exists but no run can be priced for it (unknown, retired or federal).</summary>
/// <param name="message">The reason.</param>
public sealed class ProgramNotRunnable(string message) : ProgramNotRunnableError("ProgramNotRunnable", message);

/// <summary>Python <c>ProgramChoiceRequired</c> (a <c>ProgramNotRunnable</c>): a state has several calculable programs and a READ named none; the message lists them.</summary>
public sealed class ProgramChoiceRequired : ProgramNotRunnableError
{
    /// <summary>Creates the error.</summary>
    /// <param name="state">The state.</param>
    /// <param name="candidates">The calculable programs, registry order.</param>
    public ProgramChoiceRequired(string state, IReadOnlyList<string> candidates)
        : base("ProgramChoiceRequired", $"state {state} has several calculable programs ({string.Join(", ", candidates)}): pass program_code to choose one")
    {
        Candidates = candidates;
    }

    /// <summary>The calculable programs, registry order.</summary>
    public IReadOnlyList<string> Candidates { get; }
}

/// <summary>Python <c>GoldWriteFailed</c> (a <c>RuntimeError</c>): a write or its validation did not hold; the run is not usable.</summary>
/// <param name="message">The violations.</param>
public sealed class GoldWriteFailed(string message) : PyException("GoldWriteFailed", message);
