using System.Text.RegularExpressions;

namespace TaxCredit.Infrastructure.Persistence.Sql;

/// <summary>A refused statement never reaches the provider.</summary>
public sealed class TenantScopeViolation(string message) : InvalidOperationException(message);

/// <summary>SQL and positional values after injecting the selected tenant.</summary>
public sealed record BoundStatement(string Sql, IReadOnlyList<object?> Values);

/// <summary>Binds only leading WHERE/ON predicates and a configured closed source-column set.</summary>
public sealed partial class TenantBinding
{
    private readonly HashSet<string> _columns;

    /// <summary>Creates a scope; source column names come from configuration, not a request.</summary>
    public TenantBinding(long clientId, IEnumerable<string>? sourceColumns = null)
    {
        ArgumentOutOfRangeException.ThrowIfNegative(clientId);
        ClientId = clientId;
        _columns = new HashSet<string>(sourceColumns ?? [], StringComparer.Ordinal) { "client_id" };
        if (_columns.Any(c => !Identifier().IsMatch(c)))
        {
            throw new TenantScopeViolation("Invalid configured tenant column.");
        }
    }

    /// <summary>The selected tenant, with zero reserved for explicitly global lookups.</summary>
    public long ClientId { get; }

    /// <summary>Preserves parameter order, including parameters appearing before a marker.</summary>
    public BoundStatement Bind(string sql, IReadOnlyList<object?>? parameters = null)
    {
        ArgumentNullException.ThrowIfNull(sql);
        var mask = SqlLex.Mask(sql);
        var markers = Marker().Matches(mask);
        if (markers.Count == 0 || mask.Count(c => c == '?') != (parameters?.Count ?? 0))
        {
            throw new TenantScopeViolation("Missing tenant marker or incorrect parameter count.");
        }

        var values = new List<object?>();
        var output = new System.Text.StringBuilder();
        var cursor = 0;
        var consumed = 0;
        foreach (Match marker in markers)
        {
            if (!Anchor().IsMatch(mask[..marker.Index]))
            {
                throw new TenantScopeViolation("Tenant must be the first WHERE or ON term.");
            }

            var column = marker.Groups[2].Success ? marker.Groups[2].Value : "client_id";
            if (!_columns.Contains(column))
            {
                throw new TenantScopeViolation("Unknown tenant column.");
            }

            var count = mask[cursor..marker.Index].Count(c => c == '?');
            for (var i = 0; i < count; i++)
            {
                values.Add(parameters![consumed++]);
            }

            output.Append(sql[cursor..marker.Index]);
            if (marker.Groups[1].Success)
            {
                output.Append(marker.Groups[1].Value).Append('.');
            }

            output.Append(column).Append(" = ?");
            values.Add(ClientId);
            cursor = marker.Index + marker.Length;
        }

        output.Append(sql[cursor..]);
        while (consumed < (parameters?.Count ?? 0))
        {
            values.Add(parameters![consumed++]);
        }

        return new BoundStatement(output.ToString(), values);
    }

    /// <summary>Validates the entire batch before constructing any command.</summary>
    public void CheckInsert(IReadOnlyList<string> columns, IReadOnlyList<IReadOnlyList<object?>> rows)
    {
        ArgumentNullException.ThrowIfNull(columns);
        ArgumentNullException.ThrowIfNull(rows);
        var position = columns.ToList().IndexOf("client_id");
        if (position < 0 || columns.Any(c => !Identifier().IsMatch(c)))
        {
            throw new TenantScopeViolation("Insert requires a client_id column and fixed identifiers.");
        }

        foreach (var row in rows)
        {
            if (row.Count != columns.Count || row[position] is not long id || id != ClientId)
            {
                throw new TenantScopeViolation("Insert row does not belong to this tenant.");
            }
        }
    }

    [GeneratedRegex(@"\{tenant(?::([A-Za-z_][A-Za-z0-9_]*))?(?:@([A-Za-z_][A-Za-z0-9_]*))?\}")]
    private static partial Regex Marker();

    [GeneratedRegex(@"\b(?:WHERE|ON)\s+$", RegexOptions.IgnoreCase)]
    private static partial Regex Anchor();

    [GeneratedRegex(@"^[A-Za-z_][A-Za-z0-9_]*$")]
    internal static partial Regex Identifier();
}
