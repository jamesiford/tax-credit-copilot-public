using Microsoft.Extensions.DependencyInjection;
using TaxCredit.Domain.Pipeline;
using TaxCredit.Infrastructure.Persistence;
using TaxCredit.Infrastructure.Persistence.Sql;
using TaxCredit.ServiceDefaults.Hosting;

namespace TaxCredit.Api.Tests.DraftsRuns;

public sealed class ValidationMetadataTests
{
    [Fact]
    public async Task Run_metadata_counts_every_validation_query_that_the_selected_writer_executes()
    {
        await using var host = await TestHost.Start();
        var paths = host.App.Services.GetRequiredService<RuntimePaths>();
        var statements = new List<string>();
        var writer = new GoldWriter(PersistenceDatabase.Sqlite(paths.Database, statements.Add), Corpus.Root);
        Assert.Empty(writer.Validate());
        var executed = statements.Count(message => message == "tenant-exempt SQL: section-9 invariants span the store");
        using var scope = host.App.Services.CreateScope();
        var metadata = scope.ServiceProvider.GetRequiredService<ClientCalculationConfig>();
        Assert.Equal(executed, metadata.Section9QueryCount);
    }
}
