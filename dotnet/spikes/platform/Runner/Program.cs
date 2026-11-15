using System.Diagnostics;
using System.Text.Json;
using Azure.Core;
using Azure.Identity;
using Microsoft.Data.SqlClient;
using PlatformSpike;

var root = Path.GetFullPath(Path.Combine(AppContext.BaseDirectory, "..", "..", "..", "..", "..", "..", "docs"));
var command = args.FirstOrDefault() ?? "selftest";
DemoEnvironment? config = null;
try
{
    ScratchGuard.SelfTest();
    if (command == "selftest") return 0;
    config = new DemoEnvironment();
    var guard = new ScratchGuard(config.Get("SOURCE_SCHEMA", "tcc_source"), ["Payroll"]);
    if (command != "ps1" && command != "cleanup")
        throw new InvalidOperationException("Supported commands: selftest, ps1, cleanup.");
    var token = await new AzureCliCredential().GetTokenAsync(
        new TokenRequestContext(["https://database.windows.net/.default"]));
    await using var connection = new SqlConnection(config.ConnectionString(pooling: command != "cleanup"));
    connection.AccessToken = token.Token;
    var watch = Stopwatch.StartNew();
    await connection.OpenAsync();
    guard.Check("SELECT 1");
    await using var probe = new SqlCommand("SELECT 1", connection) { CommandTimeout = 90 };
    _ = await probe.ExecuteScalarAsync();
    Console.WriteLine($"Warehouse SELECT 1 succeeded in {watch.Elapsed.TotalSeconds:F3}s.");
    await Cleanup.Run(connection, guard);
    if (command == "cleanup") return 0;
    Directory.CreateDirectory(root);
    var report = new { phase = "PS1", first_connection_and_probe_seconds = watch.Elapsed.TotalSeconds };
    await File.WriteAllTextAsync(Path.Combine(root, "platform-connectivity.json"), JsonSerializer.Serialize(report));
    return 0;
}
catch (Exception error) when (error is SqlException or Azure.Identity.AuthenticationFailedException
    or Azure.Identity.CredentialUnavailableException or GuardRefusal or InvalidOperationException)
{
    var safe = config?.Redact(error.Message) ?? error.GetType().Name;
    Console.Error.WriteLine($"{error.GetType().Name}: {safe}");
    if (error is SqlException sql) Console.Error.WriteLine($"SqlException.Number={sql.Number}");
    Directory.CreateDirectory(root);
    var paused = safe.Contains("not found", StringComparison.OrdinalIgnoreCase)
        || safe.Contains("does not exist", StringComparison.OrdinalIgnoreCase)
        || safe.Contains("unavailable", StringComparison.OrdinalIgnoreCase);
    var reason = paused ? "The demo capacity appears paused or its item is unavailable. Do not resume it."
        : "Preflight/connectivity failed. No experiment writes were attempted.";
    await File.WriteAllTextAsync(Path.Combine(root, "HALT.md"),
        $"# Platform spike halted\n\n{reason}\n\nError: {error.GetType().Name}; "
        + (error is SqlException e ? $"number {e.Number}; " : "") + safe
        + "\n\nNo scratch objects were created by this run. Cleanup of pre-existing objects is not proven.\n");
    return 2;
}
