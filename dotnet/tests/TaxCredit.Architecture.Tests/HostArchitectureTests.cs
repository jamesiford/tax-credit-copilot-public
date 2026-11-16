using System.Xml.Linq;

namespace TaxCredit.Architecture.Tests;

public sealed class HostArchitectureTests
{
    private static string Root
    {
        get
        {
            var current = new DirectoryInfo(AppContext.BaseDirectory);
            while (current is not null && !File.Exists(Path.Combine(current.FullName, "TaxCredit.slnx")))
            {
                current = current.Parent;
            }

            return current?.FullName ?? throw new DirectoryNotFoundException("Solution root not found.");
        }
    }

    [Fact]
    public void Api_references_application_adapters_and_service_defaults_but_not_domain_directly()
    {
        var api = XDocument.Load(Path.Combine(Root, "src", "TaxCredit.Api", "TaxCredit.Api.csproj"));
        var references = api.Descendants("ProjectReference").Select(p => Path.GetFileNameWithoutExtension(((string)p.Attribute("Include")!).Replace('\\', Path.DirectorySeparatorChar))).ToArray();
        Assert.Contains("TaxCredit.Application", references);
        Assert.DoesNotContain("TaxCredit.Domain", references);
        Assert.All(references, r => Assert.True(r is "TaxCredit.Application" or "TaxCredit.ServiceDefaults"
            || r.StartsWith("TaxCredit.Infrastructure", StringComparison.Ordinal)));
    }

    [Fact]
    public void Endpoint_groups_do_not_name_infrastructure_adapters()
    {
        var endpoints = Directory.GetFiles(Path.Combine(Root, "src", "TaxCredit.Api", "Endpoints"), "*.cs", SearchOption.AllDirectories);
        Assert.NotEmpty(endpoints);
        Assert.All(endpoints, path => Assert.DoesNotContain("TaxCredit.Infrastructure", File.ReadAllText(path), StringComparison.Ordinal));
    }

    [Fact]
    public void The_new_project_shells_are_inward_only_and_domain_remains_pure()
    {
        foreach (var name in new[] { "Persistence", "Sources", "Auth", "Ai" })
        {
            var project = XDocument.Load(Path.Combine(Root, "src", "TaxCredit.Infrastructure." + name, "TaxCredit.Infrastructure." + name + ".csproj"));
            Assert.All(project.Descendants("ProjectReference"), p =>
                Assert.DoesNotContain("TaxCredit.Api", (string)p.Attribute("Include")!, StringComparison.Ordinal));
        }

        var domain = XDocument.Load(Path.Combine(Root, "src", "TaxCredit.Domain", "TaxCredit.Domain.csproj"));
        Assert.Empty(domain.Descendants("PackageReference"));
        Assert.Empty(domain.Descendants("FrameworkReference"));
        Assert.Empty(domain.Descendants("ProjectReference"));
    }
}
