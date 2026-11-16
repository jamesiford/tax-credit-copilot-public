using System.Text.Json;
using TaxCredit.Application.Ports.Contract;
using TaxCredit.Application.Ports.Persistence;
using TaxCredit.Application.Ports.Sources;
using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Pipeline;
using static TaxCredit.Application.Features.ReadsCalc.ReadValues;

namespace TaxCredit.Application.Features.ReadsCalc.Ingestion;

/// <summary>Ingestion annotations are versioned lookup decisions, not the Claims finding lifecycle or a private global dictionary.</summary>
public sealed class QcAnnotations(ILookupStore store, IClock clock, IClientPayrollSource source)
{
    private const string Lookup = "qc_exception_annotation";

    /// <summary>A fresh certified resolution input is hydrated for one tenant on every calculation read.</summary>
    public QcResolutionStore Resolutions(long? client = null)
    {
        var result = new QcResolutionStore();
        foreach (var entry in store.Entries(Lookup, Tenant(client)))
        {
            if (PyJson.Loads(entry.ValueJson) is not PyDict decision)
            {
                throw new InvalidDataException("A persisted QC annotation is not an object.");
            }
            result.Set(entry.Key, decision);
        }
        return result;
    }

    /// <summary>Reopening closes the lookup version while retaining its immutable action audit.</summary>
    public object Resolve(ReadArguments args, string actor)
    {
        ArgumentNullException.ThrowIfNull(args);
        var client = Tenant(args.Client());
        var id = args.Text("exception_id")!;
        var resolution = args.Text("resolution", "accept");
        var now = PyDateTime.FromIsoFormat(clock.UtcNow.UtcDateTime.ToString("yyyy-MM-ddTHH:mm:ss.ffffff", System.Globalization.CultureInfo.InvariantCulture));
        if (resolution == "reopen")
        {
            store.Remove(Lookup, client, "exception", id, actor, now);
            return Map(("ok", true), ("exception_id", id), ("resolution", null));
        }
        var entry = Map(("exception_id", id), ("resolution", resolution), ("keep_worksite", args.Text("keep_worksite")),
            ("note", args.Text("note")), ("reviewer", actor), ("resolved_at", Iso(DateOnly.FromDateTime(clock.UtcNow.UtcDateTime))));
        store.Put(new LookupEntry(Lookup, client, "exception", id, JsonSerializer.Serialize(entry), actor), now);
        return Map(("ok", true), ("exception_id", id), ("resolution", entry));
    }

    private long Tenant(long? client) => client ?? source.FixtureAccountId
        ?? throw new ReadRefusalException(422, "A client is required for a durable ingestion annotation.");
}
