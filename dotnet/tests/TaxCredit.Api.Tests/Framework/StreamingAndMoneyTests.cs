using System.Text.Json;
using Microsoft.AspNetCore.Builder;
using TaxCredit.Api.Wire;
using TaxCredit.Domain.Numerics;

namespace TaxCredit.Api.Tests.Framework;

public sealed class StreamingAndMoneyTests
{
    [Fact]
    public void Money_keeps_the_recorded_decimal_scale_and_null_fields()
    {
        var options = new JsonSerializerOptions();
        WireJson.Configure(options);
        var records = Corpus.Recordings("p1_writes").Where(r => r.GetProperty("id").GetString()!.StartsWith("claims.create-money-", StringComparison.Ordinal)).ToArray();
        Assert.NotEmpty(records);
        foreach (var record in records)
        {
            var expected = record.GetProperty("response").GetProperty("body").GetProperty("value");
            var money = expected.GetProperty("claimed_usd").GetString()!;
            var json = JsonSerializer.SerializeToElement(new { claimed_usd = PyDecimal.Parse(money), missing = (object?)null }, options);
            Assert.Equal(money, json.GetProperty("claimed_usd").GetString());
            Assert.Equal(JsonValueKind.Null, json.GetProperty("missing").ValueKind);
        }

        Assert.Equal("\"1234.50\"", JsonSerializer.Serialize(1234.50m, options));
        Assert.Equal("5", JsonSerializer.Serialize(5.0, options));
    }

    [Fact]
    public async Task Event_frames_preserve_the_recorded_names_and_data_in_order()
    {
        var recording = Corpus.Recordings("p1_artifacts_ai").First(r => r.GetProperty("response").GetProperty("body").GetProperty("kind").GetString() == "sse");
        var events = recording.GetProperty("response").GetProperty("body").GetProperty("events").EnumerateArray().ToArray();
        await using var host = await TestHost.Start(routes: app => app.MapGet("/__tests__/stream", () => new EventStream(Frames(events))));
        using var response = await host.Client.GetAsync("/__tests__/stream");
        Assert.Equal("text/event-stream", response.Content.Headers.ContentType?.ToString());
        Assert.Equal("no-cache", response.Headers.CacheControl?.ToString());
        Assert.Equal("no", Assert.Single(response.Headers.GetValues("X-Accel-Buffering")));
        var frames = (await response.Content.ReadAsStringAsync()).Split("\n\n", StringSplitOptions.RemoveEmptyEntries);
        Assert.Equal(events.Length, frames.Length);
        for (var i = 0; i < events.Length; i++)
        {
            var lines = frames[i].Split('\n');
            Assert.Equal("event: " + events[i].GetProperty("event").GetString(), lines[0]);
            using var data = JsonDocument.Parse(lines[1]["data: ".Length..]);
            Assert.True(JsonElement.DeepEquals(events[i].GetProperty("data"), data.RootElement));
        }
    }

    private static async IAsyncEnumerable<StreamEvent> Frames(JsonElement[] events)
    {
        foreach (var frame in events)
        {
            yield return new StreamEvent(frame.GetProperty("event").GetString()!, frame.GetProperty("data"));
            await Task.Yield();
        }
    }
}
