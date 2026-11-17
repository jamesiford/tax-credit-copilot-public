using System.Security.Cryptography;
using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Pipeline;

namespace TaxCredit.Infrastructure.Rules;

/// <summary>
/// The active assumption sets with a content hash of each (Python <c>run_client_calculation._assumption_identity</c>). The label alone is not enough: an
/// edited set under an unchanged id would replay differently, which is exactly what a manifest exists to rule out.
/// </summary>
public static class AssumptionFiles
{
    /// <summary>The two files, in the order the manifest records them: the Step 1 set, then the One/Zero set.</summary>
    public static IReadOnlyList<string> FileNames { get; } = ["reference-dataset-assumptions.v8.json", "reference-onezero-assumptions.v7.json"];

    /// <summary>Reads each existing file of <see cref="FileNames"/> from the methodology folder.</summary>
    /// <param name="methodologyDirectory">Usually <c>backend/rules/methodology</c>.</param>
    /// <returns>The set id (<c>assumption_set_id</c>, else the file stem) and SHA-256 of the raw bytes; a missing file is skipped, as in Python.</returns>
    public static IReadOnlyList<AssumptionIdentity> Read(string methodologyDirectory)
    {
        ArgumentNullException.ThrowIfNull(methodologyDirectory);
        var output = new List<AssumptionIdentity>();
        foreach (var name in FileNames)
        {
            var file = Path.Combine(methodologyDirectory, name);
            if (!File.Exists(file))
            {
                continue;
            }

            var raw = File.ReadAllBytes(file);
            var document = PyJson.Loads(System.Text.Encoding.UTF8.GetString(raw)) as PyDict ?? throw new PyUnsupportedException(name + " is not a JSON object");
            var id = document.TryGetValue("assumption_set_id", out var v) && v is string { Length: > 0 } s ? s : Path.GetFileNameWithoutExtension(name);
            output.Add(new AssumptionIdentity(id, Convert.ToHexStringLower(SHA256.HashData(raw))));
        }

        return output;
    }
}
