using System.Text.RegularExpressions;
using TaxCredit.Orchestrator.Composition;

namespace TaxCredit.Orchestrator.Hosting;

/// <summary>The source's opt-in stand-in deliberately includes invented figures to test reference isolation.</summary>
public sealed partial class SyntheticReferenceSource : IReferenceSource
{
    private static readonly DateTimeOffset Retrieved = new(2026, 1, 1, 0, 0, 0, TimeSpan.Zero);
    private static readonly ReferencePassage[] Corpus =
    [
        new("Synthetic example, not statute. A hypothetical program pays a credit of $1,234 per net-new qualifying job " +
            "when the employer holds a designation for the location.", "Synthetic corpus", "synthetic:example-credit", Retrieved),
        new("Synthetic example, not statute. A hypothetical eligibility rule counts an employee who works at least 99 hours " +
            "a week, and a hypothetical base year is the first complete year of payroll.", "Synthetic corpus", "synthetic:example-eligibility", Retrieved),
        new("Synthetic example, not statute. A hypothetical definition: a location is a worksite with its own address " +
            "and its own pay periods.", "Synthetic corpus", "synthetic:example-definition", Retrieved),
    ];

    /// <inheritdoc/>
    public Task<IReadOnlyList<ReferencePassage>> SearchAsync(string question, int top, CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        var asked = Words(question);
        var passages = Corpus.Select((passage, index) => (Passage: passage, Index: index, Score: Words(passage.Text).Count(asked.Contains)))
            .Where(item => item.Score > 0).OrderByDescending(item => item.Score).ThenBy(item => item.Index)
            .Take(top).Select(item => item.Passage).ToArray();
        return Task.FromResult<IReadOnlyList<ReferencePassage>>(passages);
    }

    private static HashSet<string> Words(string text) => Word().Matches(text.ToLowerInvariant())
        .Select(match => match.Value).ToHashSet(StringComparer.Ordinal);

    [GeneratedRegex("[a-z]{3,}", RegexOptions.CultureInvariant | RegexOptions.NonBacktracking)]
    private static partial Regex Word();
}
