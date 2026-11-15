using System.Reflection;
using System.Runtime.CompilerServices;
using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Programs;
using TaxCredit.Domain.Runs;

namespace TaxCredit.Parity.Tests;

/// <summary>
/// Reflection bridge between the goldens' snake_case dataclass records (<c>{"fields":..., "order":[...]}</c>) and the C# records of the run and draft
/// models: build one from keyword arguments, edit it like <c>dataclasses.replace</c>, list its fields in declaration order, and check the
/// frozen-assignment and hashability facts. Reflection is acceptable here because the test's job is to compare, not to be a second implementation.
/// </summary>
internal static class ModelBridge
{
    private static readonly Dictionary<Type, Func<string, object>> Enums = new()
    {
        [typeof(BatchKind)] = v => RunEnumExtensions.BatchKindFromValue(v),
        [typeof(ScopeKind)] = v => RunEnumExtensions.ScopeKindFromValue(v),
        [typeof(BatchStatus)] = v => RunEnumExtensions.BatchStatusFromValue(v),
        [typeof(ItemStatus)] = v => RunEnumExtensions.ItemStatusFromValue(v),
        [typeof(DraftStatus)] = v => DraftStatusExtensions.FromValue(v),
    };

    private static readonly Dictionary<string, Type> Models = new()
    {
        ["run_batch"] = typeof(RunBatch),
        ["run_batch_item"] = typeof(RunBatchItem),
        ["item_result"] = typeof(ItemResult),
        ["fingerprint"] = typeof(Fingerprint),
        ["program_draft"] = typeof(ProgramDraft),
        ["draft_event"] = typeof(DraftEvent),
    };

    public static bool IsModel(string name) => Models.ContainsKey(name);

    public static object Make(string model, PyDict kw) => Apply(Activator.CreateInstance(Models[model])!, kw);

    public static object Edit(object model, PyDict changes) => Apply(model.GetType().GetMethod("<Clone>$")!.Invoke(model, null)!, changes);

    public static PyDict Fields(object model)
    {
        var fields = new PyDict();
        foreach (var p in Properties(model.GetType()))
        {
            fields.Add(Snake(p.Name), ToTree(p.GetValue(model)));
        }

        return fields;
    }

    public static PyDict Wrap(object model)
    {
        var fields = Fields(model);
        return new PyDict().Add("fields", fields).Add("order", fields.Select(kv => (object?)kv.Key).ToList());
    }

    public static PyDict Hash(object left, object right)
    {
        if (left.GetType().GetProperty("HashableInPython", BindingFlags.Public | BindingFlags.Static)?.GetValue(null) is false)
        {
            throw new PyTypeError("unhashable type: 'dict'");
        }

        return new PyDict().Add("hashable", true).Add("equal_objects_equal_hash", !left.Equals(right) || left.GetHashCode() == right.GetHashCode());
    }

    // A frozen dataclass raises on assignment; in C# the guarantee is that the property can only be set in an initializer.
    public static string FrozenAssign(object model, string field)
    {
        var property = model.GetType().GetProperty(Pascal(field)) ?? throw new InvalidOperationException("no property for " + field);
        var initOnly = property.SetMethod!.ReturnParameter.GetRequiredCustomModifiers().Contains(typeof(IsExternalInit));
        return initOnly ? throw new FrozenAssignment("cannot assign to field '" + field + "'") : "assignable";
    }

    public static object? Decode(object? v) => v switch
    {
        PyDict { Count: 1 } d when d.ContainsKey("$dt") => PyDateTime.FromIsoFormat((string)d["$dt"]!),
        _ => v,
    };

    public static PyDict? DtTag(PyDateTime? d) => d is null ? null : new PyDict().Add("$dt", d.Value.IsoFormat());

    private static IEnumerable<PropertyInfo> Properties(Type type) =>
        type.GetProperties(BindingFlags.Public | BindingFlags.Instance).Where(p => p.SetMethod is not null);

    private static object Apply(object model, PyDict kw)
    {
        var type = model.GetType();
        foreach (var (key, value) in kw)
        {
            var property = type.GetProperty(Pascal(key)) ?? throw new InvalidOperationException("no property for " + key);
            property.SetValue(model, FromTree(property.PropertyType, Decode(value)));
        }

        return model;
    }

    private static object? FromTree(Type type, object? v)
    {
        if (v is null)
        {
            return null;
        }

        var target = Nullable.GetUnderlyingType(type) ?? type;
        if (Enums.TryGetValue(target, out var parse) && v is string s)
        {
            return parse(s);
        }

        if (target == typeof(IReadOnlyList<long>))
        {
            return ((List<object?>)v).Select(x => (long)x!).ToList();
        }

        return v;
    }

    private static object? ToTree(object? v) => v switch
    {
        PyDateTime d => DtTag(d),
        ItemStatus e => e.Value(),
        BatchStatus e => e.Value(),
        BatchKind e => e.Value(),
        ScopeKind e => e.Value(),
        DraftStatus e => e.Value(),
        IReadOnlyList<long> list => list.Cast<object?>().ToList(),
        _ => v,
    };

    private static string Pascal(string snake) => string.Concat(snake.Split('_').Select(p => char.ToUpperInvariant(p[0]) + p[1..]));

    private static string Snake(string pascal)
    {
        var sb = new System.Text.StringBuilder();
        foreach (var c in pascal)
        {
            if (char.IsUpper(c) && sb.Length > 0)
            {
                sb.Append('_');
            }

            sb.Append(char.ToLowerInvariant(c));
        }

        return sb.ToString();
    }

    private sealed class FrozenAssignment(string message) : PyException("FrozenInstanceError", message);
}
