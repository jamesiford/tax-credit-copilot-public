using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Text;
using System.Text.Json;
using TaxCredit.Api.Tests.Framework;

namespace TaxCredit.Api.Tests.Contract;

internal static class RuntimeRequests
{
    internal const string Reader = "00000000-0000-0000-0000-0000000000a1";
    internal const string Writer = "00000000-0000-0000-0000-0000000000a2";

    internal static Task<TestHost> Start() => TestHost.Start(configuration: new Dictionary<string, string?>(PagingTests.Configuration)
    {
        ["AUTH_MODE"] = "entra",
        ["CHANNEL_ENFORCE_WRITER_FOR_USERS"] = "true",
    });

    internal static async Task Reset(TestHost host, string profile = "P1")
    {
        using var response = await host.Client.PostAsJsonAsync("/__contract__/reset?profile=" + profile, new { });
        Assert.Equal(200, (int)response.StatusCode);
    }

    internal static async Task<string> Mint(TestHost host, object specification)
    {
        using var response = await host.Client.PostAsJsonAsync("/__contract__/mint", specification);
        Assert.Equal(200, (int)response.StatusCode);
        return (await response.Content.ReadFromJsonAsync<JsonElement>()).GetProperty("token").GetString()!;
    }

    internal static async Task Env(TestHost host, object set)
    {
        using var content = new StringContent(JsonSerializer.Serialize(new { set }), Encoding.UTF8, "application/json");
        using var response = await host.Client.PostAsync("/__contract__/env", content);
        Assert.Equal(200, (int)response.StatusCode);
    }

    internal static Task<HttpResponseMessage> Send(TestHost host, string token, string path = "/api/v2/clients/1001/units",
        HttpMethod? method = null, object? body = null, string? acting = null)
    {
        var request = new HttpRequestMessage(method ?? HttpMethod.Get, path);
        request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", token);
        if (body is not null) { request.Content = JsonContent.Create(body); }
        if (acting is not null) { request.Headers.Add("X-TCC-Acting-User", acting); }
        return host.Client.SendAsync(request);
    }

    internal static string Acting(string oid = Writer) => Convert.ToBase64String(Encoding.UTF8.GetBytes(JsonSerializer.Serialize(new
    {
        oid,
        tid = "00000000-0000-0000-0000-0000000000aa",
        name = "Synthetic actor",
        upn = "actor@example.test",
        channel = "api-test",
        assurance = "channel-asserted",
    })));
}
