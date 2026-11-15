using TaxCredit.Domain.Numerics;

namespace TaxCredit.Domain.Programs;

/// <summary>
/// The parsed manifest (Python <c>tools/program_registry.Registry</c>): entries in manifest order and the folder their pack
/// files live in. Reading the manifest is <see cref="RuleLibrary.LoadRegistry"/>; this type only answers questions about it.
/// </summary>
/// <param name="Entries">Entries in manifest order.</param>
/// <param name="RulesDir">The rules folder as shown in messages.</param>
/// <param name="Source">The manifest file name or path as given.</param>
public sealed record ProgramRegistry(IReadOnlyList<ProgramEntry> Entries, string RulesDir, string Source)
{
    /// <summary>The entry for a program code (case-insensitive), retired ones included, or <c>null</c> (Python <c>get</c>).</summary>
    /// <param name="code">The code; <c>null</c> reads as empty (<c>(code or "").upper()</c>).</param>
    /// <returns>The entry.</returns>
    public ProgramEntry? Get(string? code)
    {
        var wanted = PyStr.Upper(code ?? string.Empty);
        return Entries.FirstOrDefault(e => string.Equals(e.Code, wanted, StringComparison.Ordinal));
    }

    /// <summary>Entries the engine will resolve: everything not retired.</summary>
    /// <returns>The entries, in manifest order.</returns>
    public IReadOnlyList<ProgramEntry> Active() => Entries.Where(e => e.Lifecycle != "retired").ToList();

    /// <summary>Non-federal programs, code to pack file: the content of <c>PROGRAM_CODE_TO_PACK</c>, in manifest order.</summary>
    /// <returns>The ordered pairs.</returns>
    public IReadOnlyList<KeyValuePair<string, string>> CodeToPack() =>
        Active().Where(e => e.Level != "federal").Select(e => KeyValuePair.Create(e.Code, e.PackFile)).ToList();

    /// <summary>State to pack file, the first listed program per state winning: the content of <c>STATE_TO_PACK</c>.</summary>
    /// <returns>The ordered pairs.</returns>
    public IReadOnlyList<KeyValuePair<string, string>> StateToPack()
    {
        var seen = new HashSet<string>(StringComparer.Ordinal);
        var result = new List<KeyValuePair<string, string>>();
        foreach (var entry in Active().Where(e => !string.IsNullOrEmpty(e.State)))
        {
            if (seen.Add(entry.State!))
            {
                result.Add(KeyValuePair.Create(entry.State!, entry.PackFile));
            }
        }

        return result;
    }

    /// <summary>
    /// Every non-retired program of a state, in manifest order; the first is the state's DEFAULT program (what <see cref="StateToPack"/>
    /// shows), so reordering the manifest changes the default. [F04c.1]
    /// </summary>
    /// <param name="state">The state (case-insensitive).</param>
    /// <returns>The programs.</returns>
    public IReadOnlyList<ProgramEntry> ForState(string? state)
    {
        var wanted = PyStr.Upper(state ?? string.Empty);
        return Active().Where(e => string.Equals(e.State, wanted, StringComparison.Ordinal)).ToList();
    }

    /// <summary>Federal-level programs, which have no state key and are found by jurisdiction level.</summary>
    /// <returns>The programs.</returns>
    public IReadOnlyList<ProgramEntry> Federal() => Active().Where(e => e.Level == "federal").ToList();
}

/// <summary>
/// A read-only mapping computed from the registry each time it is read (Python <c>RegistryView</c>, behind <c>STATE_TO_PACK</c> and
/// <c>PROGRAM_CODE_TO_PACK</c>), so a changed manifest is honoured.
/// </summary>
public sealed class RegistryView
{
    private readonly Func<IReadOnlyList<KeyValuePair<string, string>>> _data;

    internal RegistryView(Func<IReadOnlyList<KeyValuePair<string, string>>> data) => _data = data;

    /// <summary>Python <c>list(view.items())</c>.</summary>
    /// <returns>The ordered pairs.</returns>
    public IReadOnlyList<KeyValuePair<string, string>> Items() => _data();

    /// <summary>Python <c>len(view)</c>.</summary>
    public int Count => _data().Count;

    /// <summary>Python <c>view[key]</c>.</summary>
    /// <param name="key">The key (case-sensitive).</param>
    /// <returns>The pack file.</returns>
    /// <exception cref="PyKeyError">When the key is not in the view.</exception>
    public string this[string key] => TryGet(key, out var value) ? value : throw new PyKeyError(key);

    /// <summary>Python <c>key in view</c>.</summary>
    /// <param name="key">The key.</param>
    /// <returns>Whether the key is present.</returns>
    public bool Contains(string key) => TryGet(key, out _);

    /// <summary>Python <c>view.get(key)</c>.</summary>
    /// <param name="key">The key.</param>
    /// <param name="value">The pack file when present.</param>
    /// <returns>Whether the key is present.</returns>
    public bool TryGet(string key, out string value)
    {
        foreach (var kv in _data())
        {
            if (string.Equals(kv.Key, key, StringComparison.Ordinal))
            {
                value = kv.Value;
                return true;
            }
        }

        value = string.Empty;
        return false;
    }

    /// <summary>Python <c>sorted(view)</c>: the keys by code point.</summary>
    /// <returns>The sorted keys.</returns>
    public IReadOnlyList<string> SortedKeys() => PySort.Sorted(_data(), kv => kv.Key, PyStr.Comparer).Select(kv => kv.Key).ToList();
}
