namespace TaxCredit.Deployment.Telemetry;

internal static class Diagnostics
{
    private static int _invalid;
    private static int _failed;

    internal static void InvalidConfiguration() =>
        WriteOnce(ref _invalid, "TCC_TELEMETRY_INVALID_CONFIGURATION");

    internal static void ExportFailed() =>
        WriteOnce(ref _failed, "TCC_TELEMETRY_EXPORT_FAILED");

    private static void WriteOnce(ref int written, string code)
    {
        if (Interlocked.Exchange(ref written, 1) != 0) { return; }
        try { Console.Error.WriteLine(code); }
        catch (IOException) { /* A closed stderr must not take down the application. */ }
        catch (ObjectDisposedException) { /* Process teardown can close stderr first. */ }
    }
}
