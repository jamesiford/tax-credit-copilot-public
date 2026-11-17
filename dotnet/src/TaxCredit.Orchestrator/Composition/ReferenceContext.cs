using System.Globalization;

namespace TaxCredit.Orchestrator.Composition;

/// <summary>Public reference prose has a citation, never engine facts or placeholder authority.</summary>
public sealed record ReferencePassage(string Text, string Source, string Citation, DateTimeOffset RetrievedAt);

/// <summary>Knowledge adapters return public reference text, never payroll rows or executable tools.</summary>
public interface IReferenceSource
{
    /// <summary>Return relevant passages in source order without granting any numeric authority.</summary>
    Task<IReadOnlyList<ReferencePassage>> SearchAsync(string question, int top, CancellationToken cancellationToken);
}

/// <summary>Optional, bounded reference text; no retrieval occurs unless a caller explicitly enables it.</summary>
public sealed class ReferenceContext
{
    private readonly ReferencePassage[] passages;

    private ReferenceContext(IEnumerable<ReferencePassage> passages)
    {
        this.passages = passages.ToArray();
    }

    /// <summary>The default adds neither a model instruction nor reader reference text.</summary>
    public static ReferenceContext Disabled { get; } = new([]);

    /// <summary>Use an injected source; no provider, endpoint or credentials are defaulted implicitly.</summary>
    public static Task<ReferenceContext> RetrieveAsync(bool enabled, IReferenceSource? source,
        string question, int top = 3, CancellationToken cancellationToken = default) =>
        LoadAsync(enabled, source is null ? null : source.SearchAsync, question, top, cancellationToken);

    /// <summary>Retrieval failure cannot remove a computed answer; cancellation still belongs to the caller.</summary>
    public static async Task<ReferenceContext> LoadAsync(bool enabled,
        Func<string, int, CancellationToken, Task<IReadOnlyList<ReferencePassage>>>? search,
        string question, int top = 3, CancellationToken cancellationToken = default)
    {
        if (!enabled || search is null)
        {
            return Disabled;
        }
        ArgumentOutOfRangeException.ThrowIfLessThan(top, 1);
        ArgumentOutOfRangeException.ThrowIfGreaterThan(top, 10);
        cancellationToken.ThrowIfCancellationRequested();
        try
        {
            var found = await search(question, top, cancellationToken).ConfigureAwait(false);
            return new(found.Take(top).Where(Valid));
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
        {
            throw;
        }
        catch (Exception exception) when (exception is not OutOfMemoryException)
        {
            return Disabled;
        }
    }

    /// <summary>Sources and citations stay out of the model's instructions, and nothing becomes a fact path.</summary>
    public string ModelContext()
    {
        if (passages.Length == 0)
        {
            return "";
        }
        const string header = "REFERENCE TEXT retrieved for this question. It is background to read, not facts: " +
            "it holds no figure you may use, so write none from it and use only {{facts.…}} placeholders for any figure. " +
            "Refer to a source only as \"the cited source\"; the platform prints the citations itself.";
        return GuardedReplyComposer.Join([header, .. passages.Select((passage, index) =>
            ModelBrief.Fence(passage.Text, "reference " + (index + 1).ToString(CultureInfo.InvariantCulture)))]);
    }

    internal string ReaderText(IEnumerable<string> privateValues)
    {
        var hidden = privateValues.ToArray();
        var visible = passages.Where(passage => !CompositionProjection.ContainsHiddenText(
            passage.Text + passage.Source + passage.Citation, hidden)).ToArray();
        if (visible.Length == 0)
        {
            return "";
        }
        const string header = "**Reference text** _(quoted from the cited sources; not computed by the engine, " +
            "and no figure above comes from it)_";
        return GuardedReplyComposer.Join([header, .. visible.Select((passage, index) =>
            (index + 1).ToString(CultureInfo.InvariantCulture) + ".\n" +
            string.Join("\n", passage.Text.Trim().Split('\n').Select(line => "> " + line.TrimEnd('\r'))) +
            "\n> — " + OneLine(passage.Citation) + " · " + OneLine(passage.Source) + " · retrieved " +
            passage.RetrievedAt.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture))]);
    }

    private static bool Valid(ReferencePassage passage) =>
        !string.IsNullOrWhiteSpace(passage.Text) && passage.Text.Length <= 8000 &&
        !string.IsNullOrWhiteSpace(passage.Source) && passage.Source.Length <= 500 &&
        !string.IsNullOrWhiteSpace(passage.Citation) && passage.Citation.Length <= 2000;

    private static string OneLine(string text) => string.Join(" ", text.Split((char[]?)null, StringSplitOptions.RemoveEmptyEntries));
}
