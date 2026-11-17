using System.Text.Json.Nodes;
using TaxCredit.Application.Ports.Ai;
using TaxCredit.Infrastructure.Ai.Agents;

namespace TaxCredit.Api.Tests.Ai.Agents;

public sealed class AgentPromptTests
{
    [Fact]
    public void Packaged_roster_matches_all_twelve_original_specs_and_current_manifest()
    {
        var roster = AgentRoster.Load();
        var reference = AgentRoster.Load(new DirectoryAgentResources(Path.Combine(Corpus.Root, "backend", "agents")));
        Assert.Equal(12, roster.Agents.Count);
        Assert.Equal(reference.Agents, roster.Agents);
        Assert.Equal(12, roster.Prompts.Count);
        Assert.Empty(roster.Manifest.Check(roster.Prompts));
        Assert.Equal([ModelRole.Router, ModelRole.Narrator, ModelRole.Analysis], roster.Agents.Select(a => a.Role).Distinct());
        foreach (var (spec, original) in roster.Specs.Zip(reference.Specs))
        {
            Assert.Equal(original.Name, spec.Name);
            Assert.Equal(original.Instructions, spec.Instructions);
            Assert.Equal(original.Role, spec.Role);
            Assert.Equal(original.Temperature, spec.Temperature);
            Assert.Equal(original.Version, spec.Version);
        }

        Assert.All(roster.Agents, declaration => Assert.Empty(declaration.Tools));
        Assert.Equal(4, roster.Prompts["channel_narrator"].Version);
        Assert.Equal(4, roster.Manifest.History["channel_narrator"].Count);
        Assert.Equal("2f90a56fa35f616a533a920bcaccf1a09d8da2f61ab39f77d1209b4a08afee71",
            roster.Manifest.History["channel_narrator"][1]);
    }

    [Fact]
    public void Mutation_without_a_version_bump_is_refused()
    {
        var resources = new ChangedResources();
        resources.Values["reporting.md"] = resources.Read("reporting.md") + "Changed instructions.\n";
        var error = Assert.Throws<InvalidDataException>(() => AgentRoster.Load(resources));
        Assert.Contains("text changed but version 1 did not", error.Message, StringComparison.Ordinal);
    }

    [Fact]
    public void A_historical_hash_cannot_validate_current_instructions()
    {
        var resources = new ChangedResources();
        var manifest = JsonNode.Parse(resources.Read("manifest.json"))!;
        manifest["prompts"]!["channel_narrator"]!["versions"]!["4"] =
            manifest["prompts"]!["channel_narrator"]!["versions"]!["3"]!.GetValue<string>();
        resources.Values["manifest.json"] = manifest.ToJsonString();
        Assert.Throws<InvalidDataException>(() => AgentRoster.Load(resources));
    }

    [Fact]
    public void A_valid_hash_at_an_older_version_is_still_refused()
    {
        var resources = new ChangedResources();
        var raw = resources.Read("channel_narrator.md").Replace("version: 4\n", "version: 3\n", StringComparison.Ordinal);
        resources.Values["channel_narrator.md"] = raw;
        var manifest = JsonNode.Parse(resources.Read("manifest.json"))!;
        manifest["prompts"]!["channel_narrator"]!["versions"]!["3"] = VersionedPrompt.Parse("channel_narrator", raw).Sha256;
        resources.Values["manifest.json"] = manifest.ToJsonString();
        var error = Assert.Throws<InvalidDataException>(() => AgentRoster.Load(resources));
        Assert.Contains("older than a recorded version", error.Message, StringComparison.Ordinal);
    }

    [Theory]
    [InlineData("version: 1", "version: 2", "version 2 is not in the manifest")]
    [InlineData("  - \"1:", "  - \"7:", "changelog has no line")]
    public void Version_bumps_require_recording_and_current_changelog(string oldText, string newText, string message)
    {
        var resources = new ChangedResources();
        resources.Values["reporting.md"] = resources.Read("reporting.md").Replace(oldText, newText, StringComparison.Ordinal);
        var error = Assert.Throws<InvalidDataException>(() => AgentRoster.Load(resources));
        Assert.Contains(message, error.Message, StringComparison.Ordinal);
    }

    [Fact]
    public void Missing_or_unlisted_prompt_files_are_refused()
    {
        var resources = new ChangedResources();
        resources.Names.Remove("reporting");
        Assert.Throws<InvalidDataException>(() => AgentRoster.Load(resources));
        resources.Names.Add("reporting");
        resources.Names.Add("stray");
        resources.Values["stray.md"] = resources.Read("reporting.md");
        Assert.Throws<InvalidDataException>(() => AgentRoster.Load(resources));
    }

    [Theory]
    [InlineData("role", "\"oracle\"")]
    [InlineData("temperature", "true")]
    [InlineData("temperature", "3")]
    [InlineData("temperature", "\"0.2\"")]
    [InlineData("tools", "[\"calculate\"]")]
    [InlineData("name", "\"ReportingAgent\"")]
    [InlineData("module", "\"reporting\"")]
    [InlineData("prompt", "\"reporting\"")]
    [InlineData("name", "\"\"")]
    [InlineData("model", "\"deployment\"")]
    public void Invalid_roster_never_exposes_a_partially_publishable_estate(string field, string json)
    {
        var resources = new ChangedResources();
        var roster = JsonNode.Parse(resources.Read("roster.json"))!;
        roster["agents"]![0]![field] = JsonNode.Parse(json);
        resources.Values["roster.json"] = roster.ToJsonString();
        Assert.Throws<InvalidDataException>(() => AgentRoster.Load(resources));
    }

    [Fact]
    public void Parse_normalizes_CRLF_but_preserves_body_whitespace_and_unicode()
    {
        const string raw = "---\nversion: 1\nowner: product\nchangelog:\n  - \"1: initial\"\n---\n  Exact — £ text.  \n\n";
        var prompt = VersionedPrompt.Parse("sample", raw);
        Assert.Equal("  Exact — £ text.  \n\n", prompt.Text);
        Assert.Equal(prompt, VersionedPrompt.Parse("sample", raw.Replace("\n", "\r\n", StringComparison.Ordinal)));
        Assert.NotEqual(prompt.Sha256, VersionedPrompt.Hash(prompt.Text.Trim()));
        Assert.Throws<InvalidDataException>(() => VersionedPrompt.Parse("sample", "\uFEFF" + raw));
        Assert.Throws<InvalidDataException>(() => VersionedPrompt.Parse("sample", "---\nversion: 1\nowner: p\n---\n \n"));
    }

    [Fact]
    public void Packaged_resources_are_assembly_embedded_and_file_loading_requires_an_explicit_absolute_base()
    {
        Assert.Contains("TaxCredit.Infrastructure.Ai.Agents.Resources.Prompts.resources",
            typeof(PackagedAgentResources).Assembly.GetManifestResourceNames());
        Assert.Throws<ArgumentException>(() => new DirectoryAgentResources("backend"));
        var source = new DirectoryAgentResources(Path.Combine(Corpus.Root, "backend", "agents"));
        Assert.Throws<InvalidDataException>(() => source.Read("..\\agents.json"));
    }

    internal sealed class ChangedResources : IAgentResources
    {
        private readonly PackagedAgentResources _source = new();
        internal Dictionary<string, string> Values { get; } = new(StringComparer.Ordinal);
        internal List<string> Names { get; } = [.. new PackagedAgentResources().PromptNames];
        public string Read(string name) => Values.TryGetValue(name, out var value) ? value : _source.Read(name);
        public IReadOnlyList<string> PromptNames => Names;
    }
}
