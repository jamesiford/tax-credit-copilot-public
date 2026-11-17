using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Programs;

namespace TaxCredit.Domain.Pipeline;

/// <summary>
/// Which program a run is for, when the caller did not say (Python <c>application/program_defaults.py</c>, ADR-013). The state is derived from data: the
/// states the client's payroll holds, narrowed to those whose registered program has an authored year pack for the year asked.
/// </summary>
/// <remarks>
/// Not mirrored: the <c>logging</c> calls and the <c>DeprecationWarning</c> of <c>derive_run_state</c>; neither changes a value. The payroll footprint is a
/// delegate (<c>payroll_scope(client_id).states</c>), because reading it is I/O.
/// </remarks>
/// <param name="library">The rule library (the registry and the authored years).</param>
/// <param name="payrollStates">The work states of a client's payroll, sorted (Python <c>payroll_scope(client_id).states</c>; <c>null</c> client is the default tenant). May throw: an unreadable footprint reads as none.</param>
public sealed class ProgramDefaults(RuleLibrary library, Func<long?, IReadOnlyList<string>> payrollStates)
{
    /// <summary>Python <c>DEPRECATED_DEFAULT_STATE</c>: the value every run used before the state was derived.</summary>
    public const string DeprecatedDefaultState = "GA";

    /// <summary>Python <c>calculable_states</c>: states, in registry order, whose program has an authored year pack (for <paramref name="taxYear"/> when given).</summary>
    /// <param name="taxYear">The year, or <c>null</c>.</param>
    /// <returns>The states.</returns>
    public IReadOnlyList<string> CalculableStates(long? taxYear = null)
    {
        var output = new List<string>();
        foreach (var entry in library.LoadRegistry().Active())
        {
            if (string.IsNullOrEmpty(entry.State) || output.Contains(entry.State, StringComparer.Ordinal))
            {
                continue;
            }

            var years = library.AuthoredYears(entry.PackFile);
            if (years.Count > 0 && (taxYear is null || years.Contains(taxYear.Value)))
            {
                output.Add(entry.State);
            }
        }

        return output;
    }

    /// <summary>Python <c>pick_state</c>: the first calculable state, in registry order, that the client holds payroll in; <c>null</c> when there is none.</summary>
    /// <param name="clientStates">The states the payroll holds.</param>
    /// <param name="taxYear">The year, or <c>null</c>.</param>
    /// <returns>The state or <c>null</c>.</returns>
    public string? PickState(IEnumerable<string> clientStates, long? taxYear)
    {
        var held = clientStates.Select(PyStr.Upper).ToHashSet(StringComparer.Ordinal);
        var candidates = CalculableStates(taxYear).Where(held.Contains).ToList();
        return candidates.Count > 0 ? candidates[0] : null;
    }

    /// <summary>Python <c>derive_run_state</c>: the caller's state if given, else derived from the payroll, else the deprecated default.</summary>
    /// <param name="clientId">The client.</param>
    /// <param name="taxYear">The year.</param>
    /// <param name="requested">The caller's state (an empty string is "none").</param>
    /// <returns>The upper-cased state.</returns>
    public string DeriveRunState(long? clientId, long? taxYear, string? requested = null)
    {
        if (!string.IsNullOrEmpty(requested))
        {
            return PyStr.Upper(requested);
        }

        return PickState(Footprint(clientId), taxYear) ?? DeprecatedDefaultState;
    }

    /// <summary>Python <c>state_for_location</c>: the caller's state, else the location's own state prefix, else derived from payroll.</summary>
    /// <param name="clientId">The client.</param>
    /// <param name="worksiteId">The location.</param>
    /// <param name="taxYear">The year.</param>
    /// <param name="requested">The caller's state.</param>
    /// <returns>The upper-cased state.</returns>
    public string StateForLocation(long? clientId, string worksiteId, long? taxYear, string? requested = null)
    {
        if (!string.IsNullOrEmpty(requested))
        {
            return PyStr.Upper(requested);
        }

        var cut = worksiteId.IndexOf('_', StringComparison.Ordinal);
        var prefix = PyStr.Upper(cut < 0 ? worksiteId : worksiteId[..cut]);
        return library.LoadRegistry().StateToPack().Any(kv => kv.Key == prefix) ? prefix : DeriveRunState(clientId, taxYear);
    }

    /// <summary>Python <c>calculable_programs_for_state</c>: codes of a state's programs with an authored year pack (for <paramref name="taxYear"/> when given), registry order.</summary>
    /// <remarks>When the year narrows the list to nothing the year-less list is returned, so the caller's own decline names a real program. [F04c.2]</remarks>
    /// <param name="state">The state.</param>
    /// <param name="taxYear">The year, or <c>null</c>.</param>
    /// <returns>The codes.</returns>
    public IReadOnlyList<string> CalculableProgramsForState(string state, long? taxYear = null)
    {
        var entries = library.ProgramsForState(state).Where(e => library.AuthoredYears(e.PackFile).Count > 0).ToList();
        var forYear = entries.Where(e => taxYear is null || library.AuthoredYears(e.PackFile).Contains(taxYear.Value)).ToList();
        return (forYear.Count > 0 ? forYear : entries).Select(e => e.Code).ToList();
    }

    /// <summary>Python <c>derive_run_programs</c>: every calculable program the client's payroll states hold, registry order; empty when the footprint cannot be read.</summary>
    /// <param name="clientId">The client.</param>
    /// <param name="taxYear">The year.</param>
    /// <returns>The codes.</returns>
    public IReadOnlyList<string> DeriveRunPrograms(long? clientId, long? taxYear)
    {
        var held = Footprint(clientId).Select(PyStr.Upper).ToHashSet(StringComparer.Ordinal);
        var output = new List<string>();
        foreach (var entry in library.LoadRegistry().Active())
        {
            if (entry.State is not null && held.Contains(entry.State) && CalculableProgramsForState(entry.State, taxYear).Contains(entry.Code, StringComparer.Ordinal))
            {
                output.Add(entry.Code);
            }
        }

        return output;
    }

    /// <summary>Python <c>check_program_state</c>.</summary>
    /// <param name="state">The state, if named.</param>
    /// <param name="programCode">The program, if named.</param>
    /// <exception cref="ProgramStateConflict">When both are given and the program's registry state is not that state.</exception>
    public void CheckProgramState(string? state, string? programCode)
    {
        if (string.IsNullOrEmpty(state) || string.IsNullOrEmpty(programCode))
        {
            return;
        }

        var entry = library.ProgramForCode(programCode);
        if (entry is not null && !string.IsNullOrEmpty(entry.State) && entry.State != PyStr.Upper(state))
        {
            throw new ProgramStateConflict(
                $"program {entry.Code} is a {entry.State} program, not {PyStr.Upper(state)}: name the program or the state, or make them agree");
        }
    }

    /// <summary>Python <c>program_state</c>: the state a program is priced in.</summary>
    /// <param name="programCode">The program.</param>
    /// <returns>The state.</returns>
    /// <exception cref="ProgramNotRunnable">For an unknown, retired or federal program.</exception>
    public string ProgramState(string programCode)
    {
        var entry = library.ProgramForCode(programCode) ?? throw new ProgramNotRunnable($"no active program has the code {PyStr.Repr(programCode)}");
        return !string.IsNullOrEmpty(entry.State)
            ? entry.State
            : throw new ProgramNotRunnable(
                $"{entry.Code} is a {entry.Level} program with no state: a run prices a state's payroll rows, so federal programs are described but not runnable");
    }

    /// <summary>Python <c>resolve_program</c>: <c>(state, program_code)</c> for a request, the program first, the state as a convenience.</summary>
    /// <param name="clientId">The client.</param>
    /// <param name="state">The state, if named.</param>
    /// <param name="programCode">The program, if named; it wins and fixes the state.</param>
    /// <param name="taxYear">The year.</param>
    /// <param name="requireProgram">True for a READ: a state with several programs must name one.</param>
    /// <returns>The state and the program (<c>null</c> only for a state with no registered program).</returns>
    /// <exception cref="ProgramStateConflict">When the program and state disagree.</exception>
    /// <exception cref="ProgramChoiceRequired">When a read names a state with several programs.</exception>
    public (string State, string? ProgramCode) ResolveProgram(long? clientId, string? state, string? programCode, long? taxYear, bool requireProgram = false)
    {
        if (!string.IsNullOrEmpty(programCode))
        {
            CheckProgramState(state, programCode);
            return (ProgramState(programCode), PyStr.Upper(programCode));
        }

        var resolved = PyStr.Upper(string.IsNullOrEmpty(state) ? DeriveRunState(clientId, taxYear) : state);
        var candidates = CalculableProgramsForState(resolved, taxYear);
        if (candidates.Count > 1 && requireProgram)
        {
            throw new ProgramChoiceRequired(resolved, candidates);
        }

        // Why: with several candidates and no program named, Python logs a deprecation and takes the first in registry order.
        return (resolved, candidates.Count > 0 ? candidates[0] : ProgramCodeForState(resolved));
    }

    /// <summary>Python <c>rows_of_program</c>: Gold rows belonging to a program; rows that carry none, and an absent code, pass through. [F04c.3]</summary>
    /// <param name="rows">The rows.</param>
    /// <param name="programCode">The program.</param>
    /// <returns>The matching rows.</returns>
    public static IReadOnlyList<PyDict> RowsOfProgram(IEnumerable<PyDict> rows, string? programCode) =>
        rows.Where(r => string.IsNullOrEmpty(programCode) || !r.TryGetValue("program_code", out var v) || v is null || (v is string s && s == programCode)).ToList();

    /// <summary>Python <c>location_state</c>: the program's own state when one is named, else <see cref="StateForLocation"/>.</summary>
    /// <param name="clientId">The client.</param>
    /// <param name="worksiteId">The location.</param>
    /// <param name="state">The caller's state.</param>
    /// <param name="programCode">The program.</param>
    /// <returns>The state.</returns>
    public string LocationState(long? clientId, string worksiteId, string? state, string? programCode) =>
        !string.IsNullOrEmpty(programCode) ? ProgramState(programCode) : StateForLocation(clientId, worksiteId, null, state);

    /// <summary>Python <c>programs_to_price</c>: the default program ALWAYS plus every other program of the state with an authored year. [F04c.6]</summary>
    /// <param name="state">The state.</param>
    /// <returns>The codes.</returns>
    public IReadOnlyList<string> ProgramsToPrice(string state) =>
        library.ProgramsForState(state).Where((e, i) => i == 0 || library.AuthoredYears(e.PackFile).Count > 0).Select(e => e.Code).ToList();

    /// <summary>Python <c>state_programs</c>: <c>(state, program code)</c> for every registry state and each program a sweep prices there, states sorted.</summary>
    /// <returns>The pairs.</returns>
    public IReadOnlyList<(string State, string Code)> StatePrograms() =>
        library.StateToPack.SortedKeys().SelectMany(state => ProgramsToPrice(state).Select(code => (state, code))).ToList();

    /// <summary>Python <c>priced_program</c>: <c>(state, program code, pack file)</c> a what-if prices; a state with several programs asks which.</summary>
    /// <param name="clientId">The client.</param>
    /// <param name="state">The state.</param>
    /// <param name="programCode">The program.</param>
    /// <param name="taxYear">The year.</param>
    /// <returns>The triple.</returns>
    /// <exception cref="ProgramNotRunnable">When no pack is registered.</exception>
    public (string State, string Code, string PackFile) PricedProgram(long? clientId, string? state, string? programCode, long? taxYear)
    {
        var (st, code) = ResolveProgram(clientId, state, programCode, taxYear, requireProgram: true);
        var packFile = !string.IsNullOrEmpty(code) ? library.PackFileFor(code) : null;
        return packFile is null ? throw new ProgramNotRunnable($"No rule pack for state {st}") : (st, code!, packFile);
    }

    /// <summary>Python <c>run_state</c>: the program's own state when one is named, else <see cref="DeriveRunState"/>. [F04c.6]</summary>
    /// <param name="clientId">The client.</param>
    /// <param name="taxYear">The year.</param>
    /// <param name="state">The caller's state.</param>
    /// <param name="programCode">The program.</param>
    /// <returns>The state.</returns>
    public string RunState(long? clientId, long? taxYear, string? state, string? programCode) =>
        !string.IsNullOrEmpty(programCode) ? ProgramState(programCode) : DeriveRunState(clientId, taxYear, state);

    /// <summary>Python <c>program_code_for_state</c>: the code of the state's DEFAULT program (the first in registry order), or <c>null</c>.</summary>
    /// <param name="state">The state.</param>
    /// <returns>The code or <c>null</c>.</returns>
    public string? ProgramCodeForState(string state)
    {
        var entries = library.ProgramsForState(state);
        return entries.Count > 0 ? entries[0].Code : null;
    }

    // Python catches Exception around the footprint read: an unreadable footprint means "cannot tell".
    private IReadOnlyList<string> Footprint(long? clientId)
    {
        try
        {
            return payrollStates(clientId);
        }
        catch (Exception e) when (e is not OutOfMemoryException)
        {
            return [];
        }
    }
}
