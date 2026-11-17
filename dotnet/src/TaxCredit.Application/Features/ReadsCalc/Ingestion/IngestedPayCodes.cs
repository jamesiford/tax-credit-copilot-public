using TaxCredit.Domain.Canonical;
using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Programs;

namespace TaxCredit.Application.Features.ReadsCalc.Ingestion;

/// <summary>Exposes captured wage classifications to the canonical tool through its declared port, with no web retrieval.</summary>
public sealed class IngestedPayCodes(IIngestedConfigFiles files) : IIngestedConfigSource
{
    /// <inheritdoc />
    public object? Load(string program)
    {
        var file = program.ToUpperInvariant() switch
        {
            "GA" or "GA_JTC" => "ga_jtc.json",
            "TN" or "TN_JTC" => "tn_jtc.json",
            _ => null,
        };
        var text = file is null ? null : files.ReadText(file);
        return text is null ? null : PyJson.Loads(text) as PyDict
            ?? throw new InvalidDataException("A captured wage classification is not an object.");
    }
}
