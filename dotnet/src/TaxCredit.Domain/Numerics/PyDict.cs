using System.Collections;

namespace TaxCredit.Domain.Numerics;

/// <summary>
/// An insertion-ordered string-keyed mapping with Python <c>dict</c> semantics. Values are <c>null</c>, <c>bool</c>,
/// <c>long</c>, <see cref="System.Numerics.BigInteger"/>, <c>double</c>, <c>string</c>, <c>IReadOnlyList&lt;object?&gt;</c>
/// or another <see cref="PyDict"/>.
/// </summary>
/// <remarks>
/// Why a type of its own: Python's <c>dict</c> keeps first-insertion order, and assigning an existing key replaces
/// the value but not the position (so <c>json.loads('{"a":1,"b":2,"a":3}')</c> is <c>{"a": 3, "b": 2}</c>). Iteration
/// order is the contract wherever the result is hashed or written to a row.
/// </remarks>
public sealed class PyDict : IEnumerable<KeyValuePair<string, object?>>
{
    private readonly List<KeyValuePair<string, object?>> _items = [];
    private readonly Dictionary<string, int> _index = new(StringComparer.Ordinal);

    /// <summary>The number of entries.</summary>
    public int Count => _items.Count;

    /// <summary>The keys in insertion order.</summary>
    public IEnumerable<string> Keys => _items.Select(kv => kv.Key);

    /// <summary>The value for a key; throws <see cref="PyKeyError"/> like <c>d[key]</c> when absent.</summary>
    /// <param name="key">The key.</param>
    /// <returns>The value.</returns>
    public object? this[string key] =>
        _index.TryGetValue(key, out var i) ? _items[i].Value : throw new PyKeyError(key);

    /// <summary>Appends a new entry (a Python dict literal with distinct keys).</summary>
    /// <param name="key">The key; it must not already be present (use <see cref="Set"/> to replace).</param>
    /// <param name="value">The value.</param>
    /// <returns>This dictionary, for chaining.</returns>
    public PyDict Add(string key, object? value)
    {
        if (_index.ContainsKey(key))
        {
            throw new ArgumentException("Duplicate key; use Set for dict assignment: " + key, nameof(key));
        }

        _index[key] = _items.Count;
        _items.Add(new KeyValuePair<string, object?>(key, value));
        return this;
    }

    /// <summary>Python <c>d[key] = value</c>: replaces the value of an existing key in place, else appends.</summary>
    /// <param name="key">The key.</param>
    /// <param name="value">The value.</param>
    /// <returns>This dictionary, for chaining.</returns>
    public PyDict Set(string key, object? value)
    {
        if (_index.TryGetValue(key, out var i))
        {
            _items[i] = new KeyValuePair<string, object?>(key, value);
            return this;
        }

        return Add(key, value);
    }

    /// <summary>Python <c>key in d</c>.</summary>
    /// <param name="key">The key.</param>
    /// <returns>Whether the key is present.</returns>
    public bool ContainsKey(string key) => _index.ContainsKey(key);

    /// <summary>Python <c>d.get(key)</c> with presence reported separately.</summary>
    /// <param name="key">The key.</param>
    /// <param name="value">The value when present.</param>
    /// <returns>Whether the key is present.</returns>
    public bool TryGetValue(string key, out object? value)
    {
        if (_index.TryGetValue(key, out var i))
        {
            value = _items[i].Value;
            return true;
        }

        value = null;
        return false;
    }

    /// <inheritdoc />
    public IEnumerator<KeyValuePair<string, object?>> GetEnumerator() => _items.GetEnumerator();

    /// <inheritdoc />
    IEnumerator IEnumerable.GetEnumerator() => GetEnumerator();
}
