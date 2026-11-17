using TaxCredit.Domain.Numerics;

namespace TaxCredit.Domain.Programs;

/// <summary>
/// The read side of a rules folder: the program registry manifest, the flat rule packs and the year packs under
/// <c>rules/&lt;program&gt;/&lt;year&gt;.json</c> (the folder Python reads through <c>RULES_DIR</c>). [ADR-005, ADR-013]
/// </summary>
/// <remarks>
/// Why a port declared in the Domain: the tools it replaces (<c>tools/credit_math.py</c>, <c>tools/program_registry.py</c>)
/// resolve statute by reading files, and the pure resolution rules (strict year resolution, defaults, error text) must stay in
/// the domain where they can be replayed against Python. The Domain does no I/O, so the read is behind this interface;
/// <c>TaxCredit.Infrastructure.JsonRulePackSource</c> implements it over <c>backend/rules</c> (never a copy), and
/// <c>TaxCredit.Application</c> owns the wiring. Every path is relative to the rules folder and uses <c>/</c>.
/// </remarks>
public interface IRulePackSource
{
    /// <summary>The rules folder as it is shown in messages (Python <c>str(rules_dir)</c>).</summary>
    string RulesDirectory { get; }

    /// <summary>The registry manifest file as it is shown in messages (Python <c>str(registry_file)</c>).</summary>
    string RegistryFile { get; }

    /// <summary>Python <c>(rules_dir / path).exists()</c>.</summary>
    /// <param name="relativePath">Path relative to the rules folder.</param>
    /// <returns>Whether a file or folder is there.</returns>
    bool Exists(string relativePath);

    /// <summary>Python <c>(rules_dir / path).is_file()</c>.</summary>
    /// <param name="relativePath">Path relative to the rules folder.</param>
    /// <returns>Whether a file is there.</returns>
    bool IsFile(string relativePath);

    /// <summary>Python <c>(rules_dir / path).is_dir()</c>; the empty path is the rules folder itself.</summary>
    /// <param name="relativePath">Path relative to the rules folder.</param>
    /// <returns>Whether a folder is there.</returns>
    bool IsDirectory(string relativePath);

    /// <summary>Python <c>(rules_dir / path).read_text(encoding="utf-8")</c>: UTF-8 with universal newlines, a byte-order mark kept.</summary>
    /// <param name="relativePath">Path relative to the rules folder.</param>
    /// <returns>The text.</returns>
    string ReadText(string relativePath);

    /// <summary>The stems of <c>(rules_dir / folder).glob("*.json")</c>, in any order (callers sort).</summary>
    /// <param name="relativeFolder">Folder relative to the rules folder; empty is the rules folder.</param>
    /// <returns>File names without their final suffix.</returns>
    IReadOnlyList<string> ListJsonStems(string relativeFolder);

    /// <summary>The manifest's modification stamp (Python <c>st_mtime_ns</c>), or <c>null</c> when the manifest does not exist.</summary>
    /// <returns>The stamp.</returns>
    long? RegistryStamp();

    /// <summary>The manifest text (Python <c>registry_file.read_text(encoding="utf-8")</c>).</summary>
    /// <returns>The text.</returns>
    string ReadRegistryText();
}

/// <summary>
/// The optional ingestion hook of <c>load_pack_one_zero</c> (Python <c>rules_ingestion.ingested_one_zero</c>): a cited config that may
/// FILL a value a pack lacks but never OVERRIDE a year-resolved one. [ADR-005] Absent, the hook is "none".
/// </summary>
public interface IIngestedOneZeroSource
{
    /// <summary>The flat <c>one_zero</c> shape the engine reads, or <c>null</c> when nothing is ingested for the key.</summary>
    /// <param name="programOrState">The upper-cased state or program code.</param>
    /// <param name="taxYear">The tax year, if any.</param>
    /// <returns>The ingested values (<c>min_weekly_hours</c>, <c>min_weekly_wages</c>, <c>wage_basis</c>, ...) or <c>null</c>.</returns>
    PyDict? IngestedOneZero(string programOrState, long? taxYear);
}

/// <summary>Reads the captured ingestion configs (<c>backend/data/rules_ingested/&lt;file&gt;</c>); the only I/O behind <see cref="CapturedIngestion"/>.</summary>
public interface IIngestedConfigFiles
{
    /// <summary>Python <c>path.read_text(encoding="utf-8")</c> for a file in the ingested-config folder, or <c>null</c> when it does not exist.</summary>
    /// <param name="fileName">The file name, for example <c>ga_jtc.json</c>.</param>
    /// <returns>The text or <c>null</c>.</returns>
    string? ReadText(string fileName);
}

/// <summary>
/// The payroll lookup behind a percentage-of-wages benefit (Python <c>tools/program_credit.avg_program_wage</c>, which reads
/// <c>data/payroll.csv</c>): the average annual wage of the payroll rows in the program's state.
/// </summary>
/// <remarks>Declared here, implemented by the payroll slice; a library built without one refuses a percentage-of-wages program.</remarks>
public interface IProgramWageSource
{
    /// <summary>Average annual wage of the payroll rows of the program's state, <c>0.0</c> when there are none.</summary>
    /// <param name="programOrState">The upper-cased program code or state exactly as the credit tools were given it.</param>
    /// <returns>The average wage.</returns>
    double AverageProgramWage(string programOrState);
}
