using System.Text;
using System.Text.RegularExpressions;
using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Programs;

namespace TaxCredit.Application.Features.DraftsRuns;

internal static partial class DraftDocuments
{
    [GeneratedRegex("^[A-Z][A-Z0-9_]{2,63}$", RegexOptions.CultureInvariant)]
    internal static partial Regex Code();
    [GeneratedRegex("^[A-Z]{2}$", RegexOptions.CultureInvariant)]
    internal static partial Regex State();
    [GeneratedRegex(@"^[0-9]{4}\z", RegexOptions.CultureInvariant)]
    private static partial Regex Year();

    internal static void Check(PyDict? pack, PyDict years)
    {
        if (years.Count > ProgramDraftRules.MaxYearDocuments) { throw new DraftInvalid("A draft holds at most 30 year packs."); }
        if (years.Any(p => !Year().IsMatch(p.Key) || p.Value is not PyDict)) { throw new DraftInvalid("Years must be an object of four-digit years, each a JSON object."); }
        foreach (var document in years.Select(p => p.Value).Prepend(pack).OfType<PyDict>())
        {
            var stack = new Stack<(object? Value, int Depth)>();
            stack.Push((document, 1));
            while (stack.TryPop(out var entry))
            {
                var children = entry.Value switch { PyDict map => map.Select(p => p.Value), IReadOnlyList<object?> list => list, _ => null };
                if (children is null) { continue; }
                if (entry.Depth > ProgramDraftRules.MaxDocumentDepth) { throw new DraftInvalid("A document nests deeper than 12 levels."); }
                foreach (var value in children) { stack.Push((value, entry.Depth + 1)); }
            }
            var canonical = PyJson.Dumps(document, true, true, false);
            if (canonical.EnumerateRunes().Count() > ProgramDraftRules.MaxDocumentChars) { throw new DraftInvalid("A document is larger than 8000 characters."); }
            try { _ = PyUtf8.Encode(canonical); }
            catch (PyUnicodeEncodeError) { throw new DraftInvalid("Documents must contain valid Unicode scalar values."); }
        }
    }

    internal static IEnumerable<(string Path, string Text)> Strings(object? node, string path = "")
    {
        if (node is PyDict map)
        {
            foreach (var (key, value) in map) { foreach (var entry in Strings(value, path + "/" + key)) { yield return entry; } }
        }
        else if (node is IReadOnlyList<object?> list)
        {
            for (var index = 0; index < list.Count; index++) { foreach (var entry in Strings(list[index], $"{path}/{index}")) { yield return entry; } }
        }
        else if (node is string text) { yield return (path, text); }
    }

    internal static IEnumerable<(string File, object? Document)> All(ProgramDraft draft) =>
        new[] { ("pack", (object?)draft.Pack) }.Concat(draft.Years.OrderBy(p => p.Key, PyStr.Comparer).Select(p => ("year " + p.Key, p.Value)));
}
