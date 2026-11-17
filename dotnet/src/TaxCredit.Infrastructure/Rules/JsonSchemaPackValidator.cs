using System.Numerics;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using Json.Schema;
using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Programs;

namespace TaxCredit.Infrastructure.Rules;

/// <summary>
/// <see cref="IJsonSchemaValidator"/> over <c>JsonSchema.Net</c> 8.0.5 (MIT; Draft 2020-12): the adapter that checks a pack against the SAME
/// <c>rules/schema/rule-pack.schema.json</c> Python's <c>jsonschema</c> reads.
/// </summary>
/// <remarks>
/// <para>The library and Python's <c>jsonschema</c> agree on whether a document is valid; they do NOT word, count or order the violations alike, and this adapter
/// closes only the gaps that can be closed exactly (see <c>docs/pack-validation-deviations.md</c>, which is generated from the golden):</para>
/// <list type="bullet">
/// <item><description><c>oneOf</c>: the library reports the failing BRANCHES (and reports a branch that failed inside a <c>oneOf</c> that passed), and reports
/// nothing at all when several branches match. Python reports one <c>oneOf</c> violation at the object. The adapter groups the branch results, drops the noise of a passing
/// <c>oneOf</c> and reports one <c>oneOf</c> finding for a failing one (its message is the adapter's, not Python's).</description></item>
/// <item><description><c>propertyNames</c>: the library puts the property name on the instance location; Python reports the object. The adapter removes the last segment.</description></item>
/// <item><description>A <c>false</c> schema has no keyword (Python <c>validator is None</c>) and, because <c>jsonschema</c> yields that error without the path of the property it rejected, Python reports it at the OBJECT; the adapter reports <c>null</c> at the object too.</description></item>
/// <item><description><c>minLength</c>: the library counts text elements, Python counts code points (<c>len()</c>); the adapter drops a <c>minLength</c> finding the code points satisfy.</description></item>
/// <item><description>Regular expressions: the library runs patterns in .NET ECMAScript mode, where <c>\s</c> is ASCII-only; Python's <c>re</c> reads <c>\s</c> as <c>str.isspace()</c> (U+001C..U+001F, U+0085, U+00A0 and the Unicode spaces too). The adapter translates <c>\s</c> and <c>\S</c> in the schema's patterns (<see cref="PatternDialect"/>).</description></item>
/// <item><description>Array indices and object keys share the pointer syntax; the adapter resolves each segment against the instance to say which it is.</description></item>
/// </list>
/// <para>Everything else (message wording; <c>required</c> reported once for all missing names where Python reports one violation per name; ties at one path) is left as the library
/// reports it and measured by the parity test.</para>
/// </remarks>
public sealed class JsonSchemaPackValidator : IJsonSchemaValidator
{
    private readonly JsonSchema _year;
    private readonly JsonSchema _base;
    private readonly JsonNode _schemaRoot;

    /// <summary>Initialises the validator from the text of the schema file.</summary>
    /// <param name="schemaText">The contents of <c>rule-pack.schema.json</c>.</param>
    public JsonSchemaPackValidator(string schemaText)
    {
        ArgumentNullException.ThrowIfNull(schemaText);
        var root = JsonNode.Parse(schemaText)!.AsObject();
        SchemaVersion = (int)root["schema_version"]!.GetValue<long>();
        _schemaRoot = JsonNode.Parse(schemaText)!;
        PatternDialect.Translate(_schemaRoot);
        _year = Compile(root, "#/$defs/year_pack");
        _base = Compile(root, "#/$defs/base_pack");
    }

    /// <inheritdoc />
    public int SchemaVersion { get; }

    /// <summary>Reads the schema file named by <paramref name="options"/> (default: <c>schema/rule-pack.schema.json</c> inside the rules folder).</summary>
    /// <param name="options">Where the rules folder is.</param>
    /// <returns>The validator.</returns>
    public static JsonSchemaPackValidator FromOptions(RulePackOptions options)
    {
        ArgumentNullException.ThrowIfNull(options);
        var file = options.SchemaFile is { Length: > 0 } custom ? custom : Path.Combine(options.RulesDirectory, "schema", "rule-pack.schema.json");
        return new JsonSchemaPackValidator(File.ReadAllText(file, Encoding.UTF8));
    }

    /// <inheritdoc />
    public IReadOnlyList<SchemaFinding> Validate(object? instance, string kind)
    {
        ArgumentNullException.ThrowIfNull(kind);
        using var document = JsonDocument.Parse(TreeJson.Write(instance));
        var result = (kind == "year" ? _year : _base).Evaluate(document.RootElement, new EvaluationOptions { OutputFormat = OutputFormat.List });
        return result.IsValid ? [] : SchemaResultReader.Read(result, document.RootElement, _schemaRoot);
    }

    // Python builds `{**schema, "$ref": ...}`: the document with its root reference replaced by the sub-schema for the kind.
    private static JsonSchema Compile(JsonObject root, string reference)
    {
        var copy = JsonNode.Parse(root.ToJsonString())!.AsObject();
        PatternDialect.Translate(copy);
        copy.Remove("$ref");
        copy["$ref"] = reference;
        return JsonSchema.FromText(copy.ToJsonString(), new BuildOptions { SchemaRegistry = new SchemaRegistry() });
    }
}

/// <summary>Writes a pack tree (the Python JSON model) as JSON text for the schema library.</summary>
internal static class TreeJson
{
    internal static byte[] Write(object? tree)
    {
        using var stream = new MemoryStream();
        using (var writer = new Utf8JsonWriter(stream))
        {
            WriteValue(writer, tree);
        }

        return stream.ToArray();
    }

    private static void WriteValue(Utf8JsonWriter w, object? value)
    {
        switch (value)
        {
            case null:
                w.WriteNullValue();
                break;
            case bool b:
                w.WriteBooleanValue(b);
                break;
            case long l:
                w.WriteNumberValue(l);
                break;
            case BigInteger big:
                w.WriteRawValue(big.ToString(System.Globalization.CultureInfo.InvariantCulture));
                break;
            case double d when double.IsFinite(d):
                w.WriteNumberValue(d);
                break;
            case double:
                throw new PyUnsupportedException("NaN and Infinity are not JSON numbers for the schema library; Python's json module accepts them (not modelled)");
            case string s:
                w.WriteStringValue(s);
                break;
            case PyDict dict:
                w.WriteStartObject();
                foreach (var kv in dict)
                {
                    w.WritePropertyName(kv.Key);
                    WriteValue(w, kv.Value);
                }

                w.WriteEndObject();
                break;
            case List<object?> list:
                w.WriteStartArray();
                foreach (var item in list)
                {
                    WriteValue(w, item);
                }

                w.WriteEndArray();
                break;
            default:
                throw new PyUnsupportedException("not a JSON value: " + value.GetType().Name);
        }
    }
}
