using TaxCredit.Domain.Calculation;
using TaxCredit.Domain.Numerics;

namespace TaxCredit.Domain.Programs;

/// <summary>
/// The rule-pack tools over one rules folder (Python <c>tools/credit_math.py</c>, <c>tools/program_registry.py</c>, <c>tools/pack_lookup.py</c>,
/// <c>tools/program_credit.py</c>): which programs exist, which pack answers a state or a program code, which year's statute applies,
/// and the benefit math. Python reads the folder named by <c>RULES_DIR</c> through <c>config.get_settings</c>; here the folder is injected as an
/// <see cref="IRulePackSource"/>, so the Domain does no I/O. [ADR-005, ADR-013]
/// </summary>
/// <remarks>
/// Python keeps the parsed registry in a module-level cache keyed by (manifest file, rules folder) and re-reads it only when the manifest's
/// modification stamp changes (<c>program_registry._cache</c>). That is call history, so it is mirrored: one cache per library instance, which is
/// one per source, exactly as the Python key makes one entry per folder. A manifest that fails to parse is never cached.
/// </remarks>
public sealed partial class RuleLibrary
{
    private readonly IRulePackSource _source;
    private readonly IIngestedOneZeroSource? _ingestion;
    private readonly IProgramWageSource? _wages;
    private readonly Lock _gate = new();
    private (long Stamp, ProgramRegistry Registry)? _cached;

    /// <summary>Initialises the library.</summary>
    /// <param name="source">Where rule packs and the manifest are read from.</param>
    /// <param name="ingestion">The optional ingestion hook of <see cref="LoadPackOneZero"/>; <c>null</c> is "none".</param>
    /// <param name="wages">The payroll wage lookup behind percentage-of-wages benefits; <c>null</c> refuses such a program.</param>
    public RuleLibrary(IRulePackSource source, IIngestedOneZeroSource? ingestion = null, IProgramWageSource? wages = null)
    {
        ArgumentNullException.ThrowIfNull(source);
        _source = source;
        _ingestion = ingestion;
        _wages = wages;
        StateToPack = new RegistryView(() => LoadRegistry().StateToPack());
        CodeToPack = new RegistryView(() => LoadRegistry().CodeToPack());
    }

    /// <summary>The view behind Python <c>STATE_TO_PACK</c>: state to pack file, a state's DEFAULT program first.</summary>
    public RegistryView StateToPack { get; }

    /// <summary>The view behind Python <c>PROGRAM_CODE_TO_PACK</c>: non-federal program code to pack file.</summary>
    public RegistryView CodeToPack { get; }

    /// <summary>Python <c>load_registry</c>: the registry for the manifest now in force, re-read when its stamp changes.</summary>
    /// <returns>The registry.</returns>
    /// <exception cref="RegistryError">When the manifest is missing or unusable.</exception>
    public ProgramRegistry LoadRegistry()
    {
        var stamp = _source.RegistryStamp() ?? throw new RegistryError($"program registry not found: {_source.RegistryFile}");
        lock (_gate)
        {
            if (_cached is { } hit && hit.Stamp == stamp)
            {
                return hit.Registry;
            }

            var registry = RegistryParser.Parse(_source.ReadRegistryText(), Path.GetFileName(_source.RegistryFile), _source);
            _cached = (stamp, registry);
            return registry;
        }
    }

    /// <summary>Python <c>programs_for_state</c>: the state's programs in registry order (first = default).</summary>
    /// <param name="state">The state (case-insensitive).</param>
    /// <returns>The programs.</returns>
    public IReadOnlyList<ProgramEntry> ProgramsForState(string state) => LoadRegistry().ForState(state);

    /// <summary>Python <c>program_for_code</c>: the active entry for a code, <c>null</c> when unknown or retired.</summary>
    /// <param name="code">The program code (case-insensitive).</param>
    /// <returns>The entry or <c>null</c>.</returns>
    public ProgramEntry? ProgramForCode(string code)
    {
        var entry = LoadRegistry().Get(code);
        return entry is not null && entry.Lifecycle != "retired" ? entry : null;
    }

    /// <summary>
    /// Python <c>pack_lookup.pack_file_for</c>: a state names its DEFAULT program's pack; a program code names its own; a pack's <c>credit.code</c>
    /// and a federal entry's code are found last. A state is tried first, which is safe because no program code is two letters long.
    /// </summary>
    /// <param name="stateOrCode">A state or a program code.</param>
    /// <returns>The pack file, or <c>null</c> when neither is registered.</returns>
    public string? PackFileFor(string? stateOrCode)
    {
        var key = PyStr.Upper(stateOrCode ?? string.Empty);
        if (StateToPack.TryGet(key, out var viaState))
        {
            return viaState;
        }

        var registry = LoadRegistry();
        var entry = registry.Get(key);
        if (entry is not null && entry.Lifecycle != "retired")
        {
            return entry.PackFile;
        }

        foreach (var kv in CodeToPack.Items())
        {
            var credit = RuleTree.Get(LoadPack(kv.Value), "credit", new PyDict());
            if (RuleTree.AsMapping(credit).TryGetValue("code", out var code) && code is string text && string.Equals(text, key, StringComparison.Ordinal))
            {
                return kv.Value;
            }
        }

        return registry.Federal().FirstOrDefault(e => string.Equals(e.Code, key, StringComparison.Ordinal))?.PackFile;
    }
}
