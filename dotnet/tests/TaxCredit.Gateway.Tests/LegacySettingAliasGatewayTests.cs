using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;
using TaxCredit.ServiceDefaults.Hosting;

namespace TaxCredit.Gateway.Tests;

[CollectionDefinition("ConsoleError", DisableParallelization = true)]
public sealed class ConsoleErrorCollection;

/// <summary>The gateway accepts the pre-rename setting names for one release.</summary>
[Collection("ConsoleError")]
public sealed class LegacySettingAliasGatewayTests
{
    [Fact]
    public async Task The_gateway_accepts_the_old_names_with_one_warning_each_no_value_and_the_new_name_wins()
    {
        var directory = Path.Combine(AppContext.BaseDirectory, "tcc-gateway-alias-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(directory);
        var database = Path.Combine(directory, "operations.db");
        var original = Console.Error;
        var error = new StringWriter();
        Console.SetError(error);
        try
        {
            await using var app = GatewayHost.Build(
            [
                "--TCC_CONTRACT_HOOKS=1",
                "--TCC_PERSISTENCE_PROVIDER=warehouse", "--PERSISTENCE_PROVIDER=sqlite",
                "--OPERATIONAL_DB=" + database,
                "--ARTIFACT_LOCAL_ROOT=" + Path.Combine(directory, "bytes"),
            ], builder => builder.Logging.ClearProviders());
            var settings = app.Services.GetRequiredService<RuntimeConfiguration>();
            Assert.Equal("1", settings.Get("CONTRACT_HOOKS"));
            Assert.Equal("sqlite", settings.Get("PERSISTENCE_PROVIDER"));
            var text = error.ToString();
            Assert.Equal(1, text.Split("TCC_CONTRACT_HOOKS").Length - 1);
            Assert.DoesNotContain("TCC_PERSISTENCE_PROVIDER", text, StringComparison.Ordinal);
            Assert.DoesNotContain(database, text, StringComparison.Ordinal);
        }
        finally
        {
            Console.SetError(original);
        }
    }
}
