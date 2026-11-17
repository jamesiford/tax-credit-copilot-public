using System.Collections;

namespace TaxCredit.Domain.BaseYear;

/// <summary>
/// An insertion-ordered mapping with Python <c>dict</c> semantics for non-string keys (the <c>{tax_year: value}</c> and <c>{unit_id: ...}</c> dicts).
/// </summary>
/// <remarks>Why: assigning an existing key replaces the value but keeps the key's first position, and iteration order is the contract wherever a result is hashed.</remarks>
/// <typeparam name="TKey">The key type.</typeparam>
/// <typeparam name="TValue">The value type.</typeparam>
public sealed class OrderedMap<TKey, TValue> : IEnumerable<KeyValuePair<TKey, TValue>>
    where TKey : notnull
{
    private readonly List<KeyValuePair<TKey, TValue>> _items = [];
    private readonly Dictionary<TKey, int> _index = [];

    /// <summary>The number of entries.</summary>
    public int Count => _items.Count;

    /// <summary>The keys in insertion order.</summary>
    public IEnumerable<TKey> Keys => _items.Select(kv => kv.Key);

    /// <summary>The values in insertion order.</summary>
    public IEnumerable<TValue> Values => _items.Select(kv => kv.Value);

    /// <summary>Python <c>d[key] = value</c>: replaces an existing key in place, else appends.</summary>
    /// <param name="key">The key.</param>
    /// <param name="value">The value.</param>
    /// <returns>This map, for chaining.</returns>
    public OrderedMap<TKey, TValue> Set(TKey key, TValue value)
    {
        if (_index.TryGetValue(key, out var i))
        {
            _items[i] = new KeyValuePair<TKey, TValue>(key, value);
        }
        else
        {
            _index[key] = _items.Count;
            _items.Add(new KeyValuePair<TKey, TValue>(key, value));
        }

        return this;
    }

    /// <summary>Python <c>key in d</c>.</summary>
    /// <param name="key">The key.</param>
    /// <returns>Whether present.</returns>
    public bool ContainsKey(TKey key) => _index.ContainsKey(key);

    /// <summary>Python <c>d.get(key)</c> with presence reported separately.</summary>
    /// <param name="key">The key.</param>
    /// <param name="value">The value when present.</param>
    /// <returns>Whether present.</returns>
    public bool TryGetValue(TKey key, out TValue value)
    {
        if (_index.TryGetValue(key, out var i))
        {
            value = _items[i].Value;
            return true;
        }

        value = default!;
        return false;
    }

    /// <inheritdoc />
    public IEnumerator<KeyValuePair<TKey, TValue>> GetEnumerator() => _items.GetEnumerator();

    /// <inheritdoc />
    IEnumerator IEnumerable.GetEnumerator() => GetEnumerator();
}
