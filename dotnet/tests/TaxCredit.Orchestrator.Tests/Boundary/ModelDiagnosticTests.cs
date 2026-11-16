using System.Net;
using TaxCredit.Orchestrator.Boundary;
using static TaxCredit.Orchestrator.Tests.Boundary.DiagnosticTestSupport;

namespace TaxCredit.Orchestrator.Tests.Boundary;

public sealed class ModelDiagnosticTests
{
    private static DiagnosticOptions Options(TimeSpan? timeout = null) => new(new Dictionary<string, string?>
    {
        ["FOUNDRY_PROJECT_ENDPOINT"] = Project,
        ["AZURE_AI_MODEL_DEPLOYMENT_NAME"] = "synthetic-model",
    }, stepTimeout: timeout);

    [Fact]
    public async Task Model_success_exposes_only_metadata_and_strips_credentials_queries_and_fragments_from_base_uri()
    {
        var provider = new SafeDebugDiagnostics(Options(), new Probe(), (endpoint, model, _) =>
        {
            Assert.Equal(Project, endpoint.AbsoluteUri);
            Assert.Equal("synthetic-model", model);
            return Task.FromResult(new ModelProbeObservation(
                new Uri("https://user:secret@model.example/project/openai/v1/?api-key=secret#private"), 2));
        });
        var report = await provider.RunModelProbeAsync();
        Assert.True(report["ok"]!.GetValue<bool>());
        Assert.Equal(2, report["reply_chars"]!.GetValue<int>());
        Assert.Equal("synthetic-model", report["model"]!.GetValue<string>());
        Assert.Equal("aif-example.services.ai.azure.com", report["project_endpoint_host"]!.GetValue<string>());
        Assert.Equal("https://model.example/project/openai/v1/", report["base_url"]!.GetValue<string>());
        Assert.DoesNotContain("secret", report.ToJsonString(), StringComparison.Ordinal);
        Assert.DoesNotContain("private", report.ToJsonString(), StringComparison.Ordinal);
    }

    [Fact]
    public async Task Model_failure_reports_exception_and_cause_types_but_neither_exception_message()
    {
        var provider = new SafeDebugDiagnostics(Options(), new Probe(), (_, _, _) =>
            throw new InvalidOperationException("Bearer must-not-appear", new IOException("password=must-not-appear")));
        var report = await provider.RunModelProbeAsync();
        Assert.False(report["ok"]!.GetValue<bool>());
        Assert.Equal(nameof(InvalidOperationException), report["error"]!.GetValue<string>());
        Assert.Equal(nameof(IOException), report["cause"]!.GetValue<string>());
        Assert.DoesNotContain("must-not-appear", report.ToJsonString(), StringComparison.Ordinal);
    }

    [Fact]
    public async Task Missing_model_configuration_and_missing_probe_are_distinct_and_never_implicitly_call_a_model()
    {
        var missingConfig = await new SafeDebugDiagnostics(new DiagnosticOptions(EmptyEnvironment), new Probe())
            .RunModelProbeAsync();
        Assert.False(missingConfig["ok"]!.GetValue<bool>());
        Assert.Contains("not set", missingConfig["error"]!.GetValue<string>(), StringComparison.Ordinal);
        var missingProbe = await new SafeDebugDiagnostics(Options(), new Probe()).RunModelProbeAsync();
        Assert.False(missingProbe["ok"]!.GetValue<bool>());
        Assert.Equal("model_probe_not_configured", missingProbe["error"]!.GetValue<string>());
    }

    [Fact]
    public async Task A_model_adapter_that_ignores_cancellation_still_cannot_exceed_its_budget()
    {
        var provider = new SafeDebugDiagnostics(Options(TimeSpan.FromMilliseconds(30)), new Probe(), (_, _, _) =>
            new TaskCompletionSource<ModelProbeObservation>().Task);
        var report = await provider.RunModelProbeAsync();
        Assert.False(report["ok"]!.GetValue<bool>());
        Assert.Equal("timeout", report["error"]!.GetValue<string>());
    }

    [Fact]
    public async Task Model_caller_cancellation_propagates()
    {
        using var cancellation = new CancellationTokenSource();
        var provider = new SafeDebugDiagnostics(Options(), new Probe(), (_, _, _) =>
        {
            cancellation.Cancel();
            return Task.FromCanceled<ModelProbeObservation>(cancellation.Token);
        });
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => provider.RunModelProbeAsync(cancellation.Token));
    }

    [Theory]
    [InlineData(-1)]
    [InlineData(1_000_001)]
    public async Task Invalid_model_metadata_is_not_reported_as_success(int count)
    {
        var report = await new SafeDebugDiagnostics(Options(), new Probe(), (_, _, _) =>
            Task.FromResult(new ModelProbeObservation(null, count))).RunModelProbeAsync();
        Assert.False(report["ok"]!.GetValue<bool>());
        Assert.Equal("invalid_probe_metadata", report["error"]!.GetValue<string>());
        Assert.Null(report["reply_chars"]);
    }

    [Fact]
    public async Task System_http_probe_uses_an_unauthenticated_get_and_never_reads_or_reports_the_body()
    {
        using var handler = new GatewayTestSupport.Handler((request, _) =>
        {
            Assert.Equal(HttpMethod.Get, request.Method);
            Assert.Null(request.Headers.Authorization);
            Assert.False(request.Headers.Contains("Cookie"));
            return Task.FromResult(new HttpResponseMessage(HttpStatusCode.Unauthorized)
            {
                Content = new UnreadableContent(),
            });
        });
        using var probe = new SystemDiagnosticNetworkProbe(handler);
        Assert.Equal(401, await probe.HttpGetStatusAsync(new Uri("https://configured.example/openai/v1/models"), CancellationToken.None));
        Assert.Equal(1, handler.Calls);
    }

    [Theory]
    [InlineData("http://insecure.example")]
    [InlineData("https://user:password@configured.example")]
    public async Task System_http_probe_rejects_unsafe_targets_without_dispatch(string uri)
    {
        using var handler = new GatewayTestSupport.Handler((_, _) => throw new InvalidOperationException("must not dispatch"));
        using var probe = new SystemDiagnosticNetworkProbe(handler);
        await Assert.ThrowsAsync<ArgumentException>(() => probe.HttpGetStatusAsync(new Uri(uri), CancellationToken.None));
        Assert.Equal(0, handler.Calls);
    }
}
