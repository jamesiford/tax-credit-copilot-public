using System.Net.Sockets;
using TaxCredit.Orchestrator.Boundary;
using static TaxCredit.Orchestrator.Tests.Boundary.DiagnosticTestSupport;

namespace TaxCredit.Orchestrator.Tests.Boundary;

public sealed class NetcheckTests
{
    [Theory]
    [InlineData("10.1.2.3", "private")]
    [InlineData("20.1.2.3", "public")]
    [InlineData("127.0.0.1", "loopback")]
    [InlineData("169.254.1.1", "link-local")]
    [InlineData("fd00::1", "private")]
    [InlineData("::1", "loopback")]
    [InlineData("fe80::1", "link-local")]
    [InlineData("::ffff:10.1.2.3", "private")]
    [InlineData("::ffff:20.1.2.3", "public")]
    [InlineData("192.0.0.9", "public")]
    [InlineData("192.0.0.10", "public")]
    [InlineData("192.0.0.11", "private")]
    [InlineData("2001:3::1", "public")]
    [InlineData("2001:db8::1", "private")]
    [InlineData("not-an-address", "invalid")]
    public void Address_classification_matches_source_including_special_exceptions(string address, string expected) =>
        Assert.Equal(expected, DiagnosticMetadata.Classify(address));

    [Fact]
    public async Task Resolve_failure_stops_that_host_before_connect_and_sanitizes_exception_details()
    {
        var probe = new Probe { Resolve = (_, _) => throw new SocketException() };
        var first = FirstTarget(await Diagnostics(probe).RunNetcheckAsync());
        Assert.Equal(nameof(SocketException), first["resolve"]!.GetValue<string>());
        Assert.Null(first["tcp"]);
        Assert.All(probe.Calls, call => Assert.StartsWith("resolve:", call, StringComparison.Ordinal));
    }

    [Fact]
    public async Task Tcp_failure_preserves_private_classification_and_stops_before_tls()
    {
        var probe = new Probe
        {
            Resolve = (_, _) => Task.FromResult<IReadOnlyList<string>>(["10.0.0.4"]),
            Connect = (_, _) => throw new TimeoutException("credential=must-not-appear"),
        };
        var first = FirstTarget(await Diagnostics(probe).RunNetcheckAsync());
        Assert.Equal("private", first["resolved"]![0]!["kind"]!.GetValue<string>());
        Assert.False(first["tcp"]!["ok"]!.GetValue<bool>());
        Assert.Equal(nameof(TimeoutException), first["tcp"]!["error"]!.GetValue<string>());
        Assert.Null(first["tls_get_status"]);
        Assert.DoesNotContain("must-not-appear", first.ToJsonString(), StringComparison.Ordinal);
    }

    [Fact]
    public async Task Tls_and_http_client_results_are_independent_and_do_not_return_response_bodies()
    {
        var probe = new Probe { Http = (_, _) => throw new HttpRequestException("Bearer must-not-appear") };
        var first = FirstTarget(await Diagnostics(probe).RunNetcheckAsync());
        Assert.True(first["tcp"]!["ok"]!.GetValue<bool>());
        Assert.Equal(404, first["tls_get_status"]!.GetValue<int>());
        Assert.Equal(nameof(HttpRequestException), first["http_client_status"]!.GetValue<string>());
        Assert.DoesNotContain("must-not-appear", first.ToJsonString(), StringComparison.Ordinal);
    }

    [Fact]
    public async Task Tls_failure_does_not_skip_the_independent_http_client_check()
    {
        var probe = new Probe { Tls = (_, _, _) => throw new IOException("private handshake detail") };
        var first = FirstTarget(await Diagnostics(probe).RunNetcheckAsync());
        Assert.Equal(nameof(IOException), first["tls_get_status"]!.GetValue<string>());
        Assert.Equal(401, first["http_client_status"]!.GetValue<int>());
    }

    [Fact]
    public async Task Addresses_are_bounded_deduplicated_and_ipv4_is_preferred_without_echoing_invalid_values()
    {
        var probe = new Probe
        {
            Resolve = (_, _) => Task.FromResult<IReadOnlyList<string>>(
                ["invalid-secret", "::1", "10.0.0.4", "10.0.0.4", .. Enumerable.Range(1, 100).Select(value => "20.1.1." + value)]),
        };
        var first = FirstTarget(await Diagnostics(probe).RunNetcheckAsync());
        Assert.Equal(16, first["resolved"]!.AsArray().Count);
        Assert.Equal("10.0.0.4", first["tcp"]!["address"]!.GetValue<string>());
        Assert.DoesNotContain("invalid-secret", first.ToJsonString(), StringComparison.Ordinal);
    }

    [Fact]
    public async Task Empty_dns_results_stop_before_connect()
    {
        var probe = new Probe { Resolve = (_, _) => Task.FromResult<IReadOnlyList<string>>([]) };
        var first = FirstTarget(await Diagnostics(probe).RunNetcheckAsync());
        Assert.Equal("no addresses", first["resolve"]!.GetValue<string>());
        Assert.Null(first["tcp"]);
    }

    [Fact]
    public void Account_hosts_derive_the_three_source_targets_and_invalid_configuration_adds_nothing()
    {
        Assert.Equal(new[]
        {
            "aif-example.services.ai.azure.com", "aif-example.openai.azure.com", "aif-example.cognitiveservices.azure.com",
        }, DiagnosticMetadata.AccountHosts(Project).Select(target => target.Host));
        Assert.Empty(DiagnosticMetadata.AccountHosts("not a url"));
        Assert.Empty(DiagnosticMetadata.AccountHosts("https://user:secret@host.example"));
        Assert.Empty(DiagnosticMetadata.AccountHosts("https://host.example?token=secret"));
    }

    [Fact]
    public async Task Full_report_has_every_target_safe_environment_projection_and_no_proxy_credentials()
    {
        var environment = new Dictionary<string, string?>
        {
            ["FOUNDRY_MODEL"] = "synthetic-model",
            ["FOUNDRY_TOKEN_THING"] = "must-not-appear",
            ["AI_PROVIDER_CHAIN"] = "foundry",
            ["HTTPS_PROXY"] = "http://user:password@proxy.example",
            ["CHANNEL_GATEWAY_AUDIENCE"] = "api://not-shown",
            ["UNRELATED"] = "not shown",
        };
        var options = new DiagnosticOptions(environment, Project, "https://gateway.example", ["foundry"]);
        environment["FOUNDRY_MODEL"] = "mutated-after-snapshot";
        var report = await new SafeDebugDiagnostics(options, new Probe()).RunNetcheckAsync();
        Assert.Equal(new[] { "gateway.example", "login.microsoftonline.com", "www.microsoft.com" },
            report["targets"]!.AsArray().TakeLast(3).Select(target => target!["host"]!.GetValue<string>()));
        Assert.Equal("synthetic-model", report["environment"]!["values"]!["FOUNDRY_MODEL"]!.GetValue<string>());
        Assert.Equal("HTTPS_PROXY", report["environment"]!["proxy_variables_set"]![0]!.GetValue<string>());
        Assert.Contains("FOUNDRY_TOKEN_THING", report["environment"]!["names"]!.ToJsonString(), StringComparison.Ordinal);
        var text = report.ToJsonString();
        foreach (var forbidden in new[] { "must-not-appear", "password@", "api://not-shown", "UNRELATED", "mutated-after-snapshot" })
        {
            Assert.DoesNotContain(forbidden, text, StringComparison.Ordinal);
        }
    }

    [Fact]
    public async Task Total_budget_bounds_an_uncooperative_probe_and_returns_partial_timeout_evidence()
    {
        var clock = new DiagnosticClock();
        var probe = new Probe { Resolve = (_, _) => new TaskCompletionSource<IReadOnlyList<string>>().Task };
        var provider = new SafeDebugDiagnostics(new DiagnosticOptions(EmptyEnvironment, gatewayUrl: "https://target.example",
            stepTimeout: TimeSpan.FromSeconds(1), totalTimeout: TimeSpan.FromMilliseconds(30)), probe, timeProvider: clock);
        var pending = provider.RunNetcheckAsync();
        Assert.Single(probe.Calls);
        clock.Advance(TimeSpan.FromMilliseconds(30));
        var report = await pending;
        Assert.Equal("timeout", report["error"]!.GetValue<string>());
        Assert.Equal("timeout", FirstTarget(report)["resolve"]!.GetValue<string>());
        Assert.Single(probe.Calls);
    }

    [Fact]
    public async Task Elapsed_total_budget_stops_new_operations_even_when_timer_callbacks_are_delayed()
    {
        var clock = new DiagnosticClock();
        var probe = new Probe
        {
            Resolve = (_, _) =>
            {
                clock.Advance(TimeSpan.FromMilliseconds(31), fireTimers: false);
                return Task.FromResult<IReadOnlyList<string>>(["20.1.1.1"]);
            },
        };
        var provider = new SafeDebugDiagnostics(new DiagnosticOptions(EmptyEnvironment, gatewayUrl: "https://target.example",
            totalTimeout: TimeSpan.FromMilliseconds(30)), probe, timeProvider: clock);
        var report = await provider.RunNetcheckAsync();
        Assert.Equal("timeout", report["error"]!.GetValue<string>());
        Assert.Equal("timeout", FirstTarget(report)["tcp"]!["error"]!.GetValue<string>());
        Assert.Single(probe.Calls);
    }

    [Fact]
    public async Task Caller_cancellation_propagates_instead_of_being_a_diagnostic_failure()
    {
        using var cancel = new CancellationTokenSource();
        var probe = new Probe
        {
            Resolve = (_, _) =>
            {
                cancel.Cancel();
                return Task.FromCanceled<IReadOnlyList<string>>(cancel.Token);
            },
        };
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => Diagnostics(probe).RunNetcheckAsync(cancel.Token));
    }
}
