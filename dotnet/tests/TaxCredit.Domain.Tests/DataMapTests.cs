using System.Text;
using TaxCredit.Domain.DataMap;
using Map = TaxCredit.Domain.DataMap.DataMap;

namespace TaxCredit.Domain.Tests;

public sealed class DataMapTests
{
    private static string Shipped => File.ReadAllText(Path.Combine(Root(), "docs", "data", "data-map.json"));

    private static string Root()
    {
        var dir = new DirectoryInfo(AppContext.BaseDirectory);
        while (dir is not null && !File.Exists(Path.Combine(dir.FullName, "docs", "data", "data-map.json")))
        {
            dir = dir.Parent;
        }

        return dir?.FullName ?? throw new DirectoryNotFoundException("docs/data/data-map.json not found above the test binary.");
    }

    private static Map LoadText(string json)
    {
        var path = Path.Combine(Path.GetTempPath(), "data-map-" + Guid.NewGuid().ToString("N") + ".json");
        File.WriteAllText(path, json, new UTF8Encoding(false));
        try
        {
            return DataMapLoader.LoadFile(path);
        }
        finally
        {
            File.Delete(path);
        }
    }

    [Fact]
    public void The_embedded_map_is_the_shipped_file()
    {
        var embedded = Map.Default;
        var file = LoadText(Shipped);
        Assert.Equal("embedded", embedded.Source);
        Assert.Equal("file", file.Source);
        Assert.Equal(38, embedded.Tables.Count);
        Assert.Equal(498, embedded.Tables.Values.Sum(t => t.Columns.Count));
        Assert.Equal(["tcc_gold", "tcc_ops", "tcc_source"], [embedded.GoldSchema, embedded.OpsSchema, embedded.SourceSchema]);
        Assert.Equal(embedded.Tables.Keys, file.Tables.Keys);
    }

    [Fact]
    public void Tokens_resolve_to_the_shipped_names_and_flatten_for_sqlite()
    {
        var names = PhysicalNames.Default;
        Assert.Equal("SELECT 1 FROM tcc_ops.run_manifest m JOIN tcc_gold.unit_year_master g ON 1=1",
            names.Resolve("SELECT 1 FROM {ops.run_manifest} m JOIN {gold.unit_year_master} g ON 1=1"));
        Assert.Equal("SELECT 1 FROM \"tcc_ops_run_manifest\"", names.ResolveFlat("SELECT 1 FROM {ops.run_manifest}"));
        Assert.Equal("[tcc_ops].[manual_override]", names.Bracketed("ops.manual_override"));
        Assert.Equal("warehouse.tables.ops.nope is not a known key.", Assert.Throws<DataMapException>(() => names.Resolve("{ops.nope}")).Message);
    }

    [Fact]
    public void A_renamed_map_changes_every_resolved_name()
    {
        var json = Shipped.Replace("\"gold\": \"tcc_gold\"", "\"gold\": \"g1\"").Replace("\"ops\": \"tcc_ops\"", "\"ops\": \"o1\"")
            .Replace("\"table\": \"run_manifest\"", "\"table\": \"runs\"");
        var names = new PhysicalNames(LoadText(json));
        Assert.Equal("o1.runs", names.Table("ops.run_manifest"));
        Assert.Equal("\"o1_runs\"", names.ResolveFlat("{ops.run_manifest}"));
        Assert.Equal("g1.unit_year_master", names.Table("gold.unit_year_master"));
    }

    [Fact]
    public void A_missing_key_fails_naming_the_first_missing_key()
    {
        var json = Shipped.Replace("\"run_id\": {\n          \"column\": \"run_id\",\n          \"type\": \"VARCHAR(64)\"\n        },", string.Empty, StringComparison.Ordinal);
        if (json == Shipped)
        {
            json = Shipped.Replace("\"run_id\": {", "\"run_id_gone\": {", StringComparison.Ordinal);
        }

        var error = Assert.Throws<DataMapException>(() => LoadText(json));
        Assert.Contains("warehouse.tables.", error.Message, StringComparison.Ordinal);
    }

    [Theory]
    [InlineData("\"gold\": \"tcc_gold\"", "\"gold\": \"tcc_ops\"", "must differ")]
    [InlineData("\"table\": \"Payroll\"", "\"table\": \"Pay]roll\"", "not a plain identifier")]
    [InlineData("\"version\": 1", "\"version\": 2", "version must be 1")]
    public void Invalid_maps_are_refused_with_the_key_named(string find, string replace, string expected)
    {
        var json = Shipped.Replace(find, replace, StringComparison.Ordinal);
        Assert.NotEqual(Shipped, json);
        Assert.Contains(expected, Assert.Throws<DataMapException>(() => LoadText(json)).Message, StringComparison.Ordinal);
    }

    [Fact]
    public void Renaming_a_warehouse_column_is_refused_rather_than_silently_ignored()
    {
        var json = Shipped.Replace("\"column\": \"run_id\"", "\"column\": \"run_key\"", StringComparison.Ordinal);
        Assert.Contains("column renaming is not implemented", Assert.Throws<DataMapException>(() => LoadText(json)).Message, StringComparison.Ordinal);
    }

    [Fact]
    public void Two_logical_tables_cannot_share_a_physical_name_in_one_schema()
    {
        var json = Shipped.Replace("\"table\": \"run_batch_item\"", "\"table\": \"run_batch\"", StringComparison.Ordinal);
        Assert.Contains("already mapped", Assert.Throws<DataMapException>(() => LoadText(json)).Message, StringComparison.Ordinal);
    }
}
