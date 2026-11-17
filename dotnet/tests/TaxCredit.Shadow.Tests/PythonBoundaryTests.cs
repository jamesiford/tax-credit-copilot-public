using System.Diagnostics;
using System.Text.Json;

namespace TaxCredit.Shadow.Tests;

public sealed class PythonBoundaryTests
{
    [Fact]
    public async Task Private_diagnostics_and_semantic_mutations_pass_in_the_pinned_oracle()
    {
        var root = new DirectoryInfo(AppContext.BaseDirectory);
        while (root is not null && !Directory.Exists(Path.Combine(root.FullName, "contract")))
        {
            root = root.Parent;
        }

        Assert.NotNull(root);
        var start = new ProcessStartInfo
        {
            FileName = Environment.GetEnvironmentVariable("TCC_PYTHON") ?? @"C:\Projects\py312-oracle\.venv\Scripts\python.exe",
            WorkingDirectory = Path.Combine(root.FullName, "dotnet"),
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            UseShellExecute = false,
        };
        start.ArgumentList.Add("-B");
        start.ArgumentList.Add(Path.Combine(root.FullName, "dotnet", "spikes", "shadow", "run_tests.py"));
        using var process = Process.Start(start)!;
        var output = process.StandardOutput.ReadToEndAsync();
        var errors = process.StandardError.ReadToEndAsync();
        using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(20));
        try
        {
            await process.WaitForExitAsync(timeout.Token);
        }
        catch (OperationCanceledException)
        {
            process.Kill(entireProcessTree: true);
            throw;
        }

        Assert.Equal(0, process.ExitCode);
        Assert.True(string.IsNullOrEmpty(await errors), "The boundary runner must not emit diagnostics.");
        using var result = JsonDocument.Parse(await output);
        Assert.True(result.RootElement.GetProperty("passed").GetBoolean());
        Assert.True(result.RootElement.GetProperty("tests").GetInt32() >= 8);
    }
}
