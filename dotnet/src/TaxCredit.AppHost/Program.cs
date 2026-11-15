// Describes the local resources only; no cloud deployment (see ADR 0007).
var builder = DistributedApplication.CreateBuilder(args);

var sql = builder.AddSqlServer("sql");
var warehouse = sql.AddDatabase("tcc");

builder.AddProject<Projects.TaxCredit_Api>("api")
    .WithReference(warehouse)
    .WaitFor(warehouse);

await builder.Build().RunAsync();
