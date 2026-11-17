namespace TaxCredit.Api.Tests.WorkspaceSealed;

public sealed class WorkspaceTests
{
    [Theory]
    [InlineData("ok.get-api-workspace")]
    [InlineData("ok.post-api-workspace-refresh")]
    [InlineData("ok.post-api-workspace-source-search")]
    [InlineData("ok.post-api-workspace-employee")]
    [InlineData("ok.get-api-workspace-onezero-method")]
    [InlineData("ok.post-api-workspace-onezero-contributors")]
    [InlineData("ok.get-api-workspace-calculation-walk")]
    [InlineData("ok.get-api-workspace-comparison")]
    [InlineData("ok.post-api-workspace-comparison-stage")]
    public async Task The_missing_extract_answers_match_the_recordings(string id)
    {
        await using var host = await TestHost.Start();
        var recording = Corpus.Recording("p1_workspace_unavailable", id);
        using var request = Corpus.Request(recording);
        using var response = await host.Client.SendAsync(request);
        await Corpus.AssertJsonResponse(recording, response);
    }

    [Fact]
    public async Task Assumptions_returns_the_same_missing_dependency_family_instead_of_a_plaintext_500()
    {
        await using var host = await TestHost.Start();
        using var response = await host.Client.GetAsync("/api/workspace/assumptions");
        Assert.Equal(503, (int)response.StatusCode);
        Assert.Equal("application/json", response.Content.Headers.ContentType?.ToString());
        Assert.Contains("Reference workspace inputs missing", await response.Content.ReadAsStringAsync(), StringComparison.Ordinal);
    }
}
