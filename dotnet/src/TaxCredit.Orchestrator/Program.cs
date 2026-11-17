extern alias AzureIdentity;

using TaxCredit.Orchestrator.Hosting;
using DefaultAzureCredential = AzureIdentity::Azure.Identity.DefaultAzureCredential;

var settings = new RuntimeSettings(new ConfigurationBuilder().AddEnvironmentVariables().Build());
using var logging = LoggerFactory.Create(builder => builder.AddSimpleConsole());
using var runtime = new OrchestratorRuntime(settings, new DefaultAzureCredential(), logging);
await using var app = ResponsesHosting.Build(args, runtime.Host);
await app.RunAsync();
