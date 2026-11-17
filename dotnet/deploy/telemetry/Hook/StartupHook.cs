using TaxCredit.Deployment.Telemetry;

#pragma warning disable CA1050 // The runtime requires this exact global type and entry point.
/// <summary>Installs the optional deployment listener before the application's entry point.</summary>
public static class StartupHook
{
    private static Agent? _agent;

    /// <summary>Invalid configuration disables telemetry with only a fixed diagnostic code.</summary>
    public static void Initialize()
    {
        var settings = Settings.Read();
        if (settings is not null)
        {
            _agent = new Agent(settings);
        }
    }
}
#pragma warning restore CA1050
