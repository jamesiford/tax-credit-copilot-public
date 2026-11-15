using System.Reflection;
using System.Xml.Linq;
using TaxCredit.Domain.Numerics;
using AppDi = TaxCredit.Application.DependencyInjection;
using InMemoryAuditLog = TaxCredit.Infrastructure.InMemoryAuditLog;
using ServiceExtensions = TaxCredit.ServiceDefaults.Extensions;

namespace TaxCredit.Architecture.Tests;

/// <summary>
/// The layering rules, enforced as tests (mirrors Python <c>tests/test_architecture.py</c>):
/// <c>Api -> Application -> Domain</c>; <c>Infrastructure</c> implements Application's ports; Domain is the BCL only.
/// Checked twice: against the project files (what is declared) and against the compiled assemblies (what is used).
/// </summary>
public sealed class LayeringTests
{
    private static readonly string[] BclPrefixes = ["System", "netstandard", "mscorlib"];

    private static readonly string[] ForbiddenInDomain =
        ["System.Net", "System.Data", "System.IO.FileSystem", "System.Diagnostics.Process", "System.Threading.Tasks.Dataflow", "System.Private.Uri"];

    private static string SolutionDirectory { get; } = FindSolutionDirectory();

    private static string FindSolutionDirectory()
    {
        var dir = new DirectoryInfo(AppContext.BaseDirectory);
        while (dir is not null && !File.Exists(Path.Combine(dir.FullName, "TaxCredit.slnx")))
        {
            dir = dir.Parent;
        }

        return dir?.FullName ?? throw new DirectoryNotFoundException("TaxCredit.slnx not found above the test binary.");
    }

    private static XDocument Project(string name) => XDocument.Load(Path.Combine(SolutionDirectory, "src", name, name + ".csproj"));

    private static List<string> Items(string project, string element, string attribute = "Include") =>
        Project(project).Descendants(element).Select(e => (string?)e.Attribute(attribute)).Where(v => v is not null).Select(v => v!).ToList();

    private static List<string> ProjectRefs(string project) =>
        Items(project, "ProjectReference").Select(p => Path.GetFileNameWithoutExtension(p.Replace('\\', '/'))).ToList();

    /// <summary>Referenced assembly names that violate <paramref name="isAllowed"/>.</summary>
    internal static IReadOnlyList<string> Violations(IEnumerable<string> references, Func<string, bool> isAllowed) =>
        references.Where(r => !isAllowed(r)).Distinct().Order(StringComparer.Ordinal).ToList();

    private static List<string> AssemblyRefs(Assembly assembly) =>
        assembly.GetReferencedAssemblies().Select(a => a.Name!).ToList();

    private static bool IsBcl(string name) => BclPrefixes.Any(p => name == p || name.StartsWith(p + ".", StringComparison.Ordinal));

    [Fact]
    public void Domain_declares_no_project_package_or_framework_references()
    {
        Assert.Empty(ProjectRefs("TaxCredit.Domain"));
        Assert.Empty(Items("TaxCredit.Domain", "PackageReference"));
        Assert.Empty(Items("TaxCredit.Domain", "FrameworkReference"));
    }

    [Fact]
    public void Domain_assembly_uses_only_the_bcl_and_no_io_or_network()
    {
        var refs = AssemblyRefs(typeof(PyRound).Assembly).ToList();
        Assert.Empty(Violations(refs, IsBcl));
        Assert.DoesNotContain(refs, r => ForbiddenInDomain.Any(f => r.StartsWith(f, StringComparison.Ordinal)));
    }

    [Fact]
    public void Application_depends_on_domain_only_and_never_on_infrastructure_or_a_web_framework()
    {
        Assert.Equal(["TaxCredit.Domain"], ProjectRefs("TaxCredit.Application"));
        Assert.Equal(["Microsoft.Extensions.DependencyInjection.Abstractions"], Items("TaxCredit.Application", "PackageReference"));
        Assert.Empty(Items("TaxCredit.Application", "FrameworkReference"));

        var refs = AssemblyRefs(typeof(AppDi).Assembly);
        Assert.Empty(Violations(refs, r => IsBcl(r) || r == "TaxCredit.Domain" || r == "Microsoft.Extensions.DependencyInjection.Abstractions"));
    }

    [Fact]
    public void Infrastructure_implements_application_ports_and_does_not_reach_the_api()
    {
        Assert.Equal(["TaxCredit.Application"], ProjectRefs("TaxCredit.Infrastructure"));
        var refs = AssemblyRefs(typeof(InMemoryAuditLog).Assembly);
        Assert.DoesNotContain("TaxCredit.Api", refs);
        Assert.DoesNotContain(refs, r => r.StartsWith("Microsoft.AspNetCore", StringComparison.Ordinal));
    }

    [Fact]
    public void Service_defaults_references_no_taxcredit_project()
    {
        Assert.Empty(ProjectRefs("TaxCredit.ServiceDefaults"));
        Assert.DoesNotContain(AssemblyRefs(typeof(ServiceExtensions).Assembly), r => r.StartsWith("TaxCredit.", StringComparison.Ordinal));
    }

    [Fact]
    public void Api_composes_but_is_never_referenced_by_an_inner_layer()
    {
        foreach (var inner in new[] { "TaxCredit.Domain", "TaxCredit.Application", "TaxCredit.Infrastructure", "TaxCredit.ServiceDefaults" })
        {
            Assert.DoesNotContain("TaxCredit.Api", ProjectRefs(inner));
        }

        Assert.DoesNotContain("TaxCredit.Infrastructure", ProjectRefs("TaxCredit.Domain"));
        Assert.DoesNotContain("TaxCredit.Infrastructure", ProjectRefs("TaxCredit.Application"));
    }

    [Fact]
    public void Public_classes_are_sealed_static_or_abstract_and_there_are_no_mutable_public_statics()
    {
        var assemblies = new[] { typeof(PyRound).Assembly, typeof(AppDi).Assembly, typeof(InMemoryAuditLog).Assembly, typeof(ServiceExtensions).Assembly };
        var offenders = new List<string>();
        foreach (var type in assemblies.SelectMany(a => a.GetExportedTypes()))
        {
            if (type.IsClass && !type.IsSealed && !type.IsAbstract)
            {
                offenders.Add($"{type.FullName} is not sealed");
            }

            offenders.AddRange(type.GetFields(BindingFlags.Public | BindingFlags.Static)
                .Where(f => !f.IsInitOnly && !f.IsLiteral)
                .Select(f => $"{type.FullName}.{f.Name} is a mutable public static"));
        }

        Assert.Empty(offenders);
    }

    [Fact]
    public void The_rules_can_fail_a_synthetic_violation_is_detected()
    {
        // Mutation self-test: pretend Domain referenced Infrastructure and ASP.NET Core.
        var mutated = AssemblyRefs(typeof(PyRound).Assembly).Concat(["TaxCredit.Infrastructure", "Microsoft.AspNetCore.Http"]);
        Assert.Equal(["Microsoft.AspNetCore.Http", "TaxCredit.Infrastructure"], Violations(mutated, IsBcl));
    }
}
