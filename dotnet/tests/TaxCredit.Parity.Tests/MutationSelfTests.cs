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
        ("gold rounding: a decimal cell rounds half up instead of half even", @"src\TaxCredit.Domain\Gold\GoldValues.cs", "PyRoundingMode.HalfEven", "PyRoundingMode.HalfUp"),
        ("gold rounding: the per-job rate is quantized to two places, not four", @"src\TaxCredit.Domain\Gold\GoldProjection.Credit.cs", "GoldValues.Truthy(rate) ? rate : trend.PerJobUsd, 4)", "GoldValues.Truthy(rate) ? rate : trend.PerJobUsd, 2)"),
        ("gold rounding: the clock keeps its microseconds", @"src\TaxCredit.Domain\Gold\GoldProjection.Summaries.cs", "clock() with { OffsetMinutes = null, Microsecond = 0 }", "clock() with { OffsetMinutes = null }"),
        ("gold comparison: year complete needs strictly more months than reachable", @"src\TaxCredit.Domain\Gold\GoldProjection.Credit.cs", "long l => l >= reachable,", "long l => l > reachable,"),
        ("gold comparison: a negative float is falsy", @"src\TaxCredit.Domain\Gold\GoldValues.cs", "double d => d != 0.0,", "double d => d > 0.0,"),
        ("gold comparison: an employee with no average row reads eligible", @"src\TaxCredit.Domain\Gold\GoldProjection.cs", "var eligible = average is null ? Int(0) :", "var eligible = average is null ? Int(1) :"),
        ("gold comparison: a falsy first span falls back only when absent", @"src\TaxCredit.Domain\Gold\GoldProjection.cs", "GoldValues.Truthy(firstSource) ? firstSource : Get(row, \"Pay_Period_Start\")", "firstSource is not null ? firstSource : Get(row, \"Pay_Period_Start\")"),
        ("gold ordering: the first average row of an employee wins, not the last", @"src\TaxCredit.Domain\Gold\GoldProjection.cs", "byEmployee[GoldValues.Str(row[\"Employee_ID\"])] = row;", "byEmployee.TryAdd(GoldValues.Str(row[\"Employee_ID\"]), row);"),
        ("gold ordering: the month ends are joined without a space", @"src\TaxCredit.Domain\Gold\GoldProjection.Summaries.cs", "text.Append(i == 0 ? string.Empty : \", \")", "text.Append(i == 0 ? string.Empty : \",\")"),
        ("gold ordering: the record token seed puts the year before the programme", @"src\TaxCredit.Domain\Gold\RecordTokens.cs", "$\"{account}\\0{programCode}\\0{GoldValues.Str(taxYear)}\\0{employeeId}\"", "$\"{account}\\0{GoldValues.Str(taxYear)}\\0{programCode}\\0{employeeId}\""),
        ("gold ordering: the payroll digest reads wages before hours", @"src\TaxCredit.Domain\Gold\GoldProjection.Identity.cs", "\"Hours_Worked\", \"Gross_Wages\", \"Pay_Code\",", "\"Gross_Wages\", \"Hours_Worked\", \"Pay_Code\","),
        ("gold column order: the period fact lists the title before the FEIN", @"src\TaxCredit.Domain\Gold\GoldRow.cs", "\"worksite_id\", \"entity_fein\", \"job_title\", \"pay_period_start\",", "\"worksite_id\", \"job_title\", \"entity_fein\", \"pay_period_start\","),
        ("gold column order: the month summary lists the average before the total", @"src\TaxCredit.Domain\Gold\GoldRow.cs", "\"total\", \"average_headcount\", \"months_with_headcount\"", "\"average_headcount\", \"total\", \"months_with_headcount\""),
        ("base-year rounding: the annual credit truncates instead of rounding half to even", @"src\TaxCredit.Domain\BaseYear\BaseYearEngine.cs", "var annualCredit = PyRound.RoundToInteger(eligibleJobs * yearRate);", "var annualCredit = double.IsFinite(eligibleJobs * yearRate) ? new System.Numerics.BigInteger(Math.Truncate(eligibleJobs * yearRate)) : PyRound.RoundToInteger(eligibleJobs * yearRate);"),
        ("base-year rounding: installment jobs round half away from zero", @"src\TaxCredit.Domain\BaseYear\BaseYearEngine.cs", "PyRound.Round(jobsMaintained, 2)", "Math.Round(jobsMaintained, 2, MidpointRounding.AwayFromZero)"),
        ("base-year rounding: a unit's month totals round half away from zero", @"src\TaxCredit.Domain\Trend\UnitTrendTools.cs", "var totals = months.Select(v => PyRound.Round(v, 2)).ToList();", "var totals = months.Select(v => Math.Round(v, 2, MidpointRounding.AwayFromZero)).ToList();"),
        ("base-year comparison: net new equal to the threshold no longer qualifies", @"src\TaxCredit.Domain\BaseYear\BaseYearEngine.cs", "netNew >= yearThreshold && netNew > 0", "netNew > yearThreshold && netNew > 0"),
        ("base-year comparison: every qualifying year counts as a backfill", @"src\TaxCredit.Domain\BaseYear\BaseYearEngine.cs", "qualified && !prevQualified", "qualified"),
        ("base-year comparison: a year with exactly the reachable months is not complete", @"src\TaxCredit.Domain\Trend\UnitTrendTools.cs", "if (months >= reachable)", "if (months > reachable)"),
        ("base-year comparison: a complete year before the base reads partial", @"src\TaxCredit.Domain\Trend\UnitTrendTools.cs", "taxYear < baseYear && monthsWithHeadcount >= monthsReachable", "taxYear < baseYear && monthsWithHeadcount > monthsReachable"),
        ("base-year comparison: the designation base year is chosen strictly before the base", @"src\TaxCredit.Domain\Designations\DesignationRegistry.Splits.cs", "history.FirstOrDefault(h => YearOf(h) <= baseYear)", "history.FirstOrDefault(h => YearOf(h) < baseYear)"),
        ("base-year comparison: a tolerance equal to the difference is a mismatch", @"src\TaxCredit.Domain\Pilot\BenchmarkReconciliation.cs", "PyNum.LessOrEqual(Math.Abs(diff), tol)", "Math.Abs(diff) < PyNum.ToDouble(tol)"),
        ("base-year comparison: the projected flag ignores the base year", @"src\TaxCredit.Domain\Trend\UnitTrendTools.Columns.cs", "!withPayroll.Contains(year) && year != result.BaseYear", "!withPayroll.Contains(year)"),
        ("base-year comparison: a worksite override no longer beats the state-wide one", @"src\TaxCredit.Domain\Designations\NegotiatedOverrides.cs", "!string.IsNullOrEmpty(worksite) && _overrides", "string.IsNullOrEmpty(worksite) && _overrides"),
        ("base-year ordering: the years are evaluated newest first", @"src\TaxCredit.Domain\BaseYear\BaseYearEngine.cs", "yearlyAvg.Keys.Where(y => y > baseYear).Order().ToList()", "yearlyAvg.Keys.Where(y => y > baseYear).OrderDescending().ToList()"),
        ("base-year ordering: units are sorted in reverse", @"src\TaxCredit.Domain\Trend\UnitTrendTools.cs", "PySort.Sorted(units, u => (string)u[\"unit_id\"]!, PyStr.Comparer);", "PySort.Sorted(units, u => (string)u[\"unit_id\"]!, PyStr.Comparer, reverse: true);"),
        ("base-year ordering: reconcile keys sort in UTF-16 order, not by code point", @"src\TaxCredit.Domain\Pilot\BenchmarkReconciliation.cs", "PySort.Sorted(keys, s => s, PyStr.Comparer)", "PySort.Sorted(keys, s => s, StringComparer.Ordinal)"),
        ("base-year benefit: every year is priced at the last year's rate", @"src\TaxCredit.Domain\BaseYear\BaseYearEngine.cs", "var yearRate = For(settings, y, e => e.PerJobUsd, settings.PerJobUsd);", "var yearRate = For(settings, evalYears[^1], e => e.PerJobUsd, settings.PerJobUsd);"),
        ("base-year benefit: a tranche is repriced at the last year's rate instead of holding the opening year's", @"src\TaxCredit.Domain\BaseYear\BaseYearEngine.cs", "BuildTrancheEvent(y, newJobsCreated, yearRate,", "BuildTrancheEvent(y, newJobsCreated, For(settings, evalYears[^1], e => e.PerJobUsd, settings.PerJobUsd),"),
        ("base-year benefit: a year absent from the map inherits the previous year's statute", @"src\TaxCredit.Domain\BaseYear\BaseYearEngine.cs", "map.TryGetValue(year, out var e) ? key(e) : null;", "(map.TryGetValue(year, out var e) || map.TryGetValue(year - 1, out e)) ? key(e) : null;"),
        ("base-year benefit: the benefit period defaults to four years", @"src\TaxCredit.Domain\Trend\UnitTrendQueryHelpers.cs", "ProximityCoerce.ToInt(v) : 5L", "ProximityCoerce.ToInt(v) : 4L"),
        ("forecast rounding: the YTD average rounds half away from zero", @"src\TaxCredit.Domain\Forecast\ForecastProjection.cs", "return PyRound.Round(total / monthsElapsed, 2);", "return Math.Round(total / monthsElapsed, 2, MidpointRounding.AwayFromZero);"),
        ("forecast comparison: a month closes only strictly before the as-of date", @"src\TaxCredit.Domain\Forecast\ForecastProjection.cs", "Count(me => me <= asOf)", "Count(me => me < asOf)"),
        ("forecast denominator: months elapsed counted from 1 January, not the fiscal window", @"src\TaxCredit.Domain\Forecast\ForecastProjection.cs", "OneZeroCalendar.TwelveMonthEnds(analysisStart).Count", "OneZeroCalendar.TwelveMonthEnds(new DateOnly(analysisStart.Year, 1, 1)).Count"),
        ("forecast clamp: months elapsed no longer floors at one", @"src\TaxCredit.Domain\Forecast\ForecastProjection.cs", "Math.Max(1, Math.Min(elapsed, 12))", "Math.Min(elapsed, 12)"),
        ("forecast sum: month totals use a naive sum instead of Python's compensated sum", @"src\TaxCredit.Domain\Forecast\ForecastProjection.cs", "total += ProximityCoerce.ToFloat(PySum.Sum(slice));", "total += slice.Sum(x => ProximityCoerce.ToFloat(x));"),
        ("forecast comparison: on track drops the 1e-9 tolerance and needs strictly more than the finish line", @"src\TaxCredit.Domain\Forecast\ForecastProjection.cs", "avg.Projected + 1e-9 >= finishLine", "avg.Projected > finishLine"),
        ("forecast filter: the prior year's rows are not narrowed to the state", @"src\TaxCredit.Domain\Forecast\ForecastProjection.cs", "(r.RequireWorksiteId() ?? \"None\").StartsWith(prefix, StringComparison.Ordinal)", "true"),
        ("forecast clamp: the gap to the finish line is no longer clamped at zero", @"src\TaxCredit.Domain\Forecast\ForecastProjection.cs", "PyRound.Round(PyArith.Max(0.0, finishLine - avg.Projected), 2)", "PyRound.Round(finishLine - avg.Projected, 2)"),
        ("simulation clamp: the projected headcount is no longer clamped at zero", @"src\TaxCredit.Domain\Simulation\WhatIfSimulator.cs", "var projectedAvg = PyRound.Round(PyArith.Max(0.0, baselineAvg + newHires), 2);", "var projectedAvg = PyRound.Round(baselineAvg + newHires, 2);"),
        ("simulation location: the key is lower-cased with the BCL, not Python's full mapping", @"src\TaxCredit.Domain\Simulation\LocationResolver.cs", "var key = PyStrCase.Lower(PyStr.Strip(cityOrState ?? string.Empty));", "var key = PyStr.Strip(cityOrState ?? string.Empty).ToLowerInvariant();"),
        ("simulation lookup: the state registry is consulted case-sensitively", @"src\TaxCredit.Domain\Simulation\StateCreditCalculator.cs", "if (!library.StateToPack.TryGet(stateU, out _))", "if (!library.StateToPack.TryGet(state, out _))"),
        ("simulation comparison: a part-time head is any weight up to and including one", @"src\TaxCredit.Domain\Simulation\OneZeroSimulation.cs", "(e.Weight ?? 1.0) < 1.0", "(e.Weight ?? 1.0) <= 1.0"),
        ("simulation comparison: a role at exactly the hours floor is below it", @"src\TaxCredit.Domain\Simulation\OneZeroSimulation.cs", "wh < minHours", "wh <= minHours"),
        ("simulation lever: the wage factor adds the percent instead of a hundredth of it", @"src\TaxCredit.Domain\Simulation\OneZeroLever.cs", "1.0 + (magnitude / 100.0)", "1.0 + magnitude"),
        ("simulation lever: a new head is cloned five hours under the floor-plus-five rule", @"src\TaxCredit.Domain\Simulation\OneZeroLever.cs", "ProximityCoerce.ToFloat(q.Pack.MinWeeklyHours) + 5.0", "ProximityCoerce.ToFloat(q.Pack.MinWeeklyHours) + 4.0"),
        ("simulation lever: the template is the lowest-hours employee", @"src\TaxCredit.Domain\Simulation\OneZeroLever.cs", "PySort.MaxBy(hoursByEmployee.ToList()", "PySort.MinBy(hoursByEmployee.ToList()"),
        ("simulation ordering: equal-hours employees are removed from the end, not the start", @"src\TaxCredit.Domain\Simulation\OneZeroLever.cs", "PySort.Sorted(totals, kv => kv.Value", "PySort.Sorted(totals.Reverse(), kv => kv.Value"),
        ("simulation slice: a negative removal count keeps nothing instead of counting from the end", @"src\TaxCredit.Domain\Simulation\RowOps.cs", "var end = k < 0 ? length + k : k;", "var end = k < 0 ? 0 : k;"),
        ("ingestion comparison: a 14-day period is no longer biweekly", @"src\TaxCredit.Domain\Canonical\CanonicalMapper.cs", "span <= 14 ?", "span < 14 ?"),
        ("ingestion comparison: the cash-basis trim keeps a later pay year", @"src\TaxCredit.Domain\Canonical\CanonicalMapper.cs", "payDate.Year != taxYear", "payDate.Year < taxYear"),
        ("ingestion rounding: collapsed hours round half away from zero", @"src\TaxCredit.Domain\Canonical\CanonicalMapper.cs", "PyRound.Round(b.Hours + rec.HoursWorked, 2)", "Math.Round(b.Hours + rec.HoursWorked, 2, MidpointRounding.AwayFromZero)"),
        ("ingestion ordering: collapse buckets by pay period start, not end", @"src\TaxCredit.Domain\Canonical\CanonicalMapper.cs", "var key = (rec.EmployeeId, rec.WorksiteId, Iso(rec.PayPeriodEnd));", "var key = (rec.EmployeeId, rec.WorksiteId, Iso(rec.PayPeriodStart));"),
        ("ingestion hash-input: the date cell is read past its first ten characters", @"src\TaxCredit.Domain\Canonical\CanonicalMapper.cs", "PyStr.Prefix(ProximityCoerce.Str(v), 10)", "PyStr.Prefix(ProximityCoerce.Str(v), 16)"),
        ("ingestion comparison: a missing hours cell is an error, not zero", @"src\TaxCredit.Domain\Canonical\CanonicalMapper.cs", "ProximityCoerce.FloatOrZero(r, \"Hours_Worked\")", "ProximityCoerce.ToFloat(r[\"Hours_Worked\"])"),
        ("ingestion comparison: a placeholder address keeps its edge commas", @"src\TaxCredit.Domain\Canonical\CanonicalMapper.cs", ".Trim(',', ' ')", ".Trim(' ')"),
        ("ingestion comparison: the pay-code lookup trims the code", @"src\TaxCredit.Domain\Canonical\PayCodeClassifier.cs", "if (Excluded.Contains(payCode))", "if (Excluded.Contains(payCode.Trim()))"),
        ("ingestion comparison: the default exclusions forget relocation", @"src\TaxCredit.Domain\Canonical\PayCodeClassifier.cs", "[\"Mileage\", \"Expense_Reimbursement\", \"Relocation\"]", "[\"Mileage\", \"Expense_Reimbursement\"]"),
        ("ingestion comparison: the csv quote character is an apostrophe", @"src\TaxCredit.Infrastructure\Payroll\PayPeriodCsvAdapter.cs", "case State.StartField when c == '\"':", "case State.StartField when c == '\\'':"),
        ("ingestion ordering: an inverted range keeps its bounds", @"src\TaxCredit.Domain\Filters\GridFilter.cs", "[PyArith.Min(a.Value, b.Value), PyArith.Max(a.Value, b.Value)]", "[a.Value, b.Value]"),
        ("ingestion comparison: like wildcards are no longer bracketed", @"src\TaxCredit.Domain\Filters\GridFilter.cs", ".Replace(\"%\", \"[%]\", StringComparison.Ordinal)", ".Replace(\"%\", \"\\\\%\", StringComparison.Ordinal)"),
        ("ingestion comparison: the needle is lowered with the invariant culture, not Python's full mapping", @"src\TaxCredit.Domain\Filters\GridFilter.cs", "PyStrCase.Lower(escaped)", "escaped.ToLowerInvariant()"),
        ("ingestion comparison: a bare number reads as an equality", @"src\TaxCredit.Domain\Filters\GridFilter.cs", "is { } bare ? ($\"{column} >= ?\"", "is { } bare ? ($\"{column} = ?\""),
        ("ingestion comparison: an empty enum member is kept", @"src\TaxCredit.Domain\Filters\GridFilter.cs", ".Where(p => p.Length > 0)", ".Where(p => true)"),
        ("ingestion ordering: the shorter comparator wins over the longer", @"src\TaxCredit.Domain\Filters\GridFilter.cs", "[\">=\", \"<=\", \">\", \"<\", \"=\"]", "[\">\", \"<\", \">=\", \"<=\", \"=\"]"),
        ("ingestion comparison: the column name is not stripped", @"src\TaxCredit.Domain\Filters\GridFilter.cs", "var name = PyStr.Strip(term[..colon]);", "var name = term[..colon];"),
        ("ingestion hash-input: the line key keeps nineteen hex digits", @"src\TaxCredit.Domain\Qc\PayLineKeys.cs", "SHA256.HashData(Encoding.UTF8.GetBytes(LineContent(row))))[..20]", "SHA256.HashData(Encoding.UTF8.GetBytes(LineContent(row))))[..19]"),
        ("ingestion hash-input: line content formats hours with three places", @"src\TaxCredit.Domain\Qc\PayLineKeys.cs", "ProximityCoerce.ToFloat(value) : 0.0, 4)", "ProximityCoerce.ToFloat(value) : 0.0, 3)"),
        ("ingestion comparison: a scraggly line needs only one low value", @"src\TaxCredit.Domain\Qc\QcDetector.cs", "DefaultMinWages) && PyNumCompare.Below(hours", "DefaultMinWages) || PyNumCompare.Below(hours"),
        ("ingestion comparison: a test of twos fires for a single unit", @"src\TaxCredit.Domain\Qc\QcDetector.cs", "kv.Value.Count > 1", "kv.Value.Count >= 1"),
        ("ingestion ordering: test of twos sorted by UTF-16 code unit", @"src\TaxCredit.Domain\Qc\QcDetector.cs", "var c = PyStr.Compare(x.Emp, y.Emp);", "var c = string.CompareOrdinal(x.Emp, y.Emp);"),
        ("ingestion hash-input: the month key is not zero padded", @"src\TaxCredit.Domain\Qc\QcDetector.cs", "d.Month.ToString(\"00\"", "d.Month.ToString(\"0\""),
        ("ingestion rounding: scraggly wages round half away from zero", @"src\TaxCredit.Domain\Qc\QcDetector.cs", ".Add(\"wages\", PyRound.Round(wages, 2))", ".Add(\"wages\", Math.Round(wages, 2, MidpointRounding.AwayFromZero))"),
        ("ingestion comparison: the state prefix is matched as typed", @"src\TaxCredit.Domain\Qc\QcDetector.cs", "var prefix = PyStr.Upper(state) + \"_\";", "var prefix = state + \"_\";"),
        ("ingestion comparison: an empty report asks for validation", @"src\TaxCredit.Domain\Qc\QcDetector.cs", ".Add(\"requires_human_validation\", total > 0)", ".Add(\"requires_human_validation\", total >= 0)"),
        ("ingestion comparison: the trail counts every row, not the scoped ones", @"src\TaxCredit.Domain\Qc\QcDetector.cs", "(long)Filter(rows, taxYear, state).Count", "(long)rows.Count"),
        ("ingestion comparison: a spike of ten is no longer high", @"src\TaxCredit.Domain\Triggers\TriggerDetector.cs", "delta >= 10 ? \"high\"", "delta > 10 ? \"high\""),
        ("ingestion comparison: a threshold met exactly no longer fires", @"src\TaxCredit.Domain\Triggers\PyNumCompare.cs", "Compare(f, n) is >= 0", "Compare(f, n) is > 0"),
        ("ingestion rounding: the wage rise is rounded to two places", @"src\TaxCredit.Domain\Triggers\TriggerDetector.cs", "PyRound.Round(pct, 3)", "PyRound.Round(pct, 2)"),
        ("ingestion rounding: the percentage keeps two places", @"src\TaxCredit.Domain\Triggers\TriggerDetector.cs", "PyFormat.Fixed(x * 100, 1)", "PyFormat.Fixed(x * 100, 2)"),
        ("ingestion ordering: new FEINs sorted by UTF-16 code unit", @"src\TaxCredit.Domain\Triggers\TriggerDetector.cs", "cells.OrderBy(c => (string)c!, PyStr.Comparer)", "cells.OrderBy(c => (string)c!, StringComparer.Ordinal)"),
        ("ingestion ordering: new jurisdictions sorted by UTF-16 code unit", @"src\TaxCredit.Domain\Triggers\TriggerDetector.cs", "States(currentRows).Where(s => !priorStates.Contains(s)).OrderBy(s => s, PyStr.Comparer)", "States(currentRows).Where(s => !priorStates.Contains(s)).OrderBy(s => s, StringComparer.Ordinal)"),
        ("ingestion comparison: a zero prior average is divided by", @"src\TaxCredit.Domain\Triggers\TriggerDetector.cs", "if (!(priorAvg > 0))", "if (!(priorAvg >= 0))"),
        ("ingestion equality: true and 1 are different employees", @"src\TaxCredit.Domain\Triggers\UnitAggregation.cs", "bool b => b ? 1L : 0L,", "bool b => b ? \"true\" : \"false\","),
        ("simulation format: fixed notation rounds a tie half up, not half to even", @"src\TaxCredit.Domain\Numerics\PyFormat.cs", "twice > d || (twice == d && !q.IsEven)", "twice >= d"),
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
        // TCC_MUTATION_TEST_FILTER=FullyQualifiedName~ForecastParityTests narrows the test run of each mutant to the named classes.
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
                var (exit, log) = Run("dotnet", "test tests\\TaxCredit.Parity.Tests --filter \"" + (Environment.GetEnvironmentVariable("TCC_MUTATION_TEST_FILTER") ?? "FullyQualifiedName~GoldenEngineTests|FullyQualifiedName~DifferentialFuzz|FullyQualifiedName~Sum_matches_python|FullyQualifiedName~ProximityParityTests|FullyQualifiedName~ClaimsParityTests|FullyQualifiedName~CoverageParityTests|FullyQualifiedName~PerformanceParityTests|FullyQualifiedName~ModelsParityTests|FullyQualifiedName~RunsParityTests|FullyQualifiedName~DraftsParityTests|FullyQualifiedName~CreditMathParityTests|FullyQualifiedName~PackValidationParityTests|FullyQualifiedName~GoldParityTests|FullyQualifiedName~BaseYearParityTests|FullyQualifiedName~ForecastParityTests|FullyQualifiedName~CanonicalParityTests|FullyQualifiedName~GridFilterParityTests|FullyQualifiedName~QcTriggersParityTests") + "\"", Path.Combine(root, "dotnet"), env);
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
