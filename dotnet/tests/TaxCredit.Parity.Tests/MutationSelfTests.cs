using System.Diagnostics;
using System.Globalization;
using Xunit.Abstractions;

namespace TaxCredit.Parity.Tests;

/// <summary>
/// Mutation self-test: proves the parity harness can fail. For each mutation, the Domain sources are copied to a scratch
/// tree, one deliberate defect is applied (a rounding mode, a comparison, a sort tie-break), and the golden and
/// differential-fuzz tests are run against that copy; they must FAIL. Slow (a build per mutation), so it runs only when
/// <c>TCC_RUN_MUTATION_TESTS=1</c>; the result of the last run is recorded in <c>docs/parity-report.md</c>.
/// </summary>
public sealed class MutationSelfTests(ITestOutputHelper output)
{
    private static readonly (string Name, string File, string Old, string New)[] Mutations =
    [
        ("rounding: half-up becomes half-even", @"src\TaxCredit.Domain\Calculation\OneZeroEligibility.cs", "PyRoundingMode.HalfUp", "PyRoundingMode.HalfEven"),
        ("comparison: >= floor becomes > floor", @"src\TaxCredit.Domain\Calculation\OneZeroEligibility.cs", "avgHours + 1e-9 >= minHours", "avgHours + 1e-9 > minHours"),
        ("sum: a 3.14-style compensated int after a float", @"src\TaxCredit.Domain\Numerics\PySum.cs", "f += (double)items[i].IntValue;", "var xi = (double)items[i].IntValue; var ti = f + xi; c += Math.Abs(f) >= Math.Abs(xi) ? (f - ti) + xi : (xi - ti) + f; f = ti;"),
        ("sort: stable tie-break reversed", @"src\TaxCredit.Domain\Numerics\PySort.cs", "return x.Index.CompareTo(y.Index);", "return y.Index.CompareTo(x.Index);"),
        ("proximity rounding: half-up becomes banker's on the binary value", @"src\TaxCredit.Domain\Calculation\ProximityCoerce.cs", "return OneZeroEligibility.RoundHalfUp(value, places);", "return PyRound.Round(value, places);"),
        ("proximity comparison: hours floor >= becomes >", @"src\TaxCredit.Domain\Calculation\Proximity.cs", "var passedHours = avgHours >= minHours;", "var passedHours = avgHours > minHours;"),
        ("proximity comparison: recorded verdict ignored", @"src\TaxCredit.Domain\Calculation\Proximity.cs", "var eligible = recorded is not null ? ProximityCoerce.Truthy(recorded) : derived;", "var eligible = derived;"),
        ("proximity max/min inversion: the larger need no longer binds", @"src\TaxCredit.Domain\Calculation\Proximity.cs", "PyArith.Max(needs)", "PyArith.Min(needs)"),
        ("proximity max/min inversion: the smaller cushion no longer binds", @"src\TaxCredit.Domain\Calculation\Proximity.cs", "PyArith.Min(hoursHeadroom, wagesHeadroomHours.Value)", "PyArith.Max(hoursHeadroom, wagesHeadroomHours.Value)"),
        ("proximity ordering: id tie-break reversed", @"src\TaxCredit.Domain\Calculation\ProximityCohorts.cs", "PyStr.Compare(x.Id, y.Id)", "PyStr.Compare(y.Id, x.Id)"),
        ("proximity counting: population no longer overrides the ineligible count", @"src\TaxCredit.Domain\Calculation\ProximityCohorts.cs", ".Add(\"ineligible\", usePopulation ? ProximityCoerce.ToInt(Req(population!, \"ineligible\")) : (long)ineligible.Count)", ".Add(\"ineligible\", (long)ineligible.Count)"),
        ("decimal rounding: the 28-digit context rounds half up instead of half even", @"src\TaxCredit.Domain\Numerics\PyDecimalOps.cs", "if (cmp > 0 || (cmp == 0 && !q.IsEven))", "if (cmp >= 0)"),
        ("claims rounding: fallen_by rounds away from zero instead of half even", @"src\TaxCredit.Domain\Claims\ClaimReadings.cs", "PyRound.Round(peak.AverageHeadcount.Value - latest.AverageHeadcount.Value, 2)", "Math.Round(peak.AverageHeadcount.Value - latest.AverageHeadcount.Value, 2, MidpointRounding.AwayFromZero)"),
        ("claims rounding: jobs_margin truncates instead of rounding", @"src\TaxCredit.Domain\Claims\ProgramClaim.Readings.cs", "PyRound.Round(netNew - threshold, 2)", "Math.Truncate((netNew - threshold) * 100) / 100"),
        ("claims comparison: materiality <= becomes < (confirmed)", @"src\TaxCredit.Domain\Claims\ProgramClaim.Readings.cs", "PyDecimalOps.Compare(PyDecimalOps.Abs(variance), ClaimMoney.Materiality) <= 0", "PyDecimalOps.Compare(PyDecimalOps.Abs(variance), ClaimMoney.Materiality) < 0"),
        ("claims comparison: materiality <= becomes < (correctly not claimed)", @"src\TaxCredit.Domain\Claims\ProgramClaim.Readings.cs", "PyDecimalOps.Compare(IdentifiedUsd, ClaimMoney.Materiality) <= 0", "PyDecimalOps.Compare(IdentifiedUsd, ClaimMoney.Materiality) < 0"),
        ("claims comparison: on the line is exclusive of one whole job", @"src\TaxCredit.Domain\Claims\ProgramClaim.Readings.cs", "Math.Abs(margin) <= OnTheLineJobs", "Math.Abs(margin) < OnTheLineJobs"),
        ("claims gate: exposure no longer needs a verified claim", @"src\TaxCredit.Domain\Claims\ProgramClaim.Readings.cs", "if (IsExposure && Provenance.Verified())", "if (IsExposure)"),
        ("claims gate: an unverified claim is netted into the outstanding test", @"src\TaxCredit.Domain\Claims\ProgramClaim.Readings.cs", "var outstanding = Provenance.Verified() ? OpportunityUsd : IdentifiedUsd;", "var outstanding = OpportunityUsd;"),
        ("claims clamp: jobs_to_threshold no longer clamps at zero", @"src\TaxCredit.Domain\Claims\ProgramClaim.Readings.cs", "PyRound.Round(gap > 0.0 ? gap : 0.0, 2)", "PyRound.Round(gap, 2)"),
        ("claims comparison: declining peak takes the last maximum instead of the first", @"src\TaxCredit.Domain\Claims\ClaimReadings.cs", "if (c.AverageHeadcount > peak.AverageHeadcount)", "if (c.AverageHeadcount >= peak.AverageHeadcount)"),
        ("claims ordering: band rank of declining moves below unclaimed", @"src\TaxCredit.Domain\Claims\ClaimEnumExtensions.cs", "PriorityBand.Declining => 2,", "PriorityBand.Declining => 4,"),
        ("coverage ordering: identified dollars ascending within a band", @"src\TaxCredit.Domain\Claims\CoverageSituation.cs", "-c.IdentifiedUsd.ToDouble()", "c.IdentifiedUsd.ToDouble()"),
        ("coverage ordering: tax year tie-break reversed", @"src\TaxCredit.Domain\Claims\CoverageSituation.cs", "x.TaxYear.CompareTo(y.TaxYear)", "y.TaxYear.CompareTo(x.TaxYear)"),
        ("coverage ordering: programme totals in insertion order, not sorted", @"src\TaxCredit.Domain\Claims\Coverage.cs", "PySort.Sorted(grouped.Keys, k => k, PyStr.Comparer)", "grouped.Keys"),
        ("coverage netting: opportunity summed from the signed variance", @"src\TaxCredit.Domain\Claims\Coverage.cs", "claims.Select(c => c.OpportunityUsd)", "claims.Select(c => c.VarianceUsd)"),
        ("performance rounding: weekly average hours rounds half away from zero instead of half even", @"src\TaxCredit.Domain\Calculation\PerformanceDashboard.cs", ".Add(\"avg_weekly_hours\", PyRound.Round(avgHours, 2))", ".Add(\"avg_weekly_hours\", Math.Round(avgHours, 2, MidpointRounding.AwayFromZero))"),
        ("performance comparison: green needs strictly more than 1 + margin", @"src\TaxCredit.Domain\Calculation\PerformanceDashboard.cs", "worst >= 1.0 + margin ?", "worst > 1.0 + margin ?"),
        ("performance comparison: yellow needs strictly more than 1 - margin", @"src\TaxCredit.Domain\Calculation\PerformanceDashboard.cs", "worst >= 1.0 - margin ?", "worst > 1.0 - margin ?"),
        ("performance floor: a one-day span is no longer read as 0.01 weeks", @"src\TaxCredit.Domain\Calculation\PerformanceDashboard.cs", "PyArith.Max((double)days / 7.0, 0.01)", "((double)days / 7.0)"),
        ("performance ordering: status tie-break reversed within a worksite", @"src\TaxCredit.Domain\Calculation\PerformanceDashboard.cs", "c = PyStr.Compare(x.Status, y.Status);", "c = PyStr.Compare(y.Status, x.Status);"),
        ("reconciliation comparison: donut hole is inclusive of the tolerance", @"src\TaxCredit.Domain\Calculation\Reconciliation.cs", "if (pw > mw + tolerance)", "if (pw >= mw + tolerance)"),
        ("reconciliation comparison: the invariant is violated at exactly the tolerance", @"src\TaxCredit.Domain\Calculation\Reconciliation.cs", "if (!(u.PpAverage > u.MmAverage + InvariantTolerance))", "if (!(u.PpAverage >= u.MmAverage + InvariantTolerance))"),
        ("reconciliation rounding: the annual difference rounds half away from zero", @"src\TaxCredit.Domain\Calculation\Reconciliation.cs", "PyRound.Round(pp.AnnualAverage - mm.AnnualAverage, 2)", "Math.Round(pp.AnnualAverage - mm.AnnualAverage, 2, MidpointRounding.AwayFromZero)"),
        ("reconciliation rounding: the donut delta rounds half away from zero", @"src\TaxCredit.Domain\Calculation\Reconciliation.cs", ".Add(\"delta\", PyRound.Round(pw - mw, 2))", ".Add(\"delta\", Math.Round(pw - mw, 2, MidpointRounding.AwayFromZero))"),
        ("reconciliation ordering: units sorted by UTF-16 code unit, not code point", @"src\TaxCredit.Domain\Calculation\Reconciliation.cs", "ppSummary.Keys.Union(mmSummary.Keys, StringComparer.Ordinal), k => k, PyStr.Comparer)", "ppSummary.Keys.Union(mmSummary.Keys, StringComparer.Ordinal), k => k, StringComparer.Ordinal)"),
        ("rollups rounding: month totals round half away from zero", @"src\TaxCredit.Domain\Calculation\Rollups.cs", "sums.Select(c => PyRound.Round(c, 2))", "sums.Select(c => Math.Round(c, 2, MidpointRounding.AwayFromZero))"),
        ("rollups sum: totals use a naive running sum instead of Python's compensated sum", @"src\TaxCredit.Domain\Calculation\Rollups.cs", "PyRound.Round(PySum.Sum(cols), 2)", "PyRound.Round(cols.Sum(), 2)"),
        ("rollups comparison: an empty text key is no longer unattributed", @"src\TaxCredit.Domain\Calculation\Rollups.cs", "|| !ProximityCoerce.Truthy(v))", "|| v is null or 0L or false)"),
        ("rollups ordering: field keys sorted by UTF-16 code unit, not code point", @"src\TaxCredit.Domain\Calculation\Rollups.cs", "PySort.Sorted(byKey.Keys, k => k, PyStr.Comparer)", "PySort.Sorted(byKey.Keys, k => k, StringComparer.Ordinal)"),
        ("rollups ordering: the second field tie-break is reversed", @"src\TaxCredit.Domain\Calculation\Rollups.cs", "return c != 0 ? c : PyStr.Compare(x.B, y.B);", "return c != 0 ? c : PyStr.Compare(y.B, x.B);"),
        ("models comparison: a fiscal window of one day is accepted", @"src\TaxCredit.Domain\Warehouse\RunManifest.cs", "if (FiscalYearEnd <= FiscalYearBegin)", "if (FiscalYearEnd < FiscalYearBegin)"),
        ("models comparison: the scope check is case-insensitive", @"src\TaxCredit.Domain\Warehouse\ManualOverride.cs", "OverrideScopes.Contains(Scope))", "OverrideScopes.Contains(Scope.ToLowerInvariant()))"),
        ("models ordering: the allowed statuses are listed unsorted", @"src\TaxCredit.Domain\Warehouse\RunManifest.cs", "PySort.Sorted(set, s => s, PyStr.Comparer).Select(PyStr.Repr)", "set.Select(PyStr.Repr)"),
        ("models comparison: a draft program is derived like any other", @"src\TaxCredit.Domain\Programs\ProgramEntry.cs", "Lifecycle is \"retired\" or \"draft\"", "Lifecycle is \"retired\""),
        ("models equality: a finding's detail compares by reference, not as a dict", @"src\TaxCredit.Domain\Findings\FindingResolution.cs", "&& PyEquality.Equal(Detail, other.Detail)", "&& ReferenceEquals(Detail, other.Detail)"),
        ("open year comparison: a window ending today is still open", @"src\TaxCredit.Domain\Calculation\OpenYear.cs", "return end > (on ?? (today ?? Today)());", "return end >= (on ?? (today ?? Today)());"),
        ("open year comparison: net new equal to the threshold no longer qualifies", @"src\TaxCredit.Domain\Calculation\OpenYear.cs", "netNew >= yearThreshold && netNew > 0", "netNew > yearThreshold && netNew > 0"),
        ("open year clamp: net new is no longer clamped at zero", @"src\TaxCredit.Domain\Calculation\OpenYear.cs", "PyArith.Max(0.0, average - ProximityCoerce.ToFloat(trend.BaseAverageHeadcount))", "(average - ProximityCoerce.ToFloat(trend.BaseAverageHeadcount))"),
        ("runs transition: a failed item may also be cancelled", @"src\TaxCredit.Domain\Runs\RunStateMachine.cs", "[ItemStatus.Failed] = new HashSet<ItemStatus> { ItemStatus.Queued },", "[ItemStatus.Failed] = new HashSet<ItemStatus> { ItemStatus.Queued, ItemStatus.Cancelled },"),
        ("runs transition: a queued item can no longer be cancelled", @"src\TaxCredit.Domain\Runs\RunStateMachine.cs", "[ItemStatus.Queued] = new HashSet<ItemStatus> { ItemStatus.Leased, ItemStatus.Cancelled },", "[ItemStatus.Queued] = new HashSet<ItemStatus> { ItemStatus.Leased },"),
        ("runs transition: a running item cannot be given back to the queue", @"src\TaxCredit.Domain\Runs\RunStateMachine.cs", "ItemStatus.Succeeded, ItemStatus.Failed, ItemStatus.Queued,", "ItemStatus.Succeeded, ItemStatus.Failed,"),
        ("runs transition: moved no longer checks the state machine", @"src\TaxCredit.Domain\Runs\RunBatchItem.cs", "RunStateMachine.CheckItemMove(Status, status);", "_ = status;"),
        ("runs comparison: open items are judged by greater than zero, not non-zero", @"src\TaxCredit.Domain\Runs\RunStateMachine.cs", "if (openItems != 0)", "if (openItems > 0)"),
        ("runs comparison: started items are judged by greater than zero, not non-zero", @"src\TaxCredit.Domain\Runs\RunStateMachine.cs", "return started != 0 ?", "return started > 0 ?"),
        ("runs comparison: a batch with failures or cancellations needs both to be partial", @"src\TaxCredit.Domain\Runs\RunStateMachine.cs", "if (failed == 0 && cancelled == 0)", "if (failed == 0 || cancelled == 0)"),
        ("runs comparison: an all-failed batch reads cancelled", @"src\TaxCredit.Domain\Runs\RunStateMachine.cs", "return failed == 0 ? BatchStatus.Cancelled : BatchStatus.Failed;", "return failed == 0 ? BatchStatus.Failed : BatchStatus.Cancelled;"),
        ("runs comparison: an empty batch ignores the cancel request", @"src\TaxCredit.Domain\Runs\RunStateMachine.cs", "return cancelRequested ? BatchStatus.Cancelled : BatchStatus.Succeeded;", "return BatchStatus.Succeeded;"),
        ("runs comparison: an empty fingerprint value counts as known", @"src\TaxCredit.Domain\Runs\UnchangedRule.cs", "string.IsNullOrEmpty(before) || string.IsNullOrEmpty(now)", "before is null || now is null"),
        ("runs comparison: a different tax year is only a smaller one", @"src\TaxCredit.Domain\Runs\UnchangedRule.cs", "if (last.TaxYear != current.TaxYear)", "if (last.TaxYear < current.TaxYear)"),
        ("runs comparison: the code commit is compared when it was not asked for", @"src\TaxCredit.Domain\Runs\UnchangedRule.cs", "if (includeCodeCommit)", "if (!includeCodeCommit)"),
        ("runs ordering: the unchanged reasons are reported in reverse order", @"src\TaxCredit.Domain\Runs\UnchangedRule.cs", "return pairs;", "return pairs.AsEnumerable().Reverse().ToList();"),
        ("runs ordering: the enum wire strings of the skipped statuses are swapped", @"src\TaxCredit.Domain\Runs\RunEnums.cs", "\"skipped_unchanged\", \"skipped_no_payroll\", \"failed\"", "\"skipped_no_payroll\", \"skipped_unchanged\", \"failed\""),
        ("runs comparison: backoff float overflow starts one doubling late", @"src\TaxCredit.Domain\Runs\RetryPolicy.cs", "k >= 1024 ?", "k > 1024 ?"),
        ("runs comparison: backoff min keeps the exponential on a NaN cap", @"src\TaxCredit.Domain\Runs\RetryPolicy.cs", "return PyArith.Min(cap, x);", "return PyArith.Min(x, cap);"),
        ("runs rounding: the backoff jitter is 50 percent, not 25", @"src\TaxCredit.Domain\Runs\RetryPolicy.cs", "(0.25 * jitter())", "(0.5 * jitter())"),
        ("runs equality: refresh_once is ignored by RunBatch equality", @"src\TaxCredit.Domain\Runs\RunBatch.cs", "RefreshOnce == other.RefreshOnce", "true"),
        ("runs equality: counts compare by reference in RunBatch equality", @"src\TaxCredit.Domain\Runs\RunBatch.cs", "PyEquality.Equal(Counts, other.Counts)", "ReferenceEquals(Counts, other.Counts)"),
        ("drafts comparison: a program code may be 65 characters", @"src\TaxCredit.Domain\Programs\ProgramDraftRules.cs", "new(@\"^[A-Z][A-Z0-9_]{2,63}$\"", "new(@\"^[A-Z][A-Z0-9_]{2,64}$\""),
        ("drafts comparison: the code pattern no longer tolerates a trailing newline", @"src\TaxCredit.Domain\Programs\ProgramDraftRules.cs", "new(@\"^[A-Z][A-Z0-9_]{2,63}$\"", "new(@\"^[A-Z][A-Z0-9_]{2,63}\\z\""),
        ("drafts ordering: canonical json keeps insertion order", @"src\TaxCredit.Domain\Programs\ProgramDraftRules.cs", "sortKeys: true, compact: true, ensureAscii: false", "sortKeys: false, compact: true, ensureAscii: false"),
        ("drafts comparison: canonical json escapes non-ASCII like ensure_ascii", @"src\TaxCredit.Domain\Programs\ProgramDraftRules.cs", "sortKeys: true, compact: true, ensureAscii: false", "sortKeys: true, compact: true, ensureAscii: true"),
        ("drafts comparison: canonical json escapes DEL as a control character", @"src\TaxCredit.Domain\Numerics\PyJson.cs", "(!ascii && c >= ' ')", "(!ascii && c > '\u007f')"),
        ("drafts transition: a draft under review is editable", @"src\TaxCredit.Domain\Programs\DraftStatus.cs", "new HashSet<DraftStatus> { DraftStatus.Draft, DraftStatus.NeedsChanges }", "new HashSet<DraftStatus> { DraftStatus.Draft, DraftStatus.NeedsChanges, DraftStatus.ReadyForReview }"),
        ("drafts transition: an exported draft is closed", @"src\TaxCredit.Domain\Programs\DraftStatus.cs", "new HashSet<DraftStatus> { DraftStatus.Withdrawn }", "new HashSet<DraftStatus> { DraftStatus.Withdrawn, DraftStatus.Exported }"),
        ("drafts hierarchy: CustomerDataInDraft is no longer a ReviewRefused", @"src\TaxCredit.Domain\Programs\DraftErrors.cs", ": ReviewRefusal(\"CustomerDataInDraft\", message)", ": DraftError(\"CustomerDataInDraft\", message)"),
        ("drafts comparison: the customer data refusal reports the preview code", @"src\TaxCredit.Domain\Programs\DraftErrors.cs", "\"customer_data_refused\"", "\"preview_refused\""),
        ("drafts comparison: a surrogate run reports one position too few", @"src\TaxCredit.Domain\Numerics\PyUtf8.cs", "(start + length - 1)", "(start + length - 2)"),
        ("drafts equality: version is ignored by ProgramDraft equality", @"src\TaxCredit.Domain\Programs\ProgramDraft.cs", "Version == other.Version", "true"),
        ("drafts equality: the years compare by reference in ProgramDraft equality", @"src\TaxCredit.Domain\Programs\ProgramDraft.cs", "PyEquality.Equal(Years, other.Years)", "ReferenceEquals(Years, other.Years)"),
        ("credit math rounding: qualifying jobs round half away from zero", @"src\TaxCredit.Domain\Programs\RuleLibrary.Credit.cs", "var qualifying = PyRound.Round(PyArith.Max(0.0, PyArith.Max(0.0, average - prior) - threshold), 2);", "var qualifying = Math.Round(PyArith.Max(0.0, PyArith.Max(0.0, average - prior) - threshold), 2, MidpointRounding.AwayFromZero);"),
        ("credit math rounding: the annual credit rounds half away from zero", @"src\TaxCredit.Domain\Programs\RuleLibrary.Credit.cs", "RuleTree.RoundInt(qualifying * RuleTree.Float(perJob))", "RuleTree.Int(new System.Numerics.BigInteger(Math.Round(qualifying * RuleTree.Float(perJob), MidpointRounding.AwayFromZero)))"),
        ("credit math comparison: a NaN headcount delta no longer reads zero", @"src\TaxCredit.Domain\Programs\RuleLibrary.Credit.cs", "PyArith.Max(0.0, average - prior)", "Math.Max(0.0, average - prior)"),
        ("credit math comparison: a zero threshold override is ignored", @"src\TaxCredit.Domain\Programs\RuleLibrary.Credit.cs", "var threshold = thresholdOverride is not null", "var threshold = RuleTree.Truthy(thresholdOverride)"),
        ("credit math comparison: a per-job amount no longer wins over a percentage of wages", @"src\TaxCredit.Domain\Programs\RuleLibrary.Credit.cs", "if (benefit.ContainsKey(\"amount_per_qualifying_job_usd\"))", "if (!benefit.ContainsKey(\"amount_per_qualifying_job_pct_of_wages\") && benefit.ContainsKey(\"amount_per_qualifying_job_usd\"))"),
        ("credit math comparison: a zero floor reads as missing", @"src\TaxCredit.Domain\Programs\RuleLibrary.Packs.cs", "if (RuleTree.Get(oneZero, key) is null)", "if (!RuleTree.Truthy(RuleTree.Get(oneZero, key)))"),
        ("credit math comparison: ingestion overrides a year-resolved pack", @"src\TaxCredit.Domain\Programs\RuleLibrary.OneZero.cs", "var overridesFloors = !yearResolved;", "var overridesFloors = true;"),
        ("credit math comparison: a manifest older than the cached one is served from the cache", @"src\TaxCredit.Domain\Programs\RuleLibrary.cs", "hit.Stamp == stamp", "hit.Stamp >= stamp"),
        ("credit math ordering: authored years are listed newest first", @"src\TaxCredit.Domain\Programs\RuleLibrary.Packs.cs", "years.Sort();", "years.Sort(); years.Reverse();"),
        ("credit math ordering: the state list is in manifest order, not sorted", @"src\TaxCredit.Domain\Programs\ProgramRegistry.cs", "PySort.Sorted(_data(), kv => kv.Key, PyStr.Comparer).Select(kv => kv.Key).ToList()", "_data().Select(kv => kv.Key).ToList()"),
        ("credit math ordering: the last listed program of a state is its default", @"src\TaxCredit.Domain\Programs\ProgramRegistry.cs", "foreach (var entry in Active().Where(e => !string.IsNullOrEmpty(e.State)))", "foreach (var entry in Active().Where(e => !string.IsNullOrEmpty(e.State)).Reverse())"),
        ("pack validation comparison: a percentage-of-wages benefit is an error only when it is both a year pack and has years", @"src\TaxCredit.Domain\Programs\PackSemanticChecks.cs", "var severity = kind == PackKinds.Year || yearsAuthored ? \"error\" : \"warning\";", "var severity = kind == PackKinds.Year && yearsAuthored ? \"error\" : \"warning\";"),
        ("pack validation comparison: a year's floor is compared as text, so 35 and 35.0 disagree", @"src\TaxCredit.Domain\Programs\PackSemanticChecks.cs", "!PyEquality.Equal(RuleTree.Sub(block, key), RuleTree.Get(oz, key))", "RuleTree.Str(RuleTree.Sub(block, key)) != RuleTree.Str(RuleTree.Get(oz, key))"),
        ("pack validation comparison: any non-null value counts as a prototype flag", @"src\TaxCredit.Domain\Programs\PackSemanticChecks.cs", "kv.Key == PrototypeVerify && kv.Value is true", "kv.Key == PrototypeVerify && kv.Value is not null"),
        ("pack validation comparison: a base pack may not be named for a federal level unless it says so", @"src\TaxCredit.Domain\Programs\PackSemanticChecks.cs", "var expected = level is \"federal\" ?", "var expected = level is \"federal\" && kind == PackKinds.Base && false ?"),
        ("pack validation comparison: an unregistered pack is reported when it IS registered", @"src\TaxCredit.Domain\Programs\PackValidator.Files.cs", "if (!registered.ContainsKey(name))", "if (registered.ContainsKey(name))"),
        ("pack validation ordering: schema findings are left in the validator's order, not sorted by path", @"src\TaxCredit.Domain\Programs\PackValidator.cs", "PySort.Sorted(_schema.Validate(pack, kind), f => f.Path, PathComparer)", "_schema.Validate(pack, kind)"),
        ("pack validation ordering: the unverified flags are reported in reverse document order", @"src\TaxCredit.Domain\Programs\PackSemanticChecks.cs", "        return found;", "        found.Reverse(); return found;"),
        ("pack validation ordering: pack files are validated in reverse name order", @"src\TaxCredit.Domain\Programs\PackValidator.Files.cs", "PySort.Sorted(_source.ListJsonStems(folder).Select(stem => stem + \".json\"), n => n, PyStr.Comparer);", "PySort.Sorted(_source.ListJsonStems(folder).Select(stem => stem + \".json\"), n => n, PyStr.Comparer).AsEnumerable().Reverse().ToList();"),
        ("credit math fallback: a missing year reads the nearest earlier authored year", @"src\TaxCredit.Domain\Programs\RuleLibrary.Packs.cs", "var path = Within(program, $\"{taxYear.Value.ToString(CultureInfo.InvariantCulture)}.json\");", "var path = Within(program, $\"{(authored.Contains(taxYear.Value) ? taxYear.Value : authored.LastOrDefault(y => y < taxYear.Value, taxYear.Value)).ToString(CultureInfo.InvariantCulture)}.json\");"),
    ];

    [Fact]
    public void Each_deliberate_defect_in_a_copy_of_the_port_is_caught_by_the_harness()
    {
        if (Environment.GetEnvironmentVariable("TCC_RUN_MUTATION_TESTS") != "1")
        {
            output.WriteLine("skipped: set TCC_RUN_MUTATION_TESTS=1 to run (each mutation needs a build).");
            return;
        }

        var parity = GoldenFiles.ParityDirectory;
        var repo = Directory.GetParent(parity)!.FullName;
        var caught = new List<string>();
        var missed = new List<string>();
        // TCC_MUTATION_FILTER=performance,rollups runs only the mutations whose name contains one of the comma-separated terms.
        var terms = (Environment.GetEnvironmentVariable("TCC_MUTATION_FILTER") ?? string.Empty).Split(',', StringSplitOptions.RemoveEmptyEntries);
        foreach (var (name, file, oldText, newText) in Mutations.Where(m => terms.Length == 0 || terms.Any(t => m.Name.Contains(t, StringComparison.OrdinalIgnoreCase))))
        {
            var root = Path.Combine(Path.GetTempPath(), "tcc-mutant-" + Guid.NewGuid().ToString("N")[..8]);
            try
            {
                Copy(Path.Combine(repo, "dotnet"), Path.Combine(root, "dotnet"));
                Copy(parity, Path.Combine(root, "parity"));
                Run("cmd.exe", $"/c mklink /J \"{Path.Combine(root, "backend")}\" \"{Path.Combine(repo, "backend")}\"", root, null);
                var target = Path.Combine(root, "dotnet", file);
                var text = File.ReadAllText(target);
                Assert.Contains(oldText, text, StringComparison.Ordinal);
                File.WriteAllText(target, text.Replace(oldText, newText, StringComparison.Ordinal));

                var env = new Dictionary<string, string> { ["TCC_FUZZ_N"] = "2000", ["TCC_RUN_MUTATION_TESTS"] = "0" };
                var (exit, log) = Run("dotnet", "test tests\\TaxCredit.Parity.Tests --filter \"FullyQualifiedName~GoldenEngineTests|FullyQualifiedName~DifferentialFuzz|FullyQualifiedName~Sum_matches_python|FullyQualifiedName~ProximityParityTests|FullyQualifiedName~ClaimsParityTests|FullyQualifiedName~CoverageParityTests|FullyQualifiedName~PerformanceParityTests|FullyQualifiedName~ModelsParityTests|FullyQualifiedName~RunsParityTests|FullyQualifiedName~DraftsParityTests|FullyQualifiedName~CreditMathParityTests|FullyQualifiedName~PackValidationParityTests\"", Path.Combine(root, "dotnet"), env);
                var failedLines = log.Split('\n').Count(l => l.Contains("diverged", StringComparison.Ordinal) || l.Contains("mismatches", StringComparison.Ordinal));
                output.WriteLine($"{name}: exit={exit}, {failedLines} failure summaries");
                (exit != 0 && failedLines > 0 ? caught : missed).Add(name);
            }
            finally
            {
                Run("cmd.exe", $"/c rmdir \"{Path.Combine(root, "backend")}\"", root, null);
                if (Directory.Exists(root))
                {
                    Directory.Delete(root, true);
                }
            }
        }

        Assert.True(missed.Count == 0, "mutations NOT caught: " + string.Join("; ", missed));
        output.WriteLine("caught: " + string.Join("; ", caught));
    }

    private static void Copy(string from, string to)
    {
        Directory.CreateDirectory(to);
        foreach (var dir in Directory.EnumerateDirectories(from))
        {
            var leaf = Path.GetFileName(dir);
            if (leaf is "artifacts" or "bin" or "obj" or "regressions")
            {
                continue;
            }

            Copy(dir, Path.Combine(to, leaf));
        }

        foreach (var file in Directory.EnumerateFiles(from))
        {
            File.Copy(file, Path.Combine(to, Path.GetFileName(file)), true);
        }
    }

    private static (int Exit, string Log) Run(string exe, string args, string cwd, Dictionary<string, string>? env)
    {
        var info = new ProcessStartInfo(exe, args) { WorkingDirectory = cwd, RedirectStandardOutput = true, RedirectStandardError = true, UseShellExecute = false };
        if (env is not null)
        {
            foreach (var kv in env)
            {
                info.Environment[kv.Key] = kv.Value;
            }
        }

        using var p = Process.Start(info)!;
        var stdout = p.StandardOutput.ReadToEndAsync();
        var stderr = p.StandardError.ReadToEndAsync();
        p.WaitForExit();
        return (p.ExitCode, stdout.Result + stderr.Result);
    }
}
