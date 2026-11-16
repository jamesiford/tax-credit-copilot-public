using System.Globalization;
using System.Security.Cryptography;
using System.Text;
using TaxCredit.Application.Ports.Auth;
using TaxCredit.Application.Ports.Contract;
using TaxCredit.Application.Ports.Sources;
using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Pipeline;
using TaxCredit.Domain.Programs;
using TaxCredit.Domain.Runs;
using TaxCredit.Domain.Warehouse;

namespace TaxCredit.Application.Features.DraftsRuns;

/// <summary>Cheap planning reads the book, footprint and manifests, never payroll or the engine.</summary>
public sealed class BatchPlanner(ISourceReader source, BatchSelection selection, RuleLibrary rules,
    IRunManifestRepository manifests, ClientCalculationConfig calculation, IClientAuthorizer authorizer,
    IApiPrincipalAccessor principals, IRuntimeConfiguration configuration)
{
    internal int MaxItems => Setting("RUN_BATCH_MAX_ITEMS", 5000);
    internal int ConfirmAbove => Setting("RUN_BATCH_CONFIRM_ABOVE", 25);

    /// <summary>Resolves clients and programs once so preview, counters and queued items describe the same request.</summary>
    public async ValueTask<BatchPlan> Plan(BatchRequest request, CancellationToken cancellationToken)
    {
        ArgumentNullException.ThrowIfNull(request);
        var book = source.ListAccounts().ToDictionary(c => c.AccountId);
        var footprint = source.Footprint();
        var explicitIds = request.Scope is ScopeKind.One or ScopeKind.List;
        var wanted = explicitIds ? request.Clients : book.Keys.Order().ToArray();
        if (wanted.Any(id => !book.ContainsKey(id)))
        {
            throw BatchRequest.Refuse("unknown_clients", "These clients are not in the client book.", "Remove them or check the ids.");
        }
        var ids = new List<long>();
        foreach (var id in wanted)
        {
            var allowed = await authorizer.IsAuthorizedAsync(principals.Current ?? ApiPrincipal.Anonymous, id, cancellationToken).ConfigureAwait(false);
            if (!allowed && explicitIds) { throw new AuthRefusalException(403, "client_refused", "Not authorized for a selected client."); }
            if (allowed && (request.Scope != ScopeKind.Filter || selection.Matches(id, request.Filter, footprint.GetValueOrDefault(id) ?? []))) { ids.Add(id); }
        }
        if (ids.Count == 0) { throw BatchRequest.Refuse("empty_scope", "The selection matches no clients.", "Check the client ids or the filter."); }
        var pairs = Pairs(ids, request.ProgramCode, footprint);
        return new BatchPlan(ids, ids.ToDictionary(id => id, id => book[id].Name), pairs, Summary(request, ids, book, pairs));
    }

    internal static PyDict Spec(BatchRequest request, BatchPlan plan)
    {
        var spec = new PyDict().Add("client_count", (long)plan.Clients.Count)
            .Add("clients_sha256", ClientDigest(plan.Clients));
        if (request.Filter.Count > 0) { spec.Add("filter", request.Filter); }
        if (plan.Clients.Count <= 50) { spec.Add("client_ids", plan.Clients.Order().Cast<object?>().ToList()); }
        return spec.Add("kind", request.Kind.Value()).Add("program_code", request.ProgramCode)
            .Add("tax_years", request.TaxYears.Cast<object?>().ToList()).Add("force", request.Force).Add("skip_unchanged", request.SkipUnchanged)
            .Add("include_code_commit", request.IncludeCodeCommit).Add("refresh_once", request.RefreshOnce).Add("program_items", (long)plan.Pairs.Count);
    }

    internal static string ClientDigest(IEnumerable<long> clients)
    {
        var encoded = PyJson.Dumps(clients.Order().Cast<object?>().ToList(), sortKeys: true, compact: false);
        return Convert.ToHexStringLower(SHA256.HashData(Encoding.UTF8.GetBytes(encoded)))[..16];
    }

    private List<(long Client, string? Program)> Pairs(List<long> ids, string? program,
        IReadOnlyDictionary<long, IReadOnlyList<string>> footprint)
    {
        var options = rules.LoadRegistry().Active().Where(e => e.State is not null && rules.AuthoredYears(e.PackFile).Count > 0).ToArray();
        return ids.SelectMany(id =>
        {
            if (!string.IsNullOrEmpty(program)) { return new[] { (id, (string?)program) }; }
            var states = footprint.GetValueOrDefault(id) ?? [];
            var codes = options.Where(e => states.Contains(e.State!, StringComparer.OrdinalIgnoreCase)).Select(e => (string?)e.Code).ToArray();
            return (codes.Length == 0 ? new string?[] { null } : codes).Select(code => (id, code));
        }).ToList();
    }

    private PyDict Summary(BatchRequest request, List<long> ids, Dictionary<long, SourceAccount> book,
        List<(long Client, string? Program)> pairs)
    {
        selection.CheckAvailable(ids);
        var reads = ids.Take(200).ToDictionary(id => id, LastRun);
        var coverage = reads.Values.Where(r => r.ContainsKey("coverage")).Select(r => (string)r["coverage"]!).Distinct(StringComparer.Ordinal).ToArray();
        var count = pairs.Count * Math.Max(1, request.TaxYears.Count);
        var programs = new PyDict();
        foreach (var group in pairs.GroupBy(p => p.Program ?? "none")) { programs.Add(group.Key, (long)group.Count()); }
        return new PyDict().Add("kind", request.Kind.Value()).Add("clients", (long)ids.Count).Add("items", (long)count)
            .Add("years", request.TaxYears.Count > 0 ? request.TaxYears.Cast<object?>().ToList() : "latest runnable year per client")
            .Add("refresh_once", request.RefreshOnce).Add("force", request.Force).Add("skip_unchanged", request.SkipUnchanged)
            .Add("skip_coverage", coverage.Length == 0 ? "none_yet" : coverage.Length == 1 ? coverage[0] : "mixed")
            .Add("per_client_year_items", request.TaxYears.Count > 1)
            .Add("skip_candidates_upper_bound", reads.Count != ids.Count ? null :
                (object)(request.SkipUnchanged && !request.Force ? (long)reads.Values.Count(r => r["can_skip"] is true) : 0L))
            .Add("never_run", (long)reads.Values.Count(r => (string)r["state"]! == "never_run")).Add("manifests_read_for", (long)reads.Count)
            .Add("requires_confirmation", count > ConfirmAbove).Add("confirm_above", (long)ConfirmAbove).Add("max_items", (long)MaxItems)
            .Add("over_size_limit", count > MaxItems)
            .Add("first_items", ids.Take(20).Select(id => (object?)new PyDict().Add("client_id", id).Add("client_name", book[id].Name).Add("last_run", reads[id])).ToList())
            .Add("notes", new List<object?> {
                request.SkipUnchanged && !request.Force ? "Whether a client is skipped as unchanged is decided when its item starts; this is an upper bound, not a promise." : "Nothing is skipped: every item runs.",
                "Each run replays every authored year of the client's payroll, whatever year it is asked for." })
            .Add("programs", programs).Add("multi_program_clients", (long)pairs.GroupBy(p => p.Client).Count(g => g.Count() > 1))
            .Add("program_items", (long)pairs.Count).Add("unavailable", new List<object?>()).Add("unavailable_checked", true);
    }

    private PyDict LastRun(long id)
    {
        var last = manifests.Latest(id);
        if (last is null) { return new PyDict().Add("state", "never_run").Add("can_skip", false).Add("reason", "no earlier successful run"); }
        var recorded = new[] { last.Step1AssumptionSha256, last.OnezeroAssumptionSha256 }.Where(s => !string.IsNullOrEmpty(s)).ToArray();
        var known = !string.IsNullOrEmpty(last.CalculationId) && !string.IsNullOrEmpty(last.RulePackVersion)
            && recorded.Length > 0 && !string.IsNullOrEmpty(last.SourceSnapshotId);
        var matches = known && recorded.All(hash => calculation.Assumptions.Any(a => a.Sha256 == hash));
        return new PyDict().Add("state", "has_run").Add("run_id", last.RunId).Add("tax_year", last.TaxYear)
            .Add("completed_at", last.RunCompletedAt?.IsoFormat()).Add("can_skip", matches)
            .Add("coverage", string.IsNullOrEmpty(last.SourceSnapshotId) ? "cannot_tell_yet" : "all_years")
            .Add("reason", matches ? "assumption hashes match the last run; the data is checked when the item starts"
                : "the last run does not record a client-wide data fingerprint or what is needed to compare, or the assumptions changed");
    }

    private int Setting(string name, int fallback) =>
        int.TryParse(configuration.Get(name), NumberStyles.Integer, CultureInfo.InvariantCulture, out var value) && value > 0 ? value : fallback;
}

/// <summary>A resolved immutable request plan; no accepted work exists until the repository creates it.</summary>
public sealed record BatchPlan(IReadOnlyList<long> Clients, IReadOnlyDictionary<long, string> Names,
    IReadOnlyList<(long Client, string? Program)> Pairs, PyDict Summary);
