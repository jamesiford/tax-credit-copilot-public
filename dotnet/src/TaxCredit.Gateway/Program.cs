using TaxCredit.Gateway;

await using var app = GatewayHost.Build(args);
await app.RunAsync().ConfigureAwait(false);
