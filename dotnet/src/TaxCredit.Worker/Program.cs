using TaxCredit.Application;
using TaxCredit.Application.Hosting;
using TaxCredit.Infrastructure;
using TaxCredit.ServiceDefaults;
using TaxCredit.ServiceDefaults.Hosting;
using TaxCredit.Worker;

var once = args.Contains("--once", StringComparer.Ordinal);
var builder = Host.CreateApplicationBuilder(args.Where(a => a != "--once").ToArray());
builder.AddServiceDefaults();
builder.Services.AddApplication().AddInfrastructure().AddTaxCreditRuntime(builder.Configuration);
if (once || builder.Configuration["WORKER_ONCE"] == "1")
{
    using var host = builder.Build();
    host.Services.GetRequiredService<RuntimeStatus>().Settle();
    using var lease = await host.Services.GetRequiredService<RunWorkGate>().Enter(CancellationToken.None);
    var count = await host.Services.GetRequiredService<RunWorkExecutor>().Drain(CancellationToken.None);
    Console.WriteLine(FormattableString.Invariant($"Processed {count} queue items."));
}
else
{
    builder.Services.AddHostedService<QueueWorker>();
    await builder.Build().RunAsync();
}
