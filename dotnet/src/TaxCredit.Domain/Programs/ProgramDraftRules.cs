using System.Security.Cryptography;
using System.Text.RegularExpressions;
using TaxCredit.Domain.Numerics;

namespace TaxCredit.Domain.Programs;

/// <summary>The limits, the program-code pattern and the canonical document text of <c>domain/program_drafts.py</c>. [F05.2, ADR-013, ADR-005]</summary>
public static class ProgramDraftRules
{
    /// <summary>
    /// The most characters one stored document may hold (the Warehouse column is <c>VARCHAR(8000)</c>); Python <c>MAX_DOCUMENT_CHARS</c>.
    /// The module only declares it: <c>application/program_drafts</c> enforces it, and a clipped pack is a wrong pack.
    /// </summary>
    public const int MaxDocumentChars = 8000;

    /// <summary>A few dozen year packs at most (Python <c>MAX_YEAR_DOCUMENTS</c>); keeps an export event's path list inside its <c>VARCHAR(4000)</c>.</summary>
    public const int MaxYearDocuments = 30;

    /// <summary>How deep a document may nest (Python <c>MAX_DOCUMENT_DEPTH</c>); stops a hostile document recursing a parser or the JSON writer.</summary>
    public const int MaxDocumentDepth = 12;

    /// <summary>Python <c>CODE_PATTERN</c>, <c>^[A-Z][A-Z0-9_]{2,63}$</c>: upper case, digits and underscores, starting with a letter (<c>GA_JTC</c>).</summary>
    /// <remarks>
    /// Python's <c>$</c> (no <c>MULTILINE</c>) matches at the end or before a final <c>\n</c>, so <c>"GA_JTC\n"</c> matches; .NET's <c>$</c> does
    /// the same, and only for <c>\n</c> (not <c>\r\n</c>). Neither engine applies Unicode case folding to <c>[A-Z]</c> without <c>IGNORECASE</c>.
    /// Callers use <c>.match</c>, which <see cref="Regex.Match(string)"/> with the leading <c>^</c> reproduces.
    /// </remarks>
    public static Regex CodePattern { get; } = new(@"^[A-Z][A-Z0-9_]{2,63}$", RegexOptions.CultureInvariant);

    /// <summary>Python <c>CODE_PATTERN.match(text)</c> as a bool.</summary>
    /// <param name="text">A proposed program code.</param>
    /// <returns>Whether it matches.</returns>
    public static bool IsProgramCode(string text) => CodePattern.IsMatch(text);

    /// <summary>
    /// Python <c>canonical_json</c>: compact, key-sorted JSON with <c>ensure_ascii=False</c>, the one text a document is stored, hashed and exported as.
    /// </summary>
    /// <param name="document">A JSON tree.</param>
    /// <returns>The canonical text.</returns>
    public static string CanonicalJson(object? document) => PyJson.Dumps(document, sortKeys: true, compact: true, ensureAscii: false);

    /// <summary>Python <c>documents_hash</c>: SHA-256 over the canonical documents, what validation and review are tied to.</summary>
    /// <param name="pack">The base pack, or <c>null</c>.</param>
    /// <param name="years">The year packs by year.</param>
    /// <returns>Lower-case hex.</returns>
    /// <exception cref="PyUnicodeEncodeError">When a document holds a lone surrogate (Python fails at <c>.encode("utf-8")</c>).</exception>
    public static string DocumentsHash(PyDict? pack, PyDict years) =>
        Convert.ToHexString(SHA256.HashData(PyUtf8.Encode(CanonicalJson(new PyDict().Add("pack", pack).Add("years", years))))).ToLowerInvariant();
}
