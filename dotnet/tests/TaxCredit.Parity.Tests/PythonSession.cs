using System.Diagnostics;
using System.Text;
using System.Text.Json;

namespace TaxCredit.Parity.Tests;

/// <summary>A persistent <c>parity/engine_cli.py</c> process: one JSON request line in, one response line out.</summary>
internal sealed class PythonSession : IDisposable
{
    private readonly Process _process;

    private PythonSession(Process process) => _process = process;

    /// <summary>The oracle interpreter: <c>TCC_PYTHON</c>, verified once to be CPython 3.12; there is no default.</summary>
    public static string PythonExe => OracleInterpreter.Exe;

    public static PythonSession Start()
    {
        var parity = GoldenFiles.ParityDirectory;
        var info = new ProcessStartInfo(PythonExe, "\"" + Path.Combine(parity, "engine_cli.py") + "\"" + (OracleInterpreter.AllowOther ? " --allow-other-python" : string.Empty))
        {
            WorkingDirectory = Path.Combine(Directory.GetParent(parity)!.FullName, "backend"),
            RedirectStandardInput = true,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            StandardInputEncoding = new UTF8Encoding(false),
            StandardOutputEncoding = new UTF8Encoding(false),
            UseShellExecute = false,
        };
        info.Environment["PYTHONUTF8"] = "1";
        info.Environment.Remove("PYTHONHASHSEED");
        var p = Process.Start(info) ?? throw new InvalidOperationException("could not start python");
        p.ErrorDataReceived += (_, _) => { };
        p.BeginErrorReadLine();
        return new PythonSession(p);
    }

    /// <summary>Sends a batch and returns the responses in order.</summary>
    public List<string> Run(IReadOnlyList<string> requests)
    {
        var writer = Task.Run(() =>
        {
            foreach (var r in requests)
            {
                _process.StandardInput.WriteLine(r);
            }

            _process.StandardInput.Flush();
        });
        var responses = new List<string>(requests.Count);
        for (var i = 0; i < requests.Count; i++)
        {
            responses.Add(_process.StandardOutput.ReadLine() ?? throw new InvalidOperationException("python closed its output early"));
        }

        writer.Wait();
        return responses;
    }

    public string RunOne(string request) => Run([request])[0];

    public void Dispose()
    {
        try
        {
            _process.StandardInput.Close();
            _process.WaitForExit(5000);
        }
        catch (InvalidOperationException)
        {
        }

        if (!_process.HasExited)
        {
            _process.Kill(true);
        }

        _process.Dispose();
    }
}

/// <summary>Compares a request's Python response line against the C# engine.</summary>
internal static class DifferentialCheck
{
    /// <summary>Null when the engines agree; otherwise a description of the first difference.</summary>
    public static string? Compare(string requestJson, string responseJson)
    {
        using var req = JsonDocument.Parse(requestJson);
        using var resp = JsonDocument.Parse(responseJson);
        var expected = resp.RootElement;
        var outcome = EngineRunner.Execute(req.RootElement);
        if (!expected.GetProperty("ok").GetBoolean())
        {
            var err = expected.GetProperty("error").GetString();
            return !outcome.Ok && outcome.Error == err ? null : $"expected {err}, got {(outcome.Ok ? "a result" : outcome.Error)}";
        }

        if (!outcome.Ok)
        {
            return $"expected a result, got {outcome.Error}";
        }

        var diff = JsonTree.Diff(JsonTree.Read(expected.GetProperty("result")), outcome.Result, "result");
        if (diff is not null)
        {
            return diff;
        }

        var trail = expected.GetProperty("trail");
        diff = JsonTree.Diff(trail.ValueKind == JsonValueKind.Null ? null : JsonTree.Read(trail), outcome.Trail, "trail");
        if (diff is not null)
        {
            return diff;
        }

        return outcome.FloatDigest == expected.GetProperty("float_digest").GetString() ? null : "float digest differs";
    }
}
