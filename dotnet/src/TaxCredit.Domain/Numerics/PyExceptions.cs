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

/// <summary>Mirrors Python <c>KeyError</c> (a missing dictionary key); the message is <c>str(KeyError(key))</c>, the key's repr.</summary>
public sealed class PyKeyError(string key) : PyException("KeyError", PyStr.Repr(key));

/// <summary>Mirrors Python <c>TypeError</c> (for example ordering <c>None</c> against a string).</summary>
public sealed class PyTypeError(string message) : PyException("TypeError", message);

/// <summary>Raised for an input the port deliberately does not model, so a gap fails loudly instead of diverging silently.</summary>
public sealed class PyUnsupportedException(string message) : Exception(message);

/// <summary>Mirrors Python <c>IndexError</c> (for example <c>list index out of range</c>).</summary>
public sealed class PyIndexError(string message) : PyException("IndexError", message);
