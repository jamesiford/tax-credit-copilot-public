using System.Globalization;
using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;

namespace TaxCredit.Infrastructure.Ai.Agents;

/// <summary>Instruction text is untrimmed: whitespace changes immutable provider definitions.</summary>
public sealed partial record VersionedPrompt(string Name, int Version, string Owner, string Text, string Sha256)
{
    internal string Header { get; init; } = "";

    /// <summary>Matches Python parse_prompt: CRLF normalizes, the trailing body newline survives.</summary>
    public static VersionedPrompt Parse(string name, string raw)
    {
        ArgumentNullException.ThrowIfNull(raw);
        var match = FrontMatter().Match(raw.Replace("\r\n", "\n", StringComparison.Ordinal));
        if (!match.Success)
        {
            throw new InvalidDataException("A prompt must start with a front matter block.");
        }

        var header = match.Groups["head"].Value;
        var fields = header.Split('\n')
            .Where(line => line.Contains(':', StringComparison.Ordinal) && !line.StartsWith(' ') && !line.StartsWith('-'))
            .Select(line => line.Split(':', 2))
            .ToDictionary(parts => parts[0], parts => parts[1].Trim(), StringComparer.Ordinal);
        if (!fields.TryGetValue("version", out var version) ||
            !int.TryParse(version, NumberStyles.Integer, CultureInfo.InvariantCulture, out var number) ||
            !fields.TryGetValue("owner", out var owner))
        {
            throw new InvalidDataException("Prompt front matter needs an integer version and an owner.");
        }

        var text = match.Groups["body"].Value;
        if (string.IsNullOrWhiteSpace(text))
        {
            throw new InvalidDataException("The prompt body is empty.");
        }

        return new(name, number, owner, text, Hash(text)) { Header = header };
    }

    /// <summary>UTF-8 instruction-body hash, not the Markdown-file hash.</summary>
    public static string Hash(string text) => Convert.ToHexStringLower(SHA256.HashData(Encoding.UTF8.GetBytes(text)));

    internal bool HasChangelog => Changelog().Matches(Header)
        .Any(match => int.Parse(match.Groups[1].Value, CultureInfo.InvariantCulture) == Version);

    [GeneratedRegex(@"\A---\n(?<head>.*?)\n---\n(?<body>.*)\z", RegexOptions.Singleline)]
    private static partial Regex FrontMatter();

    [GeneratedRegex("^\\s+-\\s+\"?(\\d+):", RegexOptions.Multiline)]
    private static partial Regex Changelog();
}
