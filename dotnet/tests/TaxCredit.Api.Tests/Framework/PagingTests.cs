using System.Net.Http.Json;
using System.Text.Json;
using Microsoft.Extensions.DependencyInjection;
using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Programs;

namespace TaxCredit.Api.Tests.Framework;

public sealed class PagingTests
{
    [Theory]
    [InlineData("9223372036854775807", 200)]
    [InlineData("9223372036854775808", 200)]
    [InlineData("999999999999999999999999999999999999999999", 200)]
    [InlineData("junk", 422)]
    [InlineData("-1", 422)]
    public async Task Paging_validation_is_not_a_storage_id_constraint(string offset, int status)
    {
        await using var host = await TestHost.Start(configuration: Configuration);
        var drafts = host.App.Services.GetRequiredService<IProgramDraftRepository>();
        var now = PyDateTime.FromIsoFormat("2026-01-15T12:00:00+00:00");
        drafts.Create(new ProgramDraft
        {
            DraftId = "paging",
            ProposedCode = "GA_PAGING",
            Name = "Synthetic paging",
            JurisdictionLevel = "state",
            State = "GA",
            Status = DraftStatus.Draft,
            Version = 1,
            CreatedBy = "fixture",
            UpdatedBy = "fixture",
            CreatedAt = now,
            UpdatedAt = now,
        }, new DraftEvent { DraftId = "paging", Seq = 1, EventType = "created", Actor = "fixture", At = now });
        using var response = await host.Client.GetAsync("/api/v2/program-drafts?offset=" + offset);
        Assert.Equal(status, (int)response.StatusCode);
        if (status == 200)
        {
            var body = await response.Content.ReadFromJsonAsync<JsonElement>();
            Assert.Equal(1, body.GetProperty("total").GetInt32());
            Assert.Empty(body.GetProperty("items").EnumerateArray());
        }
    }

    [Theory]
    [InlineData("99999999999999999999", 422)]
    [InlineData("9999", 404)]
    public async Task Storage_id_bounds_stay_separate_from_an_ordinary_unknown_client(string client, int status)
    {
        await using var host = await TestHost.Start(configuration: Configuration);
        using var response = await host.Client.GetAsync("/api/v2/clients/" + client + "/units");
        Assert.Equal(status, (int)response.StatusCode);
    }

    internal static readonly Dictionary<string, string?> Configuration = new(StringComparer.Ordinal)
    {
        ["FEATURE_ASSEMBLIES"] = typeof(DiscoveryFeature).Assembly.FullName,
    };
}
