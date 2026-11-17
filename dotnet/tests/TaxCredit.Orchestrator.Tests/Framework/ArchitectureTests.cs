using System.Reflection;
using System.Xml.Linq;
using TaxCredit.Application.Features.Ai.Capabilities;
using TaxCredit.Orchestrator.Framework;
using TaxCredit.Orchestrator.Turns;

namespace TaxCredit.Orchestrator.Tests.Framework;

public sealed class ArchitectureTests
{
    [Fact]
    public void The_executable_references_shared_ports_and_defaults_not_a_vendored_backend()
    {
        var project = XDocument.Load(Path.Combine(Root(), "dotnet", "src", "TaxCredit.Orchestrator", "TaxCredit.Orchestrator.csproj"));
        var references = project.Descendants("ProjectReference").Select(item => item.Attribute("Include")!.Value).ToArray();
        Assert.Equal(["..\\TaxCredit.Application\\TaxCredit.Application.csproj", "..\\TaxCredit.ServiceDefaults\\TaxCredit.ServiceDefaults.csproj"], references);
        Assert.Empty(Directory.GetFiles(Source(), "*.py", SearchOption.AllDirectories));
        Assert.DoesNotContain(typeof(CapabilityCatalog).Assembly.GetReferencedAssemblies(),
            reference => reference.Name!.StartsWith("TaxCredit.Orchestrator", StringComparison.Ordinal) ||
                reference.Name.StartsWith("Microsoft.Agents.AI", StringComparison.Ordinal) ||
                reference.Name.StartsWith("Azure.AI.AgentServer", StringComparison.Ordinal));
    }

    [Theory]
    [InlineData("using Azure.AI.AgentServer.", "Hosting")]
    [InlineData("using Microsoft.Agents.AI.Workflows", "Workflow")]
    [InlineData("using Microsoft.Agents.AI;", "Framework")]
    [InlineData("using OpenAI;", "Framework")]
    public void Actual_vendor_hosting_and_agent_dependencies_stay_in_their_outer_adapters(string dependency, string folder)
    {
        var files = Directory.GetFiles(Source(), "*.cs", SearchOption.AllDirectories)
            .Where(file => File.ReadAllText(file).Contains(dependency, StringComparison.Ordinal)).ToArray();
        Assert.NotEmpty(files);
        Assert.All(files, file => Assert.StartsWith(folder + Path.DirectorySeparatorChar,
            Path.GetRelativePath(Source(), file), StringComparison.Ordinal));
    }

    [Fact]
    public void Singleton_tool_definitions_hold_no_verified_reader_selection_or_workflow_state()
    {
        var catalog = new ModelToolCatalog(new CapabilityCatalog());
        var forbidden = new[] { typeof(IToolExecution), typeof(ConversationState), typeof(ConversationStore) };
        foreach (var tool in catalog.Definitions)
        {
            var fields = tool.GetType().GetFields(BindingFlags.Instance | BindingFlags.NonPublic | BindingFlags.Public | BindingFlags.DeclaredOnly);
            Assert.All(fields, field =>
            {
                Assert.DoesNotContain(forbidden, type => type.IsAssignableFrom(field.FieldType));
                Assert.DoesNotContain("ActingIdentity", field.FieldType.Name, StringComparison.Ordinal);
                Assert.DoesNotContain("Checkpoint", field.FieldType.Name, StringComparison.Ordinal);
            });
        }
    }

    [Fact]
    public void The_root_pins_net10_and_all_orchestrator_modules_stay_within_the_documented_size_limit()
    {
        var properties = XDocument.Load(Path.Combine(Root(), "dotnet", "Directory.Build.props"));
        Assert.Equal("net10.0", properties.Descendants("TargetFramework").Single().Value);
        Assert.All(Directory.GetFiles(Source(), "*.cs", SearchOption.AllDirectories),
            file => Assert.True(File.ReadLines(file).Count() <= 250, Path.GetFileName(file)));
    }

    private static string Source() => Path.Combine(Root(), "dotnet", "src", "TaxCredit.Orchestrator");
    private static string Root()
    {
        var current = new DirectoryInfo(AppContext.BaseDirectory);
        while (current is not null && !Directory.Exists(Path.Combine(current.FullName, "contract"))) { current = current.Parent; }
        Assert.NotNull(current);
        return current.FullName;
    }
}
