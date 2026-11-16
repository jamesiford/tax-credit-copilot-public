using System.Reflection;
using TaxCredit.Application.Ports.Persistence;
using TaxCredit.Domain.Numerics;

namespace TaxCredit.Api.Tests.Ai.Capabilities;

internal sealed class ConfirmationMemory
{
    private readonly Lock _lock = new();
    internal List<Confirmation> Rows { get; } = [];

    internal object? Call(MethodInfo method, object?[]? args)
    {
        lock (_lock)
        {
            return method.Name switch
            {
                "Create" => Create((Confirmation)args![0]!),
                "FindByTokenHash" => Rows.FirstOrDefault(row => row.TokenSha256 == (string)args![0]!),
                "FindByIdempotencyKey" => Rows.FirstOrDefault(row => row.UserOid == (string)args![0]! && row.IdempotencyKey == (string)args[1]!),
                "Consume" => Consume((string)args![0]!, (string)args[1]!, (string)args[2]!, (PyDateTime)args[3]!, (string?)args[4]),
                "RecordResult" => Record((string)args![0]!, (string)args[1]!, (string?)args[2]),
                _ => throw new NotSupportedException(method.Name),
            };
        }
    }

    private Confirmation Create(Confirmation row)
    {
        Rows.Add(row);
        return row;
    }

    private bool Consume(string id, string user, string hash, PyDateTime now, string? key)
    {
        var index = Rows.FindIndex(row => row.ConfirmationId == id && row.UserOid == user && row.ArgsSha256 == hash &&
            row.ConsumedAt is null && DateTimeOffset.Parse(row.ExpiresAt.IsoFormat(), System.Globalization.CultureInfo.InvariantCulture) >
                DateTimeOffset.Parse(now.IsoFormat(), System.Globalization.CultureInfo.InvariantCulture));
        if (index < 0 || Rows.Any(row => row.UserOid == user && row.IdempotencyKey == key))
        {
            return false;
        }
        Rows[index] = Rows[index] with { ConsumedAt = now, IdempotencyKey = key };
        return true;
    }

    private object? Record(string id, string outcome, string? json)
    {
        var index = Rows.FindIndex(row => row.ConfirmationId == id);
        Rows[index] = Rows[index] with { Outcome = outcome, ResultJson = json };
        return null;
    }
}
