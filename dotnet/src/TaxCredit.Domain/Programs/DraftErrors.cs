using TaxCredit.Domain.Numerics;

namespace TaxCredit.Domain.Programs;

/// <summary>
/// A refusal that names its reason (Python <c>DraftError(Exception)</c>); routers map each subtype to a status and the message is for a person.
/// </summary>
/// <remarks>
/// The class hierarchy is the contract: Python code catches <c>ReviewRefused</c> to cover <c>CustomerDataInDraft</c>, so the C# subtypes
/// inherit the same way and <see cref="PyException.PythonType"/> carries the exact class name the goldens compare. Python's classes are
/// instantiable at every level; the architecture rule that public classes are sealed or abstract splits each such level in two: an abstract
/// base to catch (<see cref="DraftError"/>, <see cref="ReviewRefusal"/>, <see cref="PreviewRefusal"/>) and a sealed class to raise
/// (<see cref="DraftRefused"/> for Python's own <c>DraftError</c>, <see cref="ReviewRefused"/>, <see cref="PreviewRefused"/>).
/// </remarks>
public abstract class DraftError : PyException
{
    /// <summary>Used by the subtypes to name their Python class.</summary>
    /// <param name="pythonType">The Python class name.</param>
    /// <param name="message">What was refused.</param>
    protected DraftError(string pythonType, string message)
        : base(pythonType, message)
    {
    }

    /// <summary>Python class attribute <c>code</c>: the stable identifier a router maps.</summary>
    public abstract string Code { get; }
}

/// <summary>A refusal with no more specific type: Python's <c>DraftError</c> itself, raised directly.</summary>
/// <param name="message">What was refused.</param>
public sealed class DraftRefused(string message) : DraftError("DraftError", message)
{
    /// <inheritdoc />
    public override string Code => "draft_refused";
}

/// <summary>No draft with that id (Python <c>DraftNotFound</c>).</summary>
/// <param name="message">What was refused.</param>
public sealed class DraftNotFound(string message) : DraftError("DraftNotFound", message)
{
    /// <inheritdoc />
    public override string Code => "draft_not_found";
}

/// <summary>The draft changed since the caller read it (optimistic concurrency), or a live draft for the code exists (Python <c>DraftConflict</c>).</summary>
/// <param name="message">What was refused.</param>
public sealed class DraftConflict(string message) : DraftError("DraftConflict", message)
{
    /// <inheritdoc />
    public override string Code => "draft_conflict";
}

/// <summary>The request itself is malformed: a bad code, an unsupported jurisdiction, a document that is not an object or too large (Python <c>DraftInvalid</c>).</summary>
/// <param name="message">What was refused.</param>
public sealed class DraftInvalid(string message) : DraftError("DraftInvalid", message)
{
    /// <inheritdoc />
    public override string Code => "draft_invalid";
}

/// <summary>The requested move is not allowed from the draft's current status, or its documents cannot be edited now (Python <c>InvalidTransition</c>).</summary>
/// <param name="message">What was refused.</param>
public sealed class InvalidTransition(string message) : DraftError("InvalidTransition", message)
{
    /// <inheritdoc />
    public override string Code => "invalid_transition";
}

/// <summary>What <c>except ReviewRefused</c> catches in Python: <see cref="ReviewRefused"/> and <see cref="CustomerDataInDraft"/>.</summary>
public abstract class ReviewRefusal : DraftError
{
    /// <summary>Used by the subtypes to name their Python class.</summary>
    /// <param name="pythonType">The Python class name.</param>
    /// <param name="message">What was refused.</param>
    protected ReviewRefusal(string pythonType, string message)
        : base(pythonType, message)
    {
    }
}

/// <summary>The review rule failed: not validated, stale validation, or the reviewer is the author (Python <c>ReviewRefused</c>).</summary>
/// <param name="message">What was refused.</param>
public sealed class ReviewRefused(string message) : ReviewRefusal("ReviewRefused", message)
{
    /// <inheritdoc />
    public override string Code => "review_refused";
}

/// <summary>The documents look like they hold customer data (an identifier, an email, a client name); a bundle must not carry it (Python <c>CustomerDataInDraft</c>).</summary>
/// <param name="message">What was refused.</param>
public sealed class CustomerDataInDraft(string message) : ReviewRefusal("CustomerDataInDraft", message)
{
    /// <inheritdoc />
    public override string Code => "customer_data_in_draft";
}

/// <summary>What <c>except PreviewRefused</c> catches in Python: <see cref="PreviewRefused"/> and <see cref="CustomerDataRefused"/>.</summary>
public abstract class PreviewRefusal : DraftError
{
    /// <summary>Used by the subtypes to name their Python class.</summary>
    /// <param name="pythonType">The Python class name.</param>
    /// <param name="message">What was refused.</param>
    protected PreviewRefusal(string pythonType, string message)
        : base(pythonType, message)
    {
    }
}

/// <summary>A preview cannot run: the documents do not validate, there is no year to price, or the data is not allowed (Python <c>PreviewRefused</c>).</summary>
/// <param name="message">What was refused.</param>
public sealed class PreviewRefused(string message) : PreviewRefusal("PreviewRefused", message)
{
    /// <inheritdoc />
    public override string Code => "preview_refused";
}

/// <summary>A preview was asked to read a customer-classified source and nothing allows it (Python <c>CustomerDataRefused</c>).</summary>
/// <param name="message">What was refused.</param>
public sealed class CustomerDataRefused(string message) : PreviewRefusal("CustomerDataRefused", message)
{
    /// <inheritdoc />
    public override string Code => "customer_data_refused";
}
