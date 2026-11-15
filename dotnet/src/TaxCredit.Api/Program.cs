using TaxCredit.Application;
using TaxCredit.Application.Messaging;
using TaxCredit.Application.Queries;
using TaxCredit.Infrastructure;
using TaxCredit.ServiceDefaults;

var builder = WebApplication.CreateBuilder(args);
builder.AddServiceDefaults();
builder.Services.AddApplication().AddInfrastructure();

var app = builder.Build();
app.MapDefaultEndpoints();

// Routers stay thin: parse, dispatch through the mediator, shape the response.
app.MapGet("/api/engine", async (IMediator mediator, CancellationToken ct) => await mediator.Send(new GetEngineInfoQuery(), ct));

await app.RunAsync();
