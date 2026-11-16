using System.Globalization;
using TaxCredit.Domain.Numerics;

namespace TaxCredit.Application.Features.ClaimsArtifactsRules.Portfolio;

internal static class PortfolioOrdering
{
    internal static string Name(string sort) => sort.ToLowerInvariant() switch
    {
        "" or "band" => "priority",
        "gap_jobs" or "jobs_gap" => "jobs_to_threshold",
        "margin" => "jobs_margin",
        "variance" => "variance_usd",
        "opportunity" => "opportunity_usd",
        "identified" => "identified_usd",
        "client" => "client_id",
        var other => other,
    };

    internal static double Value(PyDict item, string sort, bool descending)
    {
        object? Get(string key) => item.TryGetValue(key, out var value) ? value : null;
        double Zero(string key) => Get(key) is { } v ? Convert.ToDouble(v, CultureInfo.InvariantCulture) : 0;
        double Nullable(string key) => Get(key) is { } v ? Convert.ToDouble(v, CultureInfo.InvariantCulture)
            : descending ? double.NegativeInfinity : double.PositiveInfinity;
        return Name(sort) switch
        {
            "priority" => (Get("priority_rank") is null ? 99 : Zero("priority_rank")) - Math.Min(Zero("identified_usd") / 1e12, .999),
            "jobs_to_threshold" => Nullable("gap_jobs"),
            "jobs_margin" => Nullable("jobs_margin"),
            "variance_usd" or "opportunity_usd" or "identified_usd" or "claimed_usd" => Nullable(Name(sort)),
            "tax_year" => Zero("tax_year"),
            "client_id" => Zero("client_id"),
            "status" => (Get("status") as string)?.Length ?? 0,
            _ => 0,
        };
    }

    internal static IEnumerable<PyDict> Sort(IEnumerable<PyDict> rows, string sort, bool descending) =>
        descending ? rows.OrderByDescending(r => Value(r, sort, true)) : rows.OrderBy(r => Value(r, sort, false));
}
