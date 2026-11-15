using System.Diagnostics;

namespace TaxCredit.Parity.Tests;

/// <summary>
/// The pinned oracle interpreter. The product runs on CPython 3.12, and later releases differ in ways that change bits
/// (<c>sum()</c> of an int after a float, the Unicode database), so the tests refuse any other interpreter. There is
/// deliberately no default path: <c>TCC_PYTHON</c> must name the interpreter explicitly.
/// </summary>
internal static class OracleInterpreter
{
    /// <summary>The message shared with the Python scripts' guard (<c>parity/oracle.py</c>).</summary>
    public const string HowToCreate =
        "The parity oracle is CPython 3.12 (the interpreter the product runs on). Create the oracle environment with:\n" +
        "    uv python install 3.12\n" +
        "    uv venv --python 3.12 C:\\Projects\\py312-oracle\\.venv\n" +
        "then set TCC_PYTHON to C:\\Projects\\py312-oracle\\.venv\\Scripts\\python.exe.";

    private static readonly Lazy<(string Exe, string Version)> Resolved = new(Resolve);

    /// <summary>The verified oracle interpreter path; throws unless <c>TCC_PYTHON</c> names CPython 3.12.</summary>
    public static string Exe => Resolved.Value.Exe;

    /// <summary>The verified interpreter's version string, e.g. <c>3.12.13</c>.</summary>
    public static string Version => Resolved.Value.Version;

    private static (string Exe, string Version) Resolve()
    {
        var exe = Environment.GetEnvironmentVariable("TCC_PYTHON");
        if (string.IsNullOrWhiteSpace(exe))
        {
            throw new InvalidOperationException("TCC_PYTHON is not set. " + HowToCreate);
        }

        var info = new ProcessStartInfo(exe, "--version") { RedirectStandardOutput = true, RedirectStandardError = true, UseShellExecute = false };
        using var p = Process.Start(info) ?? throw new InvalidOperationException("could not start " + exe);
        var text = (p.StandardOutput.ReadToEnd() + p.StandardError.ReadToEnd()).Trim();
        p.WaitForExit();
        const string prefix = "Python ";
        var version = text.StartsWith(prefix, StringComparison.Ordinal) ? text[prefix.Length..] : text;
        if (!IsCPython312(version))
        {
            throw new InvalidOperationException($"TCC_PYTHON ({exe}) is Python {version}, not 3.12. " + HowToCreate);
        }

        return (exe, version);
    }

    /// <summary>True for a <c>3.12.x</c> version string.</summary>
    internal static bool IsCPython312(string version) => version.StartsWith("3.12.", StringComparison.Ordinal);
}
