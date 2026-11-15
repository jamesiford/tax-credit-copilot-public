namespace TaxCredit.Domain.Numerics;

/// <summary>Base for exceptions that mirror a specific Python exception type by name.</summary>
public abstract class PyException : Exception
{
    /// <summary>Initialises the exception.</summary>
    /// <param name="pythonType">Name of the Python exception type being mirrored.</param>
    /// <param name="message">Human-readable detail.</param>
    protected PyException(string pythonType, string message)
        : base(message) => PythonType = pythonType;

    /// <summary>The Python exception type name (e.g. <c>ValueError</c>), used by the parity harness.</summary>
    public string PythonType { get; }
}

/// <summary>Mirrors Python <c>ValueError</c>.</summary>
public sealed class PyValueError(string message) : PyException("ValueError", message);

/// <summary>Mirrors Python <c>OverflowError</c>.</summary>
public sealed class PyOverflowError(string message) : PyException("OverflowError", message);

/// <summary>Mirrors Python <c>ZeroDivisionError</c>.</summary>
public sealed class PyZeroDivisionError(string message) : PyException("ZeroDivisionError", message);

/// <summary>Mirrors <c>decimal.InvalidOperation</c>.</summary>
public sealed class PyInvalidOperation(string message) : PyException("InvalidOperation", message);
