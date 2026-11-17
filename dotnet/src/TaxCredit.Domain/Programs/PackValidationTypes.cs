using TaxCredit.Domain.Numerics;

namespace TaxCredit.Domain.Programs;

/// <summary>One finding of the pack validator (Python <c>pack_validation.Issue</c>). <c>error</c> fails validation; <c>warning</c> and <c>info</c> are reported.</summary>
/// <param name="Severity"><c>error</c>, <c>warning</c> or <c>info</c>.</param>
/// <param name="Code">The rule that fired (<c>schema</c>, <c>filename</c>, <c>unverified</c>, ...).</param>
/// <param name="Path">Where in the pack: a <c>/</c>-joined path, <c>/</c> for the root of a flag, empty for the whole file.</param>
/// <param name="Message">What is wrong, in words.</param>
public sealed record PackIssue(string Severity, string Code, string Path, string Message);

/// <summary>
/// The findings for one file (Python <c>pack_validation.Report</c>). A class rather than a record because the validator appends to it while it
/// works, exactly as Python does; callers read it through <see cref="Issues"/>.
/// </summary>
public sealed class PackReport
{
    private readonly List<PackIssue> _issues = [];

    /// <summary>Initialises an empty report.</summary>
    /// <param name="file">The file as shown (Python <c>str(path)</c>), or the document name for a draft held in memory.</param>
    /// <param name="kind"><c>base</c> or <c>year</c>.</param>
    public PackReport(string file, string kind)
    {
        File = file;
        Kind = kind;
    }

    /// <summary>The file as shown.</summary>
    public string File { get; }

    /// <summary>The kind of pack judged: <c>base</c> or <c>year</c>.</summary>
    public string Kind { get; }

    /// <summary>The findings in the order they were added (schema findings first, sorted by path).</summary>
    public IReadOnlyList<PackIssue> Issues => _issues;

    /// <summary>True when no finding is an error (Python <c>ok</c>).</summary>
    public bool Ok => !_issues.Any(i => i.Severity == "error");

    /// <summary>Python <c>Report.add</c>: note the argument order, <c>message</c> before <c>path</c>.</summary>
    /// <param name="severity">The severity.</param>
    /// <param name="code">The rule code.</param>
    /// <param name="message">The message.</param>
    /// <param name="path">The path inside the pack.</param>
    internal void Add(string severity, string code, string message, string path = "") => _issues.Add(new PackIssue(severity, code, path, message));
}

/// <summary>The kinds of rule pack the validator tells apart (Python passes the strings <c>base</c> and <c>year</c>).</summary>
internal static class PackKinds
{
    /// <summary>A year pack, <c>rules/&lt;program&gt;/&lt;year&gt;.json</c>.</summary>
    internal const string Year = "year";

    /// <summary>A program's base pack, <c>rules/&lt;program&gt;.json</c>; every kind that is not <c>year</c> is judged as one.</summary>
    internal const string Base = "base";

    /// <summary>Python <c>path.stem.split(".")[0].isdigit()</c> over ASCII digits (non-ASCII digit file names are not modelled, as in <c>authored_years</c>).</summary>
    internal static bool IsYearName(string stem)
    {
        var first = stem.Split('.')[0];
        return first.Length > 0 && first.All(char.IsAsciiDigit);
    }
}

/// <summary>The few <c>str</c> operations the validator uses that <see cref="PyStr"/> does not provide.</summary>
internal static class PackText
{
    /// <summary>
    /// Python <c>s.lower()</c>: full case mapping. .NET's invariant lower-casing is the simple mapping, which differs in the two places Python's
    /// <c>lower()</c> is special: U+0130 becomes <c>i</c> plus a combining dot, and a capital sigma at the end of a word becomes final sigma.
    /// </summary>
    internal static string Lower(string s)
    {
        var lowered = new System.Text.StringBuilder(s.Length);
        for (var i = 0; i < s.Length; i++)
        {
            var c = s[i];
            if (c == '\u0130')
            {
                lowered.Append("i\u0307");
            }
            else if (c == '\u03A3')
            {
                lowered.Append(IsFinalSigma(s, i) ? '\u03C2' : '\u03C3');
            }
            else
            {
                lowered.Append(char.ToLowerInvariant(c));
            }
        }

        return lowered.ToString();
    }

    // Unicode Final_Sigma: a cased letter before (ignoring case-ignorable marks) and none after.
    private static bool IsFinalSigma(string s, int at)
    {
        var before = at - 1;
        while (before >= 0 && IsCaseIgnorable(s[before]))
        {
            before--;
        }

        var after = at + 1;
        while (after < s.Length && IsCaseIgnorable(s[after]))
        {
            after++;
        }

        return before >= 0 && IsCased(s[before]) && !(after < s.Length && IsCased(s[after]));
    }

    private static bool IsCased(char c) => char.GetUnicodeCategory(c) is System.Globalization.UnicodeCategory.UppercaseLetter or System.Globalization.UnicodeCategory.LowercaseLetter
        or System.Globalization.UnicodeCategory.TitlecaseLetter;

    private static bool IsCaseIgnorable(char c) => char.GetUnicodeCategory(c) is System.Globalization.UnicodeCategory.NonSpacingMark or System.Globalization.UnicodeCategory.EnclosingMark
        or System.Globalization.UnicodeCategory.Format or System.Globalization.UnicodeCategory.ModifierLetter or System.Globalization.UnicodeCategory.ModifierSymbol
        || c is '\'' or '.' or ':' or '\u00B7' or '\u2019';
}
