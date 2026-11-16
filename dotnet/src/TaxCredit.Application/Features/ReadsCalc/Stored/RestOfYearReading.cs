using TaxCredit.Application.Ports.Persistence;
using TaxCredit.Domain.Calculation;
using TaxCredit.Domain.Designations;
using TaxCredit.Domain.Pipeline;
using static TaxCredit.Application.Features.ReadsCalc.ReadValues;

namespace TaxCredit.Application.Features.ReadsCalc.Stored;

/// <summary>Shared employee checkpoint reading for the near-miss cohort, unit drawer and employee walk.</summary>
public sealed class RestOfYearReading(IGoldReadPort gold, DesignationRegistry designations)
{
    internal void Attach(IReadOnlyList<Dictionary<string, object?>> rows, long client, int year, string run,
        ResolvedStatute statute, DateOnly asOf, string method = "min_max")
    {
        var tokens = rows.Select(row => Text(row.GetValueOrDefault("record_token"))).Where(token => token.Length > 0).ToArray();
        if (tokens.Length == 0)
        {
            return;
        }
        var periods = gold.CohortPeriods(client, year, run, tokens);
        foreach (var row in rows)
        {
            if (periods.TryGetValue(Text(row.GetValueOrDefault("record_token")), out var held))
            {
                row["rest_of_year"] = Proximity.RestOfYear(held.Select(Engine).ToArray(), statute.Floors, asOf, statute.Window.End, method);
                foreach (var item in Where(held, client, year))
                {
                    row[item.Key] = item.Value;
                }
            }
        }
    }

    internal Dictionary<string, object?> Where(IReadOnlyList<IReadOnlyDictionary<string, object?>> periods, long client, int year)
    {
        var hours = new Dictionary<string, double>(StringComparer.Ordinal);
        foreach (var period in periods)
        {
            var site = Text(period.GetValueOrDefault("worksite_id"));
            if (site.Length > 0)
            {
                hours[site] = hours.GetValueOrDefault(site) + Number(period.GetValueOrDefault("hours"));
            }
        }
        if (hours.Count == 0)
        {
            return Map();
        }
        var primary = hours.MaxBy(pair => pair.Value).Key;
        var designation = designations.DesignationAt(primary, year, client);
        return Map(("worksite_id", primary), ("worksites", hours.Keys.Order(StringComparer.Ordinal).ToArray()),
            ("designation", designation?.TryGetValue("designation", out var name) is true ? name : null),
            ("tier", designation?.TryGetValue("tier", out var tier) is true ? tier : null),
            ("tier_source", designation is null ? "unassigned" : "prototype"));
    }
}
