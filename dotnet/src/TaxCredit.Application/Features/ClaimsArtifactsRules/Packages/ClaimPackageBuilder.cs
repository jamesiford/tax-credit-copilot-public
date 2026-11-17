using System.Globalization;
using System.IO.Compression;
using System.Text;
using TaxCredit.Application.Ports.Contract;
using TaxCredit.Application.Ports.Persistence;
using TaxCredit.Domain.Claims;

namespace TaxCredit.Application.Features.ClaimsArtifactsRules.Packages;

internal sealed record BuiltPackage(byte[] Data, string FileName, string RunId, string? ProgramCode, IReadOnlyDictionary<string, int> Rows);

internal sealed class ClaimPackageBuilder(IGoldReadPort gold, IClaimRepository claims, IClock clock)
{
    internal const string ContentType = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";

    internal BuiltPackage Build(long clientId, int year, string actor)
    {
        using var scope = gold.Scope();
        var run = gold.LatestRun(clientId) ?? throw new FeatureRefusalException(409, $"client {clientId} has no completed calculation run to package");
        List<object?[]> coverage = [PackageColumns.Coverage.Cast<object?>().ToArray()];
        coverage.AddRange(claims.Coverage(clientId, taxYears: [year]).Select(c => c.ToDict())
            .Select(c => PackageColumns.Coverage.Select(key => c.TryGetValue(key, out var value) ? value : null).ToArray()));
        List<object?[]> locations = [PackageColumns.Locations.Cast<object?>().ToArray()];
        List<object?[]> installments = [PackageColumns.Installments.Cast<object?>().ToArray()];
        foreach (var method in new[] { "min_max", "pay_period" })
        {
            locations.AddRange(ReadLocations(clientId, year, method).Select(r => Row(PackageColumns.Locations, r, method)));
            installments.AddRange(gold.Installments(clientId, method).Where(r => Convert.ToInt64(r["tax_year"], CultureInfo.InvariantCulture) == year)
                .Select(r => Row(PackageColumns.Installments, r, method)));
        }
        List<object?[]> provenance = [["field", "value"], ["client_id", clientId], ["package_tax_year", year]];
        provenance.AddRange(PackageColumns.Provenance.Select(key => new object?[] { key, run.GetValueOrDefault(key) }));
        provenance.Add(["trail_sha256", run.GetValueOrDefault("trail_sha256") ?? "not recorded on the run manifest"]);
        provenance.Add(["generated_by", actor]);
        provenance.Add(["generated_at", clock.UtcNow]);
        provenance.Add(["package_format", "claim_package v1"]);
        IReadOnlyList<object?[]>[] sheets = [coverage, locations, installments, provenance,
            PackageColumns.Disclaimer.Select(line => new object?[] { line }).ToArray()];
        var runId = (string)run["run_id"]!;
        return new BuiltPackage(Archive(sheets), $"claim-package-{clientId}-TY{year}-{runId[..Math.Min(8, runId.Length)]}.xlsx",
            runId, run.GetValueOrDefault("program_code") as string,
            PackageColumns.Names.Select((name, i) => (name, count: sheets[i].Count - (i == 4 ? 0 : 1)))
                .ToDictionary(p => p.name, p => p.count, StringComparer.Ordinal));
    }

    private IEnumerable<IReadOnlyDictionary<string, object?>> ReadLocations(long client, int year, string method)
    {
        const int pageSize = 1000;
        for (var offset = 0; ; offset += pageSize)
        {
            var page = gold.UnitYears(client, method, year, limit: pageSize, offset: offset);
            foreach (var row in page.Items) { yield return row; }
            if ((long)offset + pageSize >= page.Total) { yield break; }
        }
    }

    private static object?[] Row(string[] columns, IReadOnlyDictionary<string, object?> row, string method) =>
        columns.Select(c => c == "method" ? method : row.GetValueOrDefault(c)).ToArray();

    private byte[] Archive(IReadOnlyList<object?[]>[] sheets)
    {
        using var buffer = new MemoryStream();
        using (var zip = new ZipArchive(buffer, ZipArchiveMode.Create, leaveOpen: true))
        {
            Add(zip, "docProps/app.xml", WorkbookParts.App);
            Add(zip, "docProps/core.xml", Core());
            Add(zip, "xl/theme/theme1.xml", WorkbookParts.Theme);
            for (var i = 0; i < sheets.Length; i++) { Add(zip, $"xl/worksheets/sheet{i + 1}.xml", WorkbookXml.Sheet(sheets[i], i < 3)); }
            Add(zip, "xl/styles.xml", WorkbookParts.Styles);
            Add(zip, "_rels/.rels", WorkbookParts.Relationships);
            Add(zip, "xl/workbook.xml", WorkbookParts.Workbook);
            Add(zip, "xl/_rels/workbook.xml.rels", WorkbookParts.WorkbookRelationships);
            Add(zip, "[Content_Types].xml", WorkbookParts.ContentTypes);
        }
        return buffer.ToArray();
    }

    private string Core()
    {
        var now = clock.UtcNow.UtcDateTime.ToString("yyyy-MM-dd'T'HH:mm:ss'Z'", CultureInfo.InvariantCulture);
        return $"<cp:coreProperties xmlns:cp=\"http://schemas.openxmlformats.org/package/2006/metadata/core-properties\" xmlns:dc=\"http://purl.org/dc/elements/1.1/\" xmlns:dcterms=\"http://purl.org/dc/terms/\" xmlns:xsi=\"http://www.w3.org/2001/XMLSchema-instance\"><dc:creator>openpyxl</dc:creator><dcterms:created xsi:type=\"dcterms:W3CDTF\">{now}</dcterms:created><dcterms:modified xsi:type=\"dcterms:W3CDTF\">{now}</dcterms:modified></cp:coreProperties>";
    }

    private static void Add(ZipArchive zip, string name, string text)
    {
        using var output = zip.CreateEntry(name, CompressionLevel.Optimal).Open();
        output.Write(Encoding.UTF8.GetBytes(text.Replace("\r\n", "\n", StringComparison.Ordinal)));
    }
}
