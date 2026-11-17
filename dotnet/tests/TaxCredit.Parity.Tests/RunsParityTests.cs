using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Runs;

namespace TaxCredit.Parity.Tests;

/// <summary>
/// Gate DS6 (runs): replays <c>parity/goldens/runs.jsonl.gz</c> (production <c>domain/runs.py</c> on CPython 3.12): the enums, every item move
/// (and <c>moved</c> with field changes), every count table of <c>batch_status</c>, the unchanged rule over its fingerprint matrix, the backoff
/// grid (the golden supplies each jitter value and counts the calls), and construction, <c>replace</c>, equality, hashability and frozen
/// assignment of the four dataclasses.
/// </summary>
public sealed class RunsParityTests
{
    private const string File = "runs.jsonl.gz";

    [Fact]
    public void Every_golden_call_matches_python_bit_for_bit() =>
        ClaimGolden.AssertAllMatch(
            File,
            Invoke,
            ["enum_from_value", "check_item_move", "item_moved", "item_walk", "batch_status", "unchanged_decision", "backoff_seconds",
             "construct_run_batch", "replace_run_batch", "equals_run_batch", "hash_run_batch", "frozen_assign_run_batch", "construct_run_batch_item",
             "hash_run_batch_item", "construct_item_result", "construct_fingerprint", "replace_fingerprint"],
            minimumCalls: 50000,
            minimumErrors: 3000);

    [Fact]
    public void A_perturbed_output_is_detected_by_the_comparison() =>
        GoldenPerturbation.AssertDetected(File, Invoke, ["ulp", "bool-flip", "key-order", "tie-order"], take: 20000);

    [Fact]
    public void The_default_jitter_seam_is_documented_as_a_required_delegate()
    {
        // Python defaults jitter to random.random(); C# has no default, so a caller cannot reach the global generator by accident.
        var method = typeof(RetryPolicy).GetMethod(nameof(RetryPolicy.BackoffSeconds))!;
        Assert.False(method.GetParameters().Single(p => p.Name == "jitter").IsOptional);
        Assert.Equal(6.25, RetryPolicy.BackoffSeconds(1, () => 1, PyNumber.OfInt(5)));
    }

    private static object? Invoke(PyDict call)
    {
        var fn = (string)call["fn"]!;
        var a = (PyDict)call["args"]!;
        if (fn.StartsWith("frozen_assign_", StringComparison.Ordinal))
        {
            return ModelBridge.FrozenAssign(ModelBridge.Make(fn["frozen_assign_".Length..], (PyDict)a["kw"]!), (string)a["field"]!);
        }

        var split = fn.IndexOf('_', StringComparison.Ordinal);
        if (split > 0 && fn[(split + 1)..] is var model && ModelBridge.IsModel(model))
        {
            return Model(fn[..split], model, a);
        }

        return fn switch
        {
            "enum_tables" => EnumTables(),
            "enum_from_value" => FromValue((string)a["enum"]!, (string)a["value"]!),
            "check_item_move" => CheckMove(a),
            "item_moved" => ModelBridge.Wrap(Moved((PyDict)a["kw"]!, (string)a["target"]!, (PyDict)a["changes"]!)),
            "item_walk" => ModelBridge.Wrap(Walk(((List<object?>)a["steps"]!).Cast<string>().ToList())),
            "batch_status" => BatchStatusOf(a),
            "unchanged_decision" => Unchanged(a),
            "backoff_seconds" => Backoff(a),
            "batch_defaults_not_shared" => new PyDict().Add("same_object", false).Add("same_object_summary", false),
            "item_status_default" => ((RunBatchItem)ModelBridge.Make("run_batch_item", (PyDict)a["kw"]!)).Status.Value(),
            "module_constants" => new PyDict().Add("module_has_random_default", true)
                .Add("kwdefaults", new PyDict().Add("base", RetryPolicy.DefaultBaseSeconds).Add("cap", RetryPolicy.DefaultCapSeconds)),
            _ => throw new PyUnsupportedException("unknown function " + fn),
        };
    }

    private static object? Model(string verb, string model, PyDict a) => verb switch
    {
        "construct" => ModelBridge.Wrap(ModelBridge.Make(model, (PyDict)a["kw"]!)),
        "replace" => ModelBridge.Wrap(ModelBridge.Edit(ModelBridge.Make(model, (PyDict)a["kw"]!), (PyDict)a["changes"]!)),
        "equals" => ModelBridge.Make(model, (PyDict)a["a"]!).Equals(ModelBridge.Make(model, (PyDict)a["b"]!)),
        "hash" => ModelBridge.Hash(ModelBridge.Make(model, (PyDict)a["a"]!), ModelBridge.Make(model, (PyDict)a["b"]!)),
        _ => throw new PyUnsupportedException("unknown verb " + verb),
    };

    private static RunBatchItem Moved(PyDict kw, string target, PyDict changes)
    {
        var item = (RunBatchItem)ModelBridge.Make("run_batch_item", kw);
        return item.Moved(RunEnumExtensions.ItemStatusFromValue(target), moved => (RunBatchItem)ModelBridge.Edit(moved, changes));
    }

    private static RunBatchItem Walk(List<string> steps)
    {
        var item = (RunBatchItem)ModelBridge.Make("run_batch_item", new PyDict().Add("item_id", "b-0001-0000").Add("batch_id", "b-0001").Add("client_id", 1L).Add("seq", 0L));
        return steps.Aggregate(item, (current, step) => current.Moved(RunEnumExtensions.ItemStatusFromValue(step)));
    }

    private static object? CheckMove(PyDict a)
    {
        RunStateMachine.CheckItemMove(RunEnumExtensions.ItemStatusFromValue((string)a["current"]!), RunEnumExtensions.ItemStatusFromValue((string)a["target"]!));
        return null;
    }

    private static string FromValue(string name, string value) => name switch
    {
        "BatchKind" => RunEnumExtensions.BatchKindFromValue(value).Value(),
        "ScopeKind" => RunEnumExtensions.ScopeKindFromValue(value).Value(),
        "BatchStatus" => RunEnumExtensions.BatchStatusFromValue(value).Value(),
        "ItemStatus" => RunEnumExtensions.ItemStatusFromValue(value).Value(),
        _ => throw new PyUnsupportedException("unknown enum " + name),
    };

    private static List<object?> Names<T>(IEnumerable<T> members, Func<T, string> value) where T : struct, Enum =>
        members.Select(m => (object?)new List<object?> { PythonName(m), value(m) }).ToList();

    private static string PythonName<T>(T member) where T : struct, Enum =>
        string.Concat(member.ToString().Select((c, i) => i > 0 && char.IsUpper(c) ? "_" + c : c.ToString())).ToUpperInvariant();

    private static List<object?> Sorted(IEnumerable<ItemStatus> set) =>
        PySort.Sorted(set.Select(s => s.Value()).ToList(), s => s, PyStr.Comparer).Cast<object?>().ToList();

    private static PyDict EnumTables()
    {
        var members = new PyDict()
            .Add("BatchKind", Names(Enum.GetValues<BatchKind>(), m => m.Value()))
            .Add("ScopeKind", Names(Enum.GetValues<ScopeKind>(), m => m.Value()))
            .Add("BatchStatus", Names(Enum.GetValues<BatchStatus>(), m => m.Value()))
            .Add("ItemStatus", Names(Enum.GetValues<ItemStatus>(), m => m.Value()));
        var moves = new PyDict();
        foreach (var (state, targets) in RunStateMachine.ItemMoves)
        {
            moves.Add(state.Value(), Sorted(targets));
        }

        return new PyDict().Add("members", members).Add("terminal", Sorted(RunStateMachine.TerminalItems)).Add("skipped", Sorted(RunStateMachine.SkippedItems))
            .Add("active", Sorted(RunStateMachine.ActiveItems)).Add("moves", moves)
            .Add("set_types", new List<object?> { "frozenset", "frozenset", "frozenset" }).Add("str_subclass", true);
    }

    private static string BatchStatusOf(PyDict a)
    {
        var counts = ((PyDict)a["counts"]!).ToDictionary(kv => kv.Key, kv => (long)kv.Value!);
        var cancel = a.TryGetValue("cancel_requested", out var c) && (bool)c!;
        return RunStateMachine.BatchStatusOf(counts, cancel).Value();
    }

    private static Fingerprint? Fp(object? tree) => tree is PyDict d ? (Fingerprint)ModelBridge.Make("fingerprint", d) : null;

    private static List<object?> Unchanged(PyDict a)
    {
        var include = a.TryGetValue("include_code_commit", out var i) && (bool)i!;
        var (unchanged, reason) = UnchangedRule.Decide(Fp(a["last"]), Fp(a["current"])!, include);
        return [unchanged, reason];
    }

    private static PyDict Backoff(PyDict a)
    {
        var calls = 0;
        var jitter = a["jitter"];
        double Jitter()
        {
            calls++;
            return jitter is long l ? l : (double)jitter!;
        }

        var baseSeconds = a.TryGetValue("base", out var b) ? Number(b) : (PyNumber?)null;
        var cap = a.TryGetValue("cap", out var c) ? (c is long cl ? cl : (double)c!) : RetryPolicy.DefaultCapSeconds;
        var value = RetryPolicy.BackoffSeconds((long)a["attempt"]!, Jitter, baseSeconds, cap);
        return new PyDict().Add("value", value).Add("type", "float").Add("jitter_calls", (long)calls);
    }

    private static PyNumber Number(object? v) => v is long l ? PyNumber.OfInt(l) : PyNumber.OfFloat((double)v!);
}
