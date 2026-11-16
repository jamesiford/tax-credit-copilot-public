using System.Text.Json;
using System.Text.Json.Nodes;

namespace TaxCredit.Api.Tests;

internal static class Corpus
{
    internal static string Root
    {
        get
        {
            var directory = new DirectoryInfo(AppContext.BaseDirectory);
            while (directory is not null && !Directory.Exists(Path.Combine(directory.FullName, "contract", "recordings")))
            {
                directory = directory.Parent;
            }

            return directory?.FullName ?? throw new DirectoryNotFoundException("Contract corpus is not above the test binary.");
        }
    }

    internal static JsonElement Read(string relative)
    {
        using var document = JsonDocument.Parse(File.ReadAllText(Path.Combine(Root, relative)));
        return document.RootElement.Clone();
    }

    internal static JsonElement Recording(string scenario, string id) => Recordings(scenario).Single(r => r.GetProperty("id").GetString() == id);

    internal static IEnumerable<JsonElement> Recordings(string scenario)
    {
        foreach (var line in File.ReadLines(Path.Combine(Root, "contract", "recordings", scenario + ".jsonl")))
        {
            using var document = JsonDocument.Parse(line);
            yield return document.RootElement.Clone();
        }
    }

    internal static HttpRequestMessage Request(JsonElement recording)
    {
        var request = recording.GetProperty("request");
        var query = request.GetProperty("query").GetString();
        var message = new HttpRequestMessage(new HttpMethod(request.GetProperty("method").GetString()!),
            request.GetProperty("path").GetString() + (string.IsNullOrEmpty(query) ? "" : "?" + query));
        var body = request.GetProperty("body");
        if (body.GetProperty("kind").GetString() == "json")
        {
            message.Content = new StringContent(body.GetProperty("value").GetRawText(), System.Text.Encoding.UTF8, "application/json");
        }
        else if (body.GetProperty("kind").GetString() == "text")
        {
            message.Content = new StringContent(body.GetProperty("text").GetString()!);
        }

        foreach (var header in request.GetProperty("headers").EnumerateObject())
        {
            if (!message.Headers.TryAddWithoutValidation(header.Name, header.Value.GetString()) && message.Content is not null)
            {
                message.Content.Headers.Remove(header.Name);
                message.Content.Headers.TryAddWithoutValidation(header.Name, header.Value.GetString());
            }
        }

        return message;
    }

    internal static async Task AssertJsonResponse(JsonElement recording, HttpResponseMessage response)
    {
        Assert.Equal(recording.GetProperty("response").GetProperty("status").GetInt32(), (int)response.StatusCode);
        Assert.Equal("application/json", response.Content.Headers.ContentType?.ToString());
        var expected = JsonNode.Parse(recording.GetProperty("response").GetProperty("body").GetProperty("value").GetRawText());
        var actual = JsonNode.Parse(await response.Content.ReadAsStringAsync());
        Assert.True(JsonNode.DeepEquals(expected, actual), $"Expected {expected}; actual {actual}");
    }
}
