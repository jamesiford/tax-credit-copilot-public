using System.Text.RegularExpressions;
using TaxCredit.Application.Ports.Sources;
using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Programs;

namespace TaxCredit.Application.Features.DraftsRuns;

/// <summary>Blocking findings identify a field and classification, never repeat the matched customer text.</summary>
public sealed class DraftCustomerData(ISourceReader source)
{
    private static readonly (string What, Regex Pattern)[] Patterns =
    [
        ("a social security number", new(@"(?<![\d-])\d{3}-\d{2}-\d{4}(?![\d-])", RegexOptions.CultureInvariant, TimeSpan.FromSeconds(1))),
        ("an employer identification number", new(@"(?<![\d-])\d{2}-\d{7}(?![\d-])", RegexOptions.CultureInvariant, TimeSpan.FromSeconds(1))),
        ("an email address", new(@"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", RegexOptions.CultureInvariant, TimeSpan.FromSeconds(1))),
        ("a phone number", new(@"(?<![\d-])(?:\+?1[ .-])?\(?\d{3}\)?[ .-]\d{3}[ .-]\d{4}(?![\d-])", RegexOptions.CultureInvariant, TimeSpan.FromSeconds(1))),
        ("a long digit string (an identifier or account number)", new(@"(?<![\w.,-])\d{9,}(?![\w.,-])", RegexOptions.CultureInvariant, TimeSpan.FromSeconds(1))),
    ];

    /// <summary>Scans strings only; statutory numeric values are not customer identifiers.</summary>
    public IReadOnlyList<PyDict> Scan(ProgramDraft draft)
    {
        ArgumentNullException.ThrowIfNull(draft);
        var names = source.ListAccounts().Select(c => c.Name.Trim()).Where(n => n.Length >= 4).Distinct(StringComparer.OrdinalIgnoreCase).ToArray();
        var matcher = names.Length == 0 ? null : new Regex(@"(?<!\w)(?:" + string.Join("|", names.Select(Regex.Escape)) + @")(?!\w)",
            RegexOptions.IgnoreCase | RegexOptions.CultureInvariant, TimeSpan.FromSeconds(1));
        var documents = new[] { ("draft", (object?)new PyDict().Add("name", draft.Name)) }.Concat(DraftDocuments.All(draft));
        var findings = new List<PyDict>();
        foreach (var (file, document) in documents)
        {
            foreach (var (path, text) in DraftDocuments.Strings(document))
            {
                foreach (var (what, pattern) in Patterns)
                {
                    if (pattern.IsMatch(text)) { findings.Add(Finding(file, path, what)); }
                }
                if (matcher?.IsMatch(text) is true) { findings.Add(Finding(file, path, "the name of a client or employer in the book")); }
                if (findings.Count >= 20) { return findings.Take(20).ToArray(); }
            }
        }
        return findings;
    }

    private static PyDict Finding(string file, string path, string what) => DraftValidation.Finding(file, "error", "customer_data", path.Length == 0 ? "/" : path,
        $"looks like {what} (not shown here). A program draft holds statute, not customer data: remove it.");
}
