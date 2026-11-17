using System.Numerics;
using System.Reflection;
using System.Runtime.CompilerServices;
using TaxCredit.Domain.Calculation;
using TaxCredit.Domain.Findings;
using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Programs;
using TaxCredit.Domain.Warehouse;

namespace TaxCredit.Parity.Tests;

/// <summary>
/// Gate DS5 (data models): replays <c>parity/goldens/models.jsonl.gz</c> (production <c>domain/programs.py</c>, <c>domain/findings.py</c>,
/// <c>domain/warehouse.py</c> and <c>application/open_year.py</c> on CPython 3.12). Construction, validation messages, equality, hashability,
/// <c>dataclasses.replace</c>, the frozen-assignment error (a compile-time guarantee in C#: every property is init-only), the methods and the constants.
/// </summary>
public sealed class ModelsParityTests
{
    private const string File = "models.jsonl.gz";

    [Fact]
    public void Every_golden_call_matches_python_bit_for_bit() =>
        ClaimGolden.AssertAllMatch(
            File,
            Invoke,
            ["construct_run_manifest", "replace_run_manifest", "equals_run_manifest", "construct_manual_override", "construct_finding_resolution", "finding_to_dict",
             "equals_finding_resolution", "construct_program_entry", "program_entry_status", "is_open", "open_year_reading", "base_year_key", "frozen_assign_run_manifest"],
            minimumCalls: 9000,
            minimumErrors: 2500);

    [Fact]
    public void A_perturbed_output_is_detected_by_the_comparison() =>
        GoldenPerturbation.AssertDetected(File, Invoke, ["ulp", "bool-flip", "key-order"], take: 4000);

    [Fact]
    public void Python_hash_is_refused_only_for_a_finding_that_carries_a_detail_dict()
    {
        var plain = Finding(null);
        Assert.True(plain.HashableInPython);
        Assert.False(Finding(new PyDict().Add("k", 1L)).HashableInPython);
        Assert.Equal(plain.GetHashCode(), Finding(null).GetHashCode());
    }

    [Fact]
    public void Open_year_today_reads_the_local_calendar_date()
    {
        var before = DateOnly.FromDateTime(DateTime.Now);
        var today = OpenYear.Today();
        Assert.InRange(today.DayNumber, before.DayNumber, before.DayNumber + 1);
        Assert.True(OpenYear.IsOpen(today.AddDays(1)));
        Assert.False(OpenYear.IsOpen(today));
    }

    private static FindingResolution Finding(PyDict? detail) => new()
    {
        FindingId = "f",
        ClientId = 1,
        TaxYear = 2023,
        Resolution = "accept",
        DecidedBy = "d",
        DecidedAt = "t",
        Detail = detail,
    };

    private static object? Invoke(PyDict call)
    {
        var fn = (string)call["fn"]!;
        var a = (PyDict)call["args"]!;
        if (fn.StartsWith("construct_", StringComparison.Ordinal))
        {
            return Wrap(Fields(Make(fn["construct_".Length..], (PyDict)a["kw"]!)));
        }

        if (fn.StartsWith("replace_", StringComparison.Ordinal))
        {
            return Wrap(Fields(Replace(fn["replace_".Length..], (PyDict)a["kw"]!, (PyDict)a["changes"]!)));
        }

        if (fn.StartsWith("equals_", StringComparison.Ordinal))
        {
            var model = fn["equals_".Length..];
            return Make(model, (PyDict)a["a"]!).Equals(Make(model, (PyDict)a["b"]!));
        }

        if (fn.StartsWith("hash_", StringComparison.Ordinal))
        {
            return Hash(fn["hash_".Length..], (PyDict)a["a"]!, (PyDict)a["b"]!);
        }

        if (fn.StartsWith("frozen_assign_", StringComparison.Ordinal))
        {
            return FrozenAssign(fn["frozen_assign_".Length..], (PyDict)a["kw"]!, (string)a["field"]!);
        }

        return Other(fn, a);
    }

    private static object? Other(string fn, PyDict a)
    {
        switch (fn)
        {
            case "constants_programs":
                return new PyDict().Add("credit", Strings(ProgramVocabulary.SupportedCreditModels)).Add("headcount", Strings(ProgramVocabulary.SupportedHeadcountModels))
                    .Add("lifecycles", Strings(ProgramVocabulary.StoredLifecycles)).Add("levels", Strings(ProgramVocabulary.JurisdictionLevels));
            case "constants_warehouse":
                return new PyDict().Add("run_statuses", Strings(PySort.Sorted(WarehouseVocabulary.RunStatuses, s => s, PyStr.Comparer)))
                    .Add("columns", Strings(WarehouseVocabulary.RunManifestColumns))
                    .Add("override_scopes", Strings(PySort.Sorted(WarehouseVocabulary.OverrideScopes, s => s, PyStr.Comparer))).Add("run_statuses_type", "frozenset");
            case "constants_open_year":
                return new PyDict().Add("min_open_months", OpenYear.MinOpenMonths).Add("today_is_date", "date");
            case "registry_error":
                var message = (string)a["message"]!;
                return new PyDict().Add("str", new RegistryError(message).Message).Add("args", new List<object?> { message }).Add("is_value_error", true);
            case "program_entry_status":
                var years = a["authored_years"] as List<object?>;
                return Entry((PyDict)a["kw"]!).Status(years?.Select(y => (long)y!).ToList());
            case "finding_to_dict":
                return FindingOf((PyDict)a["kw"]!).ToDict();
            case "finding_detail_identity":
                var detail = (PyDict)a["detail"]!;
                return ReferenceEquals(Finding(detail).ToDict()["detail"], detail);
            case "base_year_key":
                return WarehouseVocabulary.BaseYearKey((string)a["program_code"]!, (string)a["worksite_id"]!);
            case "manifest_columns_vs_fields":
                var names = typeof(RunManifest).GetConstructors()[0].GetParameters().Select(p => Snake(p.Name!)).ToList();
                return new PyDict().Add("fields", Strings(names)).Add("columns", Strings(WarehouseVocabulary.RunManifestColumns))
                    .Add("same_set", names.Order(StringComparer.Ordinal).SequenceEqual(WarehouseVocabulary.RunManifestColumns.Order(StringComparer.Ordinal)));
            case "is_open":
                return IsOpen(a);
            case "open_year_reading":
                var trend = (PyDict)a["trend"]!;
                return OpenYear.Reading(a["average_headcount"], new OpenYearTrend(trend["base_average_headcount"], trend["final_high_water_mark"], trend["per_job_usd"]), (PyDict)a["statute"]!, a["threshold"]).ToDict();
            default:
                throw new PyUnsupportedException("unknown function " + fn);
        }
    }

    private static bool IsOpen(PyDict a)
    {
        var end = Decode(a["window_end"]);
        var on = a.TryGetValue("on", out var o) ? (DateOnly?)Decode(o) : null;
        Func<DateOnly>? today = a.TryGetValue("today", out var t) ? () => (DateOnly)Decode(t)! : null;
        return OpenYear.IsOpen(end, on, today);
    }

    private static List<object?> Strings(IEnumerable<string> items) => items.Cast<object?>().ToList();

    /// <summary>The exporter's tagged values: <c>{"$date": iso}</c> and <c>{"$dt": iso}</c> become C# values; anything else is returned unchanged.</summary>
    private static object? Decode(object? v) => v switch
    {
        PyDict { Count: 1 } d when d.ContainsKey("$date") => PyDate.FromIsoFormat((string)d["$date"]!),
        PyDict { Count: 1 } d when d.ContainsKey("$dt") => PyDateTime.FromIsoFormat((string)d["$dt"]!),
        _ => v,
    };

    private static object Make(string model, PyDict kw) => model switch
    {
        "engine_profile" => Profile(kw),
        "program_entry" => Entry(kw),
        "finding_resolution" => FindingOf(kw),
        "run_manifest" => Manifest(kw),
        "manual_override" => Override(kw),
        _ => throw new PyUnsupportedException("unknown model " + model),
    };

    private static EngineProfile Profile(PyDict kw)
    {
        var p = new EngineProfile();
        return p with
        {
            CreditModel = kw.TryGetValue("credit_model", out var c) ? (string)c! : p.CreditModel,
            HeadcountModel = kw.TryGetValue("headcount_model", out var h) ? (string)h! : p.HeadcountModel,
        };
    }

    private static ProgramEntry Entry(PyDict kw)
    {
        var e = new ProgramEntry
        {
            Code = (string)kw["code"]!,
            Name = (string)kw["name"]!,
            Level = (string)kw["level"]!,
            JurisdictionCode = (string)kw["jurisdiction_code"]!,
            PackFile = (string)kw["pack_file"]!,
            State = kw.TryGetValue("state", out var s) ? (string?)s : null,
        };
        return e with
        {
            Lifecycle = kw.TryGetValue("lifecycle", out var l) ? (string)l! : e.Lifecycle,
            EngineProfile = kw.TryGetValue("engine_profile", out var p) ? Profile((PyDict)p!) : e.EngineProfile,
            Notes = kw.TryGetValue("notes", out var n) ? (string)n! : e.Notes,
        };
    }

    private static FindingResolution FindingOf(PyDict kw) => new()
    {
        FindingId = (string)kw["finding_id"]!,
        ClientId = (long)kw["client_id"]!,
        TaxYear = (long)kw["tax_year"]!,
        Resolution = (string)kw["resolution"]!,
        DecidedBy = (string)kw["decided_by"]!,
        DecidedAt = (string)kw["decided_at"]!,
        Detail = kw.TryGetValue("detail", out var d) ? (PyDict?)d : null,
        Note = kw.TryGetValue("note", out var n) ? (string?)n : null,
        SupersededAt = kw.TryGetValue("superseded_at", out var s) ? (string?)s : null,
    };

    private static string? Str(PyDict kw, string key) => kw.TryGetValue(key, out var v) ? (string?)v : null;

    private static PyDateTime? Dt(PyDict kw, string key) => kw.TryGetValue(key, out var v) && v is not null ? (PyDateTime)Decode(v)! : null;

    private static RunManifest Manifest(PyDict kw) => new(
        (string)kw["run_id"]!, (long)kw["client_id"]!, (string)kw["program_code"]!, (long)kw["tax_year"]!,
        (DateOnly)Decode(kw["fiscal_year_begin"])!, (DateOnly)Decode(kw["fiscal_year_end"])!, (PyDateTime)Decode(kw["run_started_at"])!, (string)kw["run_status"]!,
        kw.TryGetValue("entity_id", out var e) ? (long?)e : null, Str(kw, "source_snapshot_id"), Str(kw, "step1_assumption_set_id"), Str(kw, "step1_assumption_sha256"),
        Str(kw, "onezero_assumption_set_id"), Str(kw, "onezero_assumption_sha256"), Str(kw, "rule_pack_version"), Str(kw, "code_commit"), Str(kw, "calculation_id"),
        Dt(kw, "run_completed_at"), Str(kw, "superseded_by_run_id"), Str(kw, "triggered_by"));

    private static ManualOverride Override(PyDict kw) => new(
        (string)kw["override_id"]!, (string)kw["run_id"]!, (long)kw["client_id"]!, (string)kw["scope"]!, (string)kw["target_key"]!, (string)kw["field_changed"]!,
        Str(kw, "value_before"), Str(kw, "value_after"), Str(kw, "reason_code"), Str(kw, "justification_text"), (string)kw["created_by"]!, (PyDateTime)Decode(kw["created_at"])!,
        Str(kw, "approved_by"), Dt(kw, "approved_at"));

    // dataclasses.replace: the clone is edited through its init-only setters (a record's copy), then validated where Python's __post_init__ would run.
    private static object Replace(string model, PyDict kw, PyDict changes)
    {
        var original = Make(model, kw);
        return original switch
        {
            RunManifest m => m.Replace(x => (RunManifest)Edit(x, changes)),
            ManualOverride m => m.Replace(x => (ManualOverride)Edit(x, changes)),
            _ => Edit(original, changes),
        };
    }

    private static object Edit(object model, PyDict changes)
    {
        var type = model.GetType();
        var clone = type.GetMethod("<Clone>$")!.Invoke(model, null)!;
        foreach (var (key, value) in changes)
        {
            var property = type.GetProperty(Pascal(key))!;
            var decoded = Decode(value);
            property.SetValue(clone, decoded is PyDict d && property.PropertyType == typeof(EngineProfile) ? Profile(d) : decoded);
        }

        return clone;
    }

    private static string Pascal(string snake) => string.Concat(snake.Split('_').Select(p => char.ToUpperInvariant(p[0]) + p[1..]));

    private static string Snake(string camel)
    {
        var sb = new System.Text.StringBuilder();
        foreach (var c in camel)
        {
            if (char.IsUpper(c) && sb.Length > 0)
            {
                sb.Append('_');
            }

            sb.Append(char.ToLowerInvariant(c));
        }

        return sb.ToString();
    }

    private static PyDict Hash(string model, PyDict a, PyDict b)
    {
        var left = Make(model, a);
        var right = Make(model, b);
        if (left is FindingResolution { HashableInPython: false })
        {
            throw new PyTypeError("unhashable type: 'dict'");
        }

        return new PyDict().Add("hashable", true).Add("equal_objects_equal_hash", !left.Equals(right) || left.GetHashCode() == right.GetHashCode());
    }

    // A frozen dataclass raises on assignment; in C# the same guarantee is that the property can only be set in an initializer.
    private static string FrozenAssign(string model, PyDict kw, string field)
    {
        var property = Make(model, kw).GetType().GetProperty(Pascal(field)) ?? throw new InvalidOperationException("no property for " + field);
        var initOnly = property.SetMethod!.ReturnParameter.GetRequiredCustomModifiers().Contains(typeof(IsExternalInit));
        return initOnly ? throw new FrozenAssignment("cannot assign to field '" + field + "'") : "assignable";
    }

    private sealed class FrozenAssignment(string message) : PyException("FrozenInstanceError", message);

    private static PyDict Fields(object model) => model switch
    {
        EngineProfile p => new PyDict().Add("credit_model", p.CreditModel).Add("headcount_model", p.HeadcountModel),
        ProgramEntry e => ProgramFields(e),
        FindingResolution f => FindingFields(f),
        RunManifest m => ManifestFields(m),
        ManualOverride o => OverrideFields(o),
        _ => throw new PyUnsupportedException("unknown model"),
    };

    // The dataclass field order differs from to_dict()'s order (decided_by and decided_at come before detail).
    private static PyDict FindingFields(FindingResolution f) => new PyDict()
        .Add("finding_id", f.FindingId).Add("client_id", f.ClientId).Add("tax_year", f.TaxYear).Add("resolution", f.Resolution).Add("decided_by", f.DecidedBy)
        .Add("decided_at", f.DecidedAt).Add("detail", f.Detail).Add("note", f.Note).Add("superseded_at", f.SupersededAt);

    private static PyDict Wrap(PyDict fields) => new PyDict().Add("fields", fields).Add("order", fields.Select(kv => (object?)kv.Key).ToList());

    private static PyDict ProgramFields(ProgramEntry e) => new PyDict()
        .Add("code", e.Code).Add("name", e.Name).Add("level", e.Level).Add("jurisdiction_code", e.JurisdictionCode).Add("pack_file", e.PackFile)
        .Add("state", e.State).Add("lifecycle", e.Lifecycle).Add("engine_profile", Fields(e.EngineProfile)).Add("notes", e.Notes);

    private static PyDict DateTag(DateOnly d) => new PyDict().Add("$date", WarehouseIso(d));

    private static string WarehouseIso(DateOnly d) => d.ToString("yyyy-MM-dd", System.Globalization.CultureInfo.InvariantCulture);

    private static PyDict? DtTag(PyDateTime? d) => d is null ? null : new PyDict().Add("$dt", d.Value.IsoFormat());

    private static PyDict ManifestFields(RunManifest m) => new PyDict()
        .Add("run_id", m.RunId).Add("client_id", m.ClientId).Add("program_code", m.ProgramCode).Add("tax_year", m.TaxYear)
        .Add("fiscal_year_begin", DateTag(m.FiscalYearBegin)).Add("fiscal_year_end", DateTag(m.FiscalYearEnd)).Add("run_started_at", DtTag(m.RunStartedAt))
        .Add("run_status", m.RunStatus).Add("entity_id", m.EntityId).Add("source_snapshot_id", m.SourceSnapshotId)
        .Add("step1_assumption_set_id", m.Step1AssumptionSetId).Add("step1_assumption_sha256", m.Step1AssumptionSha256)
        .Add("onezero_assumption_set_id", m.OnezeroAssumptionSetId).Add("onezero_assumption_sha256", m.OnezeroAssumptionSha256)
        .Add("rule_pack_version", m.RulePackVersion).Add("code_commit", m.CodeCommit).Add("calculation_id", m.CalculationId)
        .Add("run_completed_at", DtTag(m.RunCompletedAt)).Add("superseded_by_run_id", m.SupersededByRunId).Add("triggered_by", m.TriggeredBy);

    private static PyDict OverrideFields(ManualOverride o) => new PyDict()
        .Add("override_id", o.OverrideId).Add("run_id", o.RunId).Add("client_id", o.ClientId).Add("scope", o.Scope).Add("target_key", o.TargetKey)
        .Add("field_changed", o.FieldChanged).Add("value_before", o.ValueBefore).Add("value_after", o.ValueAfter).Add("reason_code", o.ReasonCode)
        .Add("justification_text", o.JustificationText).Add("created_by", o.CreatedBy).Add("created_at", DtTag(o.CreatedAt))
        .Add("approved_by", o.ApprovedBy).Add("approved_at", DtTag(o.ApprovedAt));
}
