using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Programs;

namespace TaxCredit.Parity.Tests;

/// <summary>
/// Gate DS6 (drafts): replays <c>parity/goldens/drafts.jsonl.gz</c> (production <c>domain/program_drafts.py</c> on CPython 3.12): the status enum,
/// the <c>DraftError</c> hierarchy (type names, codes, inheritance), <c>CODE_PATTERN</c> against every ASCII character and the newline cases,
/// <c>canonical_json</c> and <c>documents_hash</c> (non-ASCII, non-BMP, lone surrogates, depth and size boundaries) and the two dataclasses.
/// </summary>
public sealed class DraftsParityTests
{
    private const string File = "drafts.jsonl.gz";

    // Python class name -> the C# type that `except <name>` corresponds to (the abstract base where the class was split, see DraftErrors.cs).
    private static readonly (string Name, Type Catches)[] PythonClasses =
    [
        ("DraftError", typeof(DraftError)), ("DraftNotFound", typeof(DraftNotFound)), ("DraftConflict", typeof(DraftConflict)), ("DraftInvalid", typeof(DraftInvalid)),
        ("InvalidTransition", typeof(InvalidTransition)), ("ReviewRefused", typeof(ReviewRefusal)), ("CustomerDataInDraft", typeof(CustomerDataInDraft)),
        ("PreviewRefused", typeof(PreviewRefusal)), ("CustomerDataRefused", typeof(CustomerDataRefused)),
    ];
    [Fact]
    public void Every_golden_call_matches_python_bit_for_bit() =>
        ClaimGolden.AssertAllMatch(
            File,
            Invoke,
            ["raise_error", "status_from_value", "code_pattern", "documents_hash", "canonical_json", "canonical_documents", "construct_program_draft",
             "replace_program_draft", "equals_program_draft", "hash_program_draft", "frozen_assign_program_draft", "construct_draft_event", "equals_draft_event",
             "content_sha256", "with_changes"],
            minimumCalls: 8000,
            minimumErrors: 400);

    [Fact]
    public void A_perturbed_output_is_detected_by_the_comparison() =>
        GoldenPerturbation.AssertDetected(File, Invoke, ["bool-flip", "key-order"], take: 6000);

    [Fact]
    public void The_python_trailing_newline_rule_of_the_code_pattern_holds_in_dotnet()
    {
        Assert.True(ProgramDraftRules.IsProgramCode("GA_JTC\n"));
        Assert.False(ProgramDraftRules.IsProgramCode("GA_JTC\n\n"));
        Assert.False(ProgramDraftRules.IsProgramCode("GA_JTC\r\n"));
        Assert.False(ProgramDraftRules.IsProgramCode("ga_jtc"));
    }

    private static object? Invoke(PyDict call)
    {
        var fn = (string)call["fn"]!;
        var a = (PyDict)call["args"]!;
        var split = fn.IndexOf('_', StringComparison.Ordinal);
        if (fn.StartsWith("frozen_assign_", StringComparison.Ordinal))
        {
            return ModelBridge.FrozenAssign(ModelBridge.Make(fn["frozen_assign_".Length..], (PyDict)a["kw"]!), (string)a["field"]!);
        }

        if (split > 0 && ModelBridge.IsModel(fn[(split + 1)..]))
        {
            return Model(fn[..split], fn[(split + 1)..], a);
        }

        return Other(fn, a);
    }

    private static object? Model(string verb, string model, PyDict a) => verb switch
    {
        "construct" => ModelBridge.Wrap(ModelBridge.Make(model, (PyDict)a["kw"]!)),
        "replace" => ModelBridge.Wrap(ModelBridge.Edit(ModelBridge.Make(model, (PyDict)a["kw"]!), (PyDict)a["changes"]!)),
        "equals" => ModelBridge.Make(model, (PyDict)a["a"]!).Equals(ModelBridge.Make(model, (PyDict)a["b"]!)),
        "hash" => ModelBridge.Hash(ModelBridge.Make(model, (PyDict)a["a"]!), ModelBridge.Make(model, (PyDict)a["b"]!)),
        _ => throw new PyUnsupportedException("unknown verb " + verb),
    };

    private static object? Other(string fn, PyDict a)
    {
        switch (fn)
        {
            case "error_info":
                return ErrorInfo();
            case "raise_error":
                throw Make((string)a["cls"]!, (string)a["message"]!);
            case "raise_error_empty":
                throw Make((string)a["cls"]!, string.Empty);
            case "error_code":
                return Make((string)a["cls"]!, " m").Code;
            case "error_is_a":
                return PythonClasses.SelectMany(x => PythonClasses.Select(y => (object?)new List<object?> { x.Name, y.Name, y.Catches.IsAssignableFrom(x.Catches) })).ToList();
            case "status_tables":
                return StatusTables();
            case "status_from_value":
                return DraftStatusExtensions.FromValue((string)a["value"]!).Value();
            case "status_flags":
                var s = DraftStatusExtensions.FromValue((string)a["status"]!);
                return new PyDict().Add("editable", DraftStatusExtensions.Editable.Contains(s)).Add("closed", DraftStatusExtensions.Closed.Contains(s));
            case "code_pattern_meta":
                return new PyDict().Add("pattern", ProgramDraftRules.CodePattern.ToString());
            case "code_pattern":
                return CodeMatch((string)a["text"]!);
            case "documents_hash":
                return ProgramDraftRules.DocumentsHash((PyDict?)a["pack"], (PyDict)a["years"]!);
            case "canonical_json":
                return ProgramDraftRules.CanonicalJson(a["document"]);
            case "canonical_documents":
                var text = ProgramDraftRules.CanonicalJson(new PyDict().Add("pack", a["pack"]).Add("years", a["years"]));
                return new PyDict().Add("text", text).Add("length", (long)PyStr.Length(text));
            case "content_sha256":
                return ((ProgramDraft)ModelBridge.Make("program_draft", (PyDict)a["kw"]!)).ContentSha256;
            case "with_changes":
                var draft = (ProgramDraft)ModelBridge.Make("program_draft", (PyDict)a["kw"]!);
                return ModelBridge.Wrap(draft.WithChanges(d => (ProgramDraft)ModelBridge.Edit(d, (PyDict)a["changes"]!)));
            case "defaults_not_shared":
                return new PyDict().Add("years", false).Add("detail", false);
            default:
                throw new PyUnsupportedException("unknown function " + fn);
        }
    }

    private static PyDict CodeMatch(string text)
    {
        var m = ProgramDraftRules.CodePattern.Match(text);
        return new PyDict().Add("matched", m.Success).Add("end", m.Success ? (long)(m.Index + m.Length) : null).Add("group", m.Success ? m.Value : null);
    }

    private static PyDict StatusTables()
    {
        var members = Enum.GetValues<DraftStatus>()
            .Select(s => (object?)new List<object?> { string.Concat(s.ToString().Select((c, i) => i > 0 && char.IsUpper(c) ? "_" + c : c.ToString())).ToUpperInvariant(), s.Value() })
            .ToList();
        List<object?> Sorted(IEnumerable<DraftStatus> set) => PySort.Sorted(set.Select(s => s.Value()).ToList(), s => s, PyStr.Comparer).Cast<object?>().ToList();
        return new PyDict().Add("members", members).Add("editable", Sorted(DraftStatusExtensions.Editable)).Add("closed", Sorted(DraftStatusExtensions.Closed))
            .Add("types", new List<object?> { "frozenset", "frozenset" })
            .Add("limits", new List<object?> { (long)ProgramDraftRules.MaxDocumentChars, (long)ProgramDraftRules.MaxYearDocuments, (long)ProgramDraftRules.MaxDocumentDepth });
    }

    // The bases are read off the real C# inheritance chain, so a subtype that stopped inheriting from its Python parent would fail here.
    private static PyDict ErrorInfo()
    {
        var info = new PyDict();
        foreach (var (name, _) in PythonClasses)
        {
            var instance = Make(name, "m");
            var bases = new List<object?>();
            for (var t = instance.GetType().BaseType; t is not null && t != typeof(PyException); t = t.BaseType)
            {
                var python = PythonClasses.First(c => c.Catches == t).Name;
                if (python != name && !bases.Contains(python))
                {
                    bases.Add(python);
                }
            }

            bases.Add("Exception");
            info.Add(name, new PyDict().Add("code", instance.Code).Add("bases", bases).Add("is_exception", true));
        }

        return info;
    }
    private static DraftError Make(string name, string message) => name switch
    {
        "DraftError" => new DraftRefused(message),
        "DraftNotFound" => new DraftNotFound(message),
        "DraftConflict" => new DraftConflict(message),
        "DraftInvalid" => new DraftInvalid(message),
        "InvalidTransition" => new InvalidTransition(message),
        "ReviewRefused" => new ReviewRefused(message),
        "CustomerDataInDraft" => new CustomerDataInDraft(message),
        "PreviewRefused" => new PreviewRefused(message),
        "CustomerDataRefused" => new CustomerDataRefused(message),
        _ => throw new PyUnsupportedException("unknown error " + name),
    };
}
