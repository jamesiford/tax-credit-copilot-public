using TaxCredit.Domain.Numerics;

namespace TaxCredit.Domain.Filters;

/// <summary>One whitelisted filter column: the SQL expression a wire name maps to and its grammar type (<c>text</c>, <c>numeric</c> or <c>enum</c>).</summary>
/// <param name="SqlExpression">The SQL expression interpolated into the statement (only ever taken from the caller's whitelist).</param>
/// <param name="Kind">The grammar type; an unknown kind is a <c>KeyError</c> when the term compiles, as in Python.</param>
public sealed record FilterColumn(string SqlExpression, string Kind);

/// <summary>The result of <see cref="GridFilter.Compile"/>: Python's <c>(sql, values, applied)</c> tuple.</summary>
/// <param name="Sql">The clause text, <c>" AND (..) AND (..)"</c>, or empty.</param>
/// <param name="Values">The bound parameters in placeholder order: doubles for numeric terms, strings for text and enum terms.</param>
/// <param name="Applied">What actually compiled, wire name to expression, in first-seen order (a repeated name keeps its first position and takes the last expression).</param>
public sealed record CompiledFilter(string Sql, IReadOnlyList<object> Values, PyDict Applied)
{
    /// <summary>The tuple as a tree, the way the Python golden records it: <c>[sql, values, applied]</c>.</summary>
    /// <returns>The tree.</returns>
    public List<object?> ToTree() => [Sql, Values.Cast<object?>().ToList(), Applied];
}

/// <summary>
/// Python <c>tools/grid_filter.py</c>: the <c>filter=</c> grammar (<c>col:expr;col:expr</c>), parsed once and compiled into SQL predicates.
/// The column must be on the caller's whitelist and is never interpolated otherwise; every value is a bound parameter; an unparseable term is DROPPED.
/// </summary>
public static class GridFilter
{
    // Longest first: ">=" must win over ">".
    private static readonly string[] Comparators = [">=", "<=", ">", "<", "="];

    /// <summary>Python <c>compile_filters(wire, columns)</c>.</summary>
    /// <param name="wire">The query-string value; <c>null</c> and empty compile to nothing.</param>
    /// <param name="columns">Wire column name to <see cref="FilterColumn"/>; names not in it are ignored.</param>
    /// <returns>The clause, the bound values and the filters that took effect.</returns>
    public static CompiledFilter Compile(string? wire, IReadOnlyDictionary<string, FilterColumn> columns)
    {
        ArgumentNullException.ThrowIfNull(columns);
        var clauses = new List<string>();
        var values = new List<object>();
        var applied = new PyDict();
        foreach (var term in (wire ?? string.Empty).Split(';'))
        {
            var colon = term.IndexOf(':', StringComparison.Ordinal);
            if (colon < 0)
            {
                continue;
            }

            var name = PyStr.Strip(term[..colon]);
            var expr = PyStr.Strip(term[(colon + 1)..]);
            if (!columns.TryGetValue(name, out var spec) || expr.Length == 0)
            {
                continue;
            }

            var built = Build(spec, expr);
            if (built is null)
            {
                continue;
            }

            clauses.Add("(" + built.Value.Clause + ")");
            values.AddRange(built.Value.Params);
            applied.Set(name, expr);
        }

        return new CompiledFilter(clauses.Count > 0 ? " AND " + string.Join(" AND ", clauses) : string.Empty, values, applied);
    }

    private static (string Clause, object[] Params)? Build(FilterColumn spec, string expr) => spec.Kind switch
    {
        "numeric" => NumericPredicate(spec.SqlExpression, expr),
        "text" => TextPredicate(spec.SqlExpression, expr),
        "enum" => EnumPredicate(spec.SqlExpression, expr),
        _ => throw new PyKeyError(spec.Kind),
    };

    // Python `float(text.strip())` inside `except (TypeError, ValueError): return None`.
    internal static double? Number(string text) => PyFloat.TryParse(PyStr.Strip(text), out var v) ? v : null;

    internal static (string, object[])? NumericPredicate(string column, string expr)
    {
        var dots = expr.IndexOf("..", StringComparison.Ordinal);
        if (dots >= 0)
        {
            var (a, b) = (Number(expr[..dots]), Number(expr[(dots + 2)..]));
            // Python min()/max() keep the first operand unless the second beats it, so NaN bounds keep their position.
            return a is null || b is null ? null : ($"{column} >= ? AND {column} <= ?", [PyArith.Min(a.Value, b.Value), PyArith.Max(a.Value, b.Value)]);
        }

        foreach (var op in Comparators)
        {
            if (expr.StartsWith(op, StringComparison.Ordinal))
            {
                return Number(expr[op.Length..]) is { } value ? ($"{column} {op} ?", [value]) : null;
            }
        }

        // A bare number reads as ">=", matching the browser (every numeric column answers an "at least" question).
        return Number(expr) is { } bare ? ($"{column} >= ?", [bare]) : null;
    }

    internal static (string, object[])? TextPredicate(string column, string expr)
    {
        var needle = PyStr.Strip(expr.StartsWith('~') ? expr[1..] : expr);
        if (needle.Length == 0)
        {
            return null;
        }

        // LIKE wildcards in the needle would let a filter widen itself, so they are escaped rather than honoured.
        var escaped = needle.Replace("[", "[[]", StringComparison.Ordinal).Replace("%", "[%]", StringComparison.Ordinal).Replace("_", "[_]", StringComparison.Ordinal);
        return ($"LOWER({column}) LIKE ?", [$"%{PyStrCase.Lower(escaped)}%"]);
    }

    internal static (string, object[])? EnumPredicate(string column, string expr)
    {
        var values = expr.Split('|').Select(PyStr.Strip).Where(p => p.Length > 0).Cast<object>().ToArray();
        return values.Length == 0 ? null : ($"{column} IN ({string.Join(", ", values.Select(_ => "?"))})", values);
    }
}
