using TaxCredit.Application.Ports.Contract;

namespace TaxCredit.ServiceDefaults.Hosting;

/// <summary>Launches from a project, solution, repository or published directory use explicit roots or deterministic upward discovery.</summary>
public sealed class RuntimePaths
{
    /// <summary>No working-directory changes or copies of the rule library are needed.</summary>
    public RuntimePaths(IRuntimeConfiguration settings)
    {
        ArgumentNullException.ThrowIfNull(settings);
        Repository = settings.Get("TCC_REPOSITORY_ROOT") ?? Discover();
        Rules = settings.Get("RULES_DIR") ?? Path.Combine(Repository, "backend", "rules");
        Seeds = settings.Get("TCC_SEED_ROOT") ?? Path.Combine(Repository, "contract", "seed");
        Csv = settings.Get("PAYROLL_PATH") ?? Path.Combine(Repository, "backend", "data", "payroll_pay_periods.csv");
        var state = Path.Combine(Repository, "dotnet", "artifacts", "local");
        Database = settings.Get("OPERATIONAL_DB") ?? Path.Combine(state, "operations.db");
        Artifacts = settings.Get("ARTIFACT_LOCAL_ROOT") ?? Path.Combine(state, "bytes");
    }

    /// <summary>Product resources and schema root.</summary>
    public string Repository { get; }
    /// <summary>Existing authored packs, never a generated copy.</summary>
    public string Rules { get; }
    /// <summary>Committed hermetic fixture root.</summary>
    public string Seeds { get; }
    /// <summary>Explicit synthetic CSV source.</summary>
    public string Csv { get; }
    /// <summary>Shared API/Worker local destination.</summary>
    public string Database { get; }
    /// <summary>Local bytes root, never automatically deleted by reset.</summary>
    public string Artifacts { get; }

    private static string Discover()
    {
        foreach (var start in new[] { Environment.CurrentDirectory, AppContext.BaseDirectory })
        {
            for (var dir = new DirectoryInfo(start); dir is not null; dir = dir.Parent)
            {
                if (Directory.Exists(Path.Combine(dir.FullName, "backend", "rules"))
                    && Directory.Exists(Path.Combine(dir.FullName, "docs", "data", "schema")))
                {
                    return dir.FullName;
                }
            }
        }

        throw new InvalidOperationException("Set TCC_REPOSITORY_ROOT to the product resources and schema root.");
    }
}
