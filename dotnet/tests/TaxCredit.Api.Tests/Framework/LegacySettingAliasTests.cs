using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.TestHost;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using TaxCredit.Api.Hosting;
using TaxCredit.Application;
using TaxCredit.Infrastructure;
using TaxCredit.ServiceDefaults.Hosting;

namespace TaxCredit.Api.Tests.Framework;

[CollectionDefinition("ConsoleError", DisableParallelization = true)]
public sealed class ConsoleErrorCollection;

/// <summary>The one-release fallback for settings renamed away from the product prefix.</summary>
[Collection("ConsoleError")]
public sealed class LegacySettingAliasTests
{
    private const string SecretValue = "value-that-must-never-be-logged";

    private static IConfiguration Configuration(params (string Name, string Value)[] pairs) =>
        new ConfigurationBuilder().AddInMemoryCollection(pairs.ToDictionary(p => p.Name, p => (string?)p.Value)).Build();

    public static TheoryData<string, string> Aliases()
    {
        var data = new TheoryData<string, string>();
        foreach (var (current, legacy) in LegacySettingAliases.Table) { data.Add(current, legacy); }
        return data;
    }

    [Theory]
    [MemberData(nameof(Aliases))]
    public void Every_alias_resolves_the_deprecated_name_and_the_new_name_wins(string current, string legacy)
    {
        Assert.Equal("old", LegacySettingAliases.Read(Configuration((legacy, "old")), current));
        Assert.Equal("new", LegacySettingAliases.Read(Configuration((legacy, "old"), (current, "new")), current));
        Assert.Null(LegacySettingAliases.Read(Configuration(), current));
        Assert.StartsWith("TCC_", legacy, StringComparison.Ordinal);
    }

    [Fact]
    public void The_report_names_each_deprecated_variable_once_and_never_a_value()
    {
        var lines = new List<string>();
        LegacySettingAliases.Report(Configuration(("TCC_SEED_ROOT", SecretValue), ("TCC_BULK_LOAD", SecretValue), ("BULK_LOAD", "on")), lines.Add);
        var line = Assert.Single(lines);
        Assert.Contains("TCC_SEED_ROOT", line, StringComparison.Ordinal);
        Assert.Contains("SEED_ROOT", line, StringComparison.Ordinal);
        Assert.DoesNotContain(SecretValue, line, StringComparison.Ordinal);
    }

    [Fact]
    public async Task The_api_host_accepts_the_old_names_with_one_warning_each_and_no_value()
    {
        var error = new StringWriter();
        var original = Console.Error;
        Console.SetError(error);
        try
        {
            var root = Directory.CreateDirectory(Path.Combine(Corpus.Root, "dotnet", "artifacts", "host-tests", Guid.NewGuid().ToString("N"))).FullName;
            var builder = WebApplication.CreateBuilder(new WebApplicationOptions { EnvironmentName = "Production" });
            builder.Logging.ClearProviders();
            builder.Configuration.AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["TCC_CONTRACT_HOOKS"] = "1",
                ["TCC_PERSISTENCE_PROVIDER"] = "sqlite",
                ["TCC_REPOSITORY_ROOT"] = Corpus.Root,
                ["ENVIRONMENT"] = "local",
                ["AUTH_MODE"] = "none",
                ["DATA_SOURCE"] = "csv",
                ["OPERATIONAL_DB"] = Path.Combine(root, "operations.db"),
                ["ARTIFACT_LOCAL_ROOT"] = Path.Combine(root, "bytes"),
            });
            builder.WebHost.UseTestServer();
            builder.AddSkeletonHost();
            await using var app = builder.Build();
            var settings = app.Services.GetRequiredService<RuntimeConfiguration>();
            Assert.Equal("1", settings.Get("CONTRACT_HOOKS"));
            Assert.Equal("sqlite", settings.Get("PERSISTENCE_PROVIDER"));
            Assert.Equal(Corpus.Root, app.Services.GetRequiredService<RuntimePaths>().Repository);
            var text = error.ToString();
            foreach (var name in new[] { "TCC_CONTRACT_HOOKS", "TCC_PERSISTENCE_PROVIDER", "TCC_REPOSITORY_ROOT" })
            {
                Assert.Equal(1, text.Split(name).Length - 1);
            }

            Assert.DoesNotContain(Corpus.Root, text, StringComparison.Ordinal);
        }
        finally
        {
            Console.SetError(original);
        }
    }

    [Fact]
    public void The_worker_composition_accepts_the_old_names_and_the_new_name_wins()
    {
        var original = Console.Error;
        var error = new StringWriter();
        Console.SetError(error);
        try
        {
            var builder = Host.CreateApplicationBuilder();
            builder.Configuration.AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["TCC_CONTRACT_HOOKS"] = "1",
                ["TCC_WORKER_ONCE"] = "1",
                ["TCC_PERSISTENCE_PROVIDER"] = "warehouse",
                ["PERSISTENCE_PROVIDER"] = "sqlite",
                ["ENVIRONMENT"] = "local",
                ["DATA_SOURCE"] = "csv",
                ["OPERATIONAL_DB"] = Path.Combine(Path.GetTempPath(), Guid.NewGuid().ToString("N") + ".db"),
            });
            builder.Services.AddApplication().AddInfrastructure().AddTaxCreditRuntime(builder.Configuration);
            Assert.Equal("1", builder.Configuration.Setting("WORKER_ONCE"));
            using var host = builder.Build();
            var settings = host.Services.GetRequiredService<RuntimeConfiguration>();
            Assert.Equal("sqlite", settings.Get("PERSISTENCE_PROVIDER"));
            Assert.Equal("1", settings.Get("CONTRACT_HOOKS"));
            var text = error.ToString();
            Assert.Contains("TCC_CONTRACT_HOOKS", text, StringComparison.Ordinal);
            Assert.DoesNotContain("TCC_PERSISTENCE_PROVIDER", text, StringComparison.Ordinal);
        }
        finally
        {
            Console.SetError(original);
        }
    }
}
