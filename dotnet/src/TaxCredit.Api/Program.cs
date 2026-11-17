using TaxCredit.Api.Hosting;

var builder = WebApplication.CreateBuilder(args);
builder.AddSkeletonHost();

var app = builder.Build();
app.MapSkeletonHost();

await app.RunAsync();
