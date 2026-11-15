using System.Text.Json;
using TaxCredit.Domain.Claims;
using TaxCredit.Domain.Designations;
using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Pipeline;
using TaxCredit.Domain.Programs;
using TaxCredit.Domain.Warehouse;
using TaxCredit.Infrastructure.Payroll;
using TaxCredit.Infrastructure.Rules;

namespace TaxCredit.Infrastructure.Persistence.Tests.GoldWrite;

internal static class PipelineInputs
{
    internal static ClientCalculation Create(JsonElement record, IClaimSink claims, IBaseYearOverrides overrides, IGoldWriter writer)
    {
        var meta = GoldenPayload.Records("gold_payload.jsonl.gz").First();
        var payroll = Payroll(record);
        var library = new RuleLibrary(new JsonRulePackSource(new RulePackOptions
        {
            RulesDirectory = Path.Combine(PersistenceFixture.Root, "backend", "rules"),
        }));
        var defaults = new ProgramDefaults(library, client => PayrollRows.StatesPresent(payroll.LoadPayPeriods(client)));
        var fiscal = new FiscalSource(library, new NoFiscalRules());
        var clockReads = 0;
        PyDateTime Clock() => new(new DateOnly(2026, 11, 15), 9, 30, 15 + clockReads++, 0, null);
        DateOnly Today() => new(2026, 11, 15);
        var assumptions = AssumptionFiles.Read(Path.Combine(PersistenceFixture.Root, "backend", "rules", "methodology"));
        Assert.Equal(meta.GetProperty("assumptions").EnumerateArray().Select(a => a.GetProperty("sha256").GetString()), assumptions.Select(a => a.Sha256));
        var parts = new ClientCalculationParts(library, defaults, new ClientRunResolver(library, defaults, fiscal, payroll),
            new RunFingerprint(library, fiscal), Designations(meta), payroll, overrides,
            new ClientAssessment(library, fiscal, Today, Clock, () => Guid.NewGuid().ToString()), claims, writer);
        return new ClientCalculation(parts, new ClientCalculationConfig(meta.GetProperty("freezes").GetProperty("git_commit").GetString()!,
            assumptions, meta.GetProperty("section_9_query_count").GetInt64(), Today, Clock,
            () => record.GetProperty("out").GetProperty("run_id").GetString()!));
    }

    internal static RunClientCalculationCommand Command(JsonElement record)
    {
        var args = record.GetProperty("args");
        string? Text(string name) => args.TryGetProperty(name, out var value) ? value.GetString() : null;
        return new RunClientCalculationCommand(args.GetProperty("client_id").GetInt64(), args.GetProperty("tax_year").GetInt64(),
            Text("state"), Text("program_code"), args.TryGetProperty("assess_tax_years", out var years)
                ? years.EnumerateArray().Select(y => y.GetInt64()).ToArray() : null, Text("actor") ?? "system");
    }

    internal static void Seed(JsonElement record, IClaimSink claims, IManualOverrideRepository overrides)
    {
        var moment = new PyDateTime(new DateOnly(2026, 11, 15), 9, 0, 0, 0, 0);
        foreach (var seed in record.GetProperty("seed_claims").EnumerateArray())
        {
            var status = ClaimEnumExtensions.StatusFromValue(seed[3].GetString()!);
            claims.Record(ProgramClaim.Create(new ClaimSpec
            {
                ClientId = seed[0].GetInt64(),
                ProgramCode = seed[1].GetString(),
                TaxYear = seed[2].GetInt64(),
                Status = status,
                IdentifiedUsd = seed[4].GetString(),
                DecidedBy = "analyst",
                DeclineReason = status == ClaimStatus.Declined ? "prefers R&D" : null,
                EffectiveFrom = moment,
            }));
        }

        foreach (var group in record.GetProperty("overrides").EnumerateArray())
        {
            foreach (var pair in group[2].EnumerateArray())
            {
                overrides.Record(new ManualOverride(Guid.NewGuid().ToString(), "saved-before-run", group[0].GetInt64(),
                    "unit", WarehouseVocabulary.BaseYearKey(group[1].GetString()!, pair[0].GetString()!), "base_year",
                    null, pair[1].GetRawText(), "approved", "Golden saved-base-year scenario.", "tests", moment));
            }
        }
    }

    private static IPayrollSource Payroll(JsonElement record)
    {
        if (record.GetProperty("source").GetProperty("kind").GetString() == "csv")
        {
            return new CsvPayrollSource(Path.Combine(PersistenceFixture.Root, "backend", "data", "payroll_pay_periods.csv"), 1001);
        }

        var client = record.GetProperty("args").GetProperty("client_id").GetInt64();
        var input = GoldenPayload.Records("gold_payload_input.jsonl.gz").First(r => r.GetProperty("k").GetString() == "rows" && r.GetProperty("client").GetInt64() == client);
        var columns = input.GetProperty("columns").EnumerateArray().Select(c => c.GetString()!).ToArray();
        var rows = input.GetProperty("rows").EnumerateArray().Select(row =>
        {
            var dictionary = new PyDict();
            for (var i = 0; i < columns.Length; i++)
            {
                var value = row[i];
                dictionary.Add(columns[i], value.ValueKind switch
                {
                    JsonValueKind.Null => null,
                    JsonValueKind.String => value.GetString(),
                    JsonValueKind.Number when columns[i] is "Hours_Worked" or "Gross_Wages" => (object)value.GetDouble(),
                    JsonValueKind.Number => value.GetInt64(),
                    _ => throw new InvalidDataException("Unexpected payroll input kind."),
                });
            }

            return PayRow.Of(dictionary);
        }).ToArray();
        return new InMemoryPayrollSource(new Dictionary<long, IReadOnlyList<PayRow>> { [client] = rows });
    }

    private static DesignationRegistry Designations(JsonElement meta)
    {
        var data = meta.GetProperty("designations");
        IReadOnlyList<PyDict> History(JsonElement rows) => rows.EnumerateArray().Select(r => (PyDict)PyJson.Loads(r.GetRawText())!).ToArray();
        var legacy = data.GetProperty("legacy").EnumerateArray()
            .Select(r => new KeyValuePair<string, IReadOnlyList<PyDict>>(r[0].GetString()!, History(r[1]))).ToArray();
        var source = data.GetProperty("source").EnumerateArray()
            .Select(r => new SourceDesignation(r[0].GetInt64(), r[1].GetString()!, History(r[2]))).ToArray();
        return new DesignationRegistry(legacy, source, History(data.GetProperty("synthetic_ga_default")), () => true);
    }
}

internal sealed class CertifyingWriter(GoldRunPayload expected, IGoldWriter inner) : IGoldWriter
{
    public IReadOnlyList<KeyValuePair<string, long>> WriteRun(GoldRunPayload payload)
    {
        GoldenPayload.Equal(expected, payload);
        return inner.WriteRun(payload);
    }

    public IReadOnlyList<(string Query, long RowCount)> Validate() => inner.Validate();
}
