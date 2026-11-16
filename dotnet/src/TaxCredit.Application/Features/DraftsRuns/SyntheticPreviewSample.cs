using System.Text;
using TaxCredit.Domain.Calculation;
using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Pipeline;
using TaxCredit.Domain.Programs;

namespace TaxCredit.Application.Features.DraftsRuns;

/// <summary>Reads only the designated committed sample, independent of the runtime payroll source or caller client id.</summary>
public sealed class SyntheticPreviewSample(IRulePackSource rules)
{
    /// <summary>Relabels the sample's GA worksites, retaining the certified CSV typing and row interpretation.</summary>
    public IReadOnlyList<PayrollRow> Load(string state)
    {
        var path = Path.Combine(Path.GetDirectoryName(rules.RulesDirectory)!, "data", "payroll_pay_periods.csv");
        if (!File.Exists(path)) { throw new PreviewRefused("The designated synthetic sample is unavailable."); }
        using var reader = new StreamReader(path, new UTF8Encoding(false, true));
        using var records = Records(reader).GetEnumerator();
        if (!records.MoveNext()) { return []; }
        var header = records.Current;
        var raw = new List<PyDict>();
        while (records.MoveNext())
        {
            var cells = records.Current;
            if (cells.Count != header.Count) { throw new InvalidDataException("Malformed committed synthetic sample."); }
            var row = FeatureValues.Copy(header.Select((name, index) => new KeyValuePair<string, object?>(name, cells[index])));
            if (row["Worksite_ID"] is not string site || !site.StartsWith("GA_", StringComparison.Ordinal)) { continue; }
            row.Set("Worksite_ID", state + "_" + site[3..]);
            raw.Add(row);
        }
        return CsvPayroll.Typed(raw).Select(row => PayRow.Of(row).Row).ToArray();
    }

    private static IEnumerable<List<string>> Records(TextReader reader)
    {
        var fields = new List<string>();
        var field = new StringBuilder();
        var quoted = false;
        while (reader.Read() is var next && next >= 0)
        {
            var character = (char)next;
            if (character == '"' && (quoted || field.Length == 0))
            {
                if (quoted && reader.Peek() == '"') { reader.Read(); field.Append('"'); }
                else { quoted = !quoted; }
            }
            else if (!quoted && character is ',' or '\r' or '\n')
            {
                fields.Add(field.ToString());
                field.Clear();
                if (character == ',') { continue; }
                if (character == '\r' && reader.Peek() == '\n') { reader.Read(); }
                if (fields.Count > 1 || fields[0].Length > 0) { yield return fields; }
                fields = [];
            }
            else { field.Append(character); }
        }
        if (quoted) { throw new InvalidDataException("Unclosed quotation in committed synthetic sample."); }
        if (field.Length > 0 || fields.Count > 0) { fields.Add(field.ToString()); yield return fields; }
    }
}
