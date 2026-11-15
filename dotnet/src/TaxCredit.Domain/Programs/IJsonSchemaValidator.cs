namespace TaxCredit.Domain.Programs;

/// <summary>
/// One structural violation found by a JSON Schema validator, as plain data (Python <c>jsonschema.ValidationError</c> reduced to the three
/// things <c>pack_validation.check_schema</c> reads).
/// </summary>
/// <param name="Path">
/// The absolute path of the offending value inside the pack: object keys as <c>string</c>, array positions as <c>long</c>. A path is a
/// list because <c>"0"</c> as a key and <c>0</c> as an index are different places.
/// </param>
/// <param name="Message">The validator's own wording. Python's <c>jsonschema</c> and the .NET validator word the same violation differently; see <c>docs/pack-validation-deviations.md</c>.</param>
/// <param name="Keyword">The schema keyword that failed (<c>required</c>, <c>type</c>, <c>enum</c>, ...); <c>null</c> when a <c>false</c> schema rejected the value.</param>
public sealed record SchemaFinding(IReadOnlyList<object> Path, string Message, string? Keyword);

/// <summary>
/// The JSON Schema step of pack validation (Python <c>jsonschema.Draft202012Validator</c> over <c>rules/schema/rule-pack.schema.json</c>).
/// </summary>
/// <remarks>
/// Why a port declared in the Domain: the Domain does no I/O and takes no package, and a JSON Schema engine is both (it reads the schema file and
/// is a library). The semantic rules that decide what the findings mean stay in <see cref="PackValidator"/>; the implementation lives in
/// <c>TaxCredit.Infrastructure.Rules</c>. [ADR-013]
/// </remarks>
public interface IJsonSchemaValidator
{
    /// <summary>Python <c>pack_validation.schema_version()</c>: the <c>schema_version</c> member of the schema document.</summary>
    int SchemaVersion { get; }

    /// <summary>Python <c>iter_errors</c> over the base-pack or year-pack sub-schema, in the order the validator reports them (the caller sorts).</summary>
    /// <param name="instance">The pack: a tree of <c>null</c>, bool, long, <see cref="System.Numerics.BigInteger"/>, double, string, <c>List&lt;object?&gt;</c> and <see cref="Numerics.PyDict"/>.</param>
    /// <param name="kind"><c>year</c> validates a year pack; any other value validates a base pack, as in Python.</param>
    /// <returns>Every violation; empty when the instance is valid.</returns>
    IReadOnlyList<SchemaFinding> Validate(object? instance, string kind);
}
