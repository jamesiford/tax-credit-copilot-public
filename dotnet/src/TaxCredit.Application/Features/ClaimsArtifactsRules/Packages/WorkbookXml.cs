using System.Globalization;
using System.Text;
using TaxCredit.Domain.Numerics;

namespace TaxCredit.Application.Features.ClaimsArtifactsRules.Packages;

internal static class WorkbookXml
{
    private const string Namespace = "http://schemas.openxmlformats.org/spreadsheetml/2006/main";

    internal static string Sheet(IReadOnlyList<object?[]> rows, bool frozen)
    {
        var width = rows.Max(row => row.Length);
        var xml = new StringBuilder($"<worksheet xmlns=\"{Namespace}\"><sheetPr><outlinePr summaryBelow=\"1\" summaryRight=\"1\" /><pageSetUpPr /></sheetPr>");
        xml.Append(CultureInfo.InvariantCulture, $"<dimension ref=\"A1:{Column(width)}{rows.Count}\" /><sheetViews><sheetView workbookViewId=\"0\">");
        xml.Append(frozen
            ? "<pane ySplit=\"1\" topLeftCell=\"A2\" activePane=\"bottomLeft\" state=\"frozen\" /><selection pane=\"bottomLeft\" activeCell=\"A1\" sqref=\"A1\" />"
            : "<selection activeCell=\"A1\" sqref=\"A1\" />");
        xml.Append("</sheetView></sheetViews><sheetFormatPr baseColWidth=\"8\" defaultRowHeight=\"15\" /><cols><col width=\"28\" customWidth=\"1\" min=\"1\" max=\"1\" /></cols><sheetData>");
        for (var r = 0; r < rows.Count; r++)
        {
            xml.Append(CultureInfo.InvariantCulture, $"<row r=\"{r + 1}\">");
            for (var c = 0; c < rows[r].Length; c++)
            {
                if (rows[r][c] is { } value) { Cell(xml, $"{Column(c + 1)}{r + 1}", value); }
            }
            xml.Append("</row>");
        }
        return xml.Append("</sheetData><pageMargins left=\"0.75\" right=\"0.75\" top=\"1\" bottom=\"1\" header=\"0.5\" footer=\"0.5\" /></worksheet>").ToString();
    }

    private static void Cell(StringBuilder xml, string coordinate, object value)
    {
        if (value is DateTimeOffset instant) { Numeric(xml, coordinate, instant.UtcDateTime.ToOADate(), true); }
        else if (value is DateTime date) { Numeric(xml, coordinate, date.ToOADate(), true); }
        else if (value is bool flag) { xml.Append($"<c r=\"{coordinate}\" t=\"b\"><v>{(flag ? 1 : 0)}</v></c>"); }
        else if (value is double or float or int or long or decimal or PyDecimal)
        {
            Numeric(xml, coordinate, value is PyDecimal money ? money.ToDouble() : Convert.ToDouble(value, CultureInfo.InvariantCulture));
        }
        else
        {
            var text = Convert.ToString(value, CultureInfo.InvariantCulture) ?? "";
            // Text never becomes a formula: user-authored attribution is data, not executable workbook content.
            xml.Append($"<c r=\"{coordinate}\" t=\"inlineStr\">");
            if (text.Length > 0)
            {
                xml.Append("<is><t");
                if (char.IsWhiteSpace(text[0]) || char.IsWhiteSpace(text[^1])) { xml.Append(" xml:space=\"preserve\""); }
                xml.Append('>').Append(Escape(text)).Append("</t></is>");
            }
            xml.Append("</c>");
        }
    }

    private static void Numeric(StringBuilder xml, string coordinate, double value, bool date = false)
    {
        var text = double.IsFinite(value) ? value.ToString("G16", CultureInfo.InvariantCulture).ToLowerInvariant() : "";
        xml.Append($"<c r=\"{coordinate}\"{(date ? " s=\"1\"" : "")} t=\"n\"><v>{text}</v></c>");
    }

    internal static string Escape(string text) => text.Replace("&", "&amp;", StringComparison.Ordinal)
        .Replace("<", "&lt;", StringComparison.Ordinal).Replace(">", "&gt;", StringComparison.Ordinal)
        .Replace("\r", "&#13;", StringComparison.Ordinal);

    private static string Column(int index)
    {
        var column = "";
        while (index > 0) { index--; column = (char)('A' + index % 26) + column; index /= 26; }
        return column;
    }
}
