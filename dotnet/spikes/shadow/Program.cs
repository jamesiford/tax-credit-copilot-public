using System.Text.Json;
using PlatformSpike;

namespace TaxCredit.Shadow;

internal static class Program
{
    private static int Main(string[] args)
    {
        if (args is not ["--self-test"])
        {
            Console.WriteLine("{\"verdict\":\"refused\"}");
            return 2;
        }

        try
        {
            var previous = Console.Out;
            int fixtures;
            try
            {
                Console.SetOut(TextWriter.Null);
                fixtures = ScratchGuard.SelfTest();
            }
            finally
            {
                Console.SetOut(previous);
            }

            var catalogue = JsonSerializer.Deserialize<Dictionary<string, string>>(
                File.ReadAllText(Path.Combine(AppContext.BaseDirectory, "sql-catalogue.json")))
                ?? throw new InvalidOperationException("Missing closed catalogue.");
            foreach (var statement in catalogue.Values)
            {
                ObservationGuard.Check(statement, catalogue.Values);
            }

            var ownershipCases = BoundarySelfTest.Cleanup();
            if (fixtures != 31) { throw new InvalidOperationException("Inherited fixture count changed."); }
            Console.WriteLine(JsonSerializer.Serialize(new { verdict = "passed", inherited_fixtures = fixtures, templates = catalogue.Count, ownership_cases = ownershipCases }));
            return 0;
        }
        catch (Exception exception) when (exception is GuardRefusal or IOException or JsonException or InvalidOperationException)
        {
            Console.WriteLine("{\"verdict\":\"guard-failed\"}");
            return 1;
        }
    }
}
