using System.Text;
using TaxCredit.Domain.Canonical;
using TaxCredit.Domain.Numerics;

namespace TaxCredit.Infrastructure.Payroll;

/// <summary>
/// Python <c>PayPeriodCsvAdapter</c>: the prototype pay-period CSV read as <c>csv.DictReader(open(path, newline="", encoding="utf-8"))</c>.
/// </summary>
/// <remarks>
/// Mirrors the default CSV dialect of CPython 3.12 (<c>_csv.c</c> <c>parse_process_char</c>, non-strict): comma delimiter, <c>"</c> quoting with doubled quotes,
/// lines ended by <c>\n</c>, <c>\r\n</c> or <c>\r</c> (a terminator inside quotes is data), a quote inside an unquoted field is literal, characters after a
/// closing quote are appended, blank lines are skipped after the header, a short row pads with <c>None</c> and a long row's extra cells are dropped
/// (Python keeps them under the key <c>None</c>, which a string-keyed <see cref="PyDict"/> cannot hold and <c>to_canonical</c> never reads). A byte-order mark
/// stays in the first header, as with Python's plain <c>utf-8</c>. Not mirrored: the 131072-character field limit and the <c>UnicodeDecodeError</c> of
/// invalid UTF-8 (surfaced here as a .NET decoder exception).
/// </remarks>
/// <param name="path">The CSV file; a missing file reads as no rows, as in Python.</param>
public sealed class PayPeriodCsvAdapter(string path) : ISourceAdapter
{
    private enum State
    {
        StartRecord,
        StartField,
        InField,
        InQuoted,
        QuoteInQuoted,
        EatCrNl,
    }

    /// <inheritdoc />
    public IEnumerable<PyDict> Rows() =>
        File.Exists(path) ? DictRows(Parse(new UTF8Encoding(false, true).GetString(File.ReadAllBytes(path)))) : [];

    /// <summary>Parses CSV text as <c>csv.reader</c> does: one list of cells per record, a blank line being an empty list.</summary>
    /// <param name="text">The text.</param>
    /// <returns>The records.</returns>
    public static List<List<string>> Parse(string text)
    {
        ArgumentNullException.ThrowIfNull(text);
        var records = new List<List<string>>();
        var fields = new List<string>();
        var field = new StringBuilder();
        var state = State.StartRecord;
        foreach (var line in Lines(text))
        {
            for (var i = 0; i <= line.Length; i++)
            {
                var atEol = i == line.Length;
                state = Step(state, atEol ? '\0' : line[i], atEol, fields, field);
            }

            if (state == State.StartRecord)
            {
                records.Add(fields);
                fields = [];
            }
        }

        if (field.Length > 0 || state == State.InQuoted)
        {
            fields.Add(field.ToString());
            records.Add(fields);
        }

        return records;
    }

    // One character of CPython's `parse_process_char`; `eol` is its EOL marker (the end of a line string).
    private static State Step(State state, char c, bool eol, List<string> fields, StringBuilder field)
    {
        var newline = !eol && c is '\n' or '\r';
        switch (state)
        {
            case State.StartRecord when eol:
                return State.StartRecord;
            case State.StartRecord when newline:
                return State.EatCrNl;
            case State.StartRecord:
                return Step(State.StartField, c, eol, fields, field);
            case State.StartField or State.InField or State.QuoteInQuoted when eol || newline:
                Save(fields, field);
                return eol ? State.StartRecord : State.EatCrNl;
            case State.StartField when c == '"':
                return State.InQuoted;
            case State.StartField or State.InField or State.QuoteInQuoted when c == ',':
                Save(fields, field);
                return State.StartField;
            case State.QuoteInQuoted when c == '"':
                field.Append('"');
                return State.InQuoted;
            case State.InQuoted when eol:
                return State.InQuoted;
            case State.InQuoted when c == '"':
                return State.QuoteInQuoted;
            case State.InQuoted:
                field.Append(c);
                return State.InQuoted;
            case State.EatCrNl when eol:
                return State.StartRecord;
            case State.EatCrNl when newline:
                return State.EatCrNl;
            case State.EatCrNl:
                throw new InvalidDataException("new-line character seen in unquoted field - do you need to open the file in universal-newline mode?");
            default:
                field.Append(c);
                return State.InField;
        }
    }

    private static void Save(List<string> fields, StringBuilder field)
    {
        fields.Add(field.ToString());
        field.Clear();
    }

    // Lines as Python's `open(newline="")` yields them: split after "\n", "\r\n" or a lone "\r", the terminator kept.
    private static IEnumerable<string> Lines(string text)
    {
        var start = 0;
        for (var i = 0; i < text.Length; i++)
        {
            if (text[i] == '\r' && i + 1 < text.Length && text[i + 1] == '\n')
            {
                yield return text[start..(i + 2)];
                start = i + 2;
                i++;
            }
            else if (text[i] is '\n' or '\r')
            {
                yield return text[start..(i + 1)];
                start = i + 1;
            }
        }

        if (start < text.Length)
        {
            yield return text[start..];
        }
    }

    // Python `csv.DictReader.__next__`: `dict(zip(fieldnames, row))` with `None` for the cells a short row lacks; blank rows are skipped.
    private static List<PyDict> DictRows(List<List<string>> records)
    {
        var rows = new List<PyDict>();
        for (var r = 1; r < records.Count; r++)
        {
            if (records[r].Count == 0)
            {
                continue;
            }

            var row = new PyDict();
            for (var i = 0; i < records[0].Count; i++)
            {
                row.Set(records[0][i], i < records[r].Count ? records[r][i] : null);
            }

            rows.Add(row);
        }

        return rows;
    }
}
