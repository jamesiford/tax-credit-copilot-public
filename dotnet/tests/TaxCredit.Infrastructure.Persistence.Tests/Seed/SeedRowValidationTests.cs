using System.IO.Compression;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json.Nodes;

namespace TaxCredit.Infrastructure.Persistence.Tests.Seed;

public sealed class SeedRowValidationTests
{
    [Fact]
    [Trait("Category", "heavy")]
    public void Malformed_source_values_are_refused_even_when_the_new_hashes_match()
    {
        using var fixture = new PersistenceFixture();
        fixture.Load("P1");
        var root = Path.Combine(Path.GetTempPath(), "tcc-row-seed-" + Guid.NewGuid().ToString("N"));
        var profile = Path.Combine(root, "P1");
        Directory.CreateDirectory(profile);
        try
        {
            var source = Path.Combine(PersistenceFixture.Root, "contract", "seed", "P1");
            foreach (var file in Directory.EnumerateFiles(source, "*", SearchOption.AllDirectories))
            {
                var destination = Path.Combine(profile, Path.GetRelativePath(source, file));
                Directory.CreateDirectory(Path.GetDirectoryName(destination)!);
                File.Copy(file, destination);
            }

            var path = Path.Combine(profile, "source", "pay_periods.jsonl.gz");
            string content;
            using (var file = File.OpenRead(path))
            using (var gzip = new GZipStream(file, CompressionMode.Decompress))
            using (var read = new StreamReader(gzip))
            {
                var first = JsonNode.Parse(read.ReadLine()!)!;
                first["Hours_Worked"] = new JsonArray(1, 2);
                content = first.ToJsonString() + "\n" + read.ReadToEnd();
            }

            var bytes = Encoding.UTF8.GetBytes(content);
            using (var file = File.Create(path))
            using (var gzip = new GZipStream(file, CompressionLevel.SmallestSize))
            {
                gzip.Write(bytes);
            }

            var manifestPath = Path.Combine(profile, "manifest.json");
            var manifest = JsonNode.Parse(File.ReadAllText(manifestPath))!;
            var table = manifest["tables"]!["source/pay_periods.jsonl.gz"]!;
            table["sha256"] = Convert.ToHexStringLower(SHA256.HashData(File.ReadAllBytes(path)));
            table["content_sha256"] = Convert.ToHexStringLower(SHA256.HashData(bytes));
            File.WriteAllText(manifestPath, manifest.ToJsonString());
            Assert.Throws<InvalidDataException>(() => new SeedImporter(fixture.Database, root, PersistenceFixture.Root).Load("P1"));
            Assert.Equal(9477, new SourceSeedData(fixture.Database).ReadTable("pay_periods").Count());
        }
        finally
        {
            foreach (var file in Directory.EnumerateFiles(root, "*", SearchOption.AllDirectories))
            {
                File.Delete(file);
            }

            foreach (var directory in Directory.EnumerateDirectories(root, "*", SearchOption.AllDirectories).OrderByDescending(d => d.Length))
            {
                Directory.Delete(directory);
            }

            Directory.Delete(root);
        }
    }
}
