using System.Data.Common;
using System.Globalization;
using System.Text.RegularExpressions;
using Microsoft.Data.SqlClient;
using Microsoft.Data.Sqlite;
using TaxCredit.Application.Ports.Persistence;
using TaxCredit.Domain.Numerics;
using TaxCredit.Infrastructure.Persistence.Sql;

namespace TaxCredit.Infrastructure.Persistence.GoldRead;

/// <summary>A typed refusal, never a partial query result or an exposed SQL/provider error.</summary>
public sealed class GoldQueryException : InvalidOperationException
{
    /// <summary>Creates a stable error code and safe explanation.</summary>
    public GoldQueryException(string code, string message, Exception? innerException = null) : base(message, innerException) => Code = code;
    /// <summary>The stable refusal category.</summary>
    public string Code { get; }
}

/// <summary>Structured questions over a closed Gold catalogue; every dataset and column comes from reviewed code.</summary>
public sealed partial class GoldDataQuery : IGoldDataQueryPort
{
    private readonly PersistenceDatabase _database;
    private readonly Func<long, bool> _employeeAccess;
    private readonly int _timeoutSeconds;

    /// <summary>Raw employee rows require a trusted first-party authorization callback; default is refusal.</summary>
    public GoldDataQuery(PersistenceDatabase database, Func<long, bool>? employeeAccess = null, int timeoutSeconds = 20)
    {
        ArgumentNullException.ThrowIfNull(database);
        ArgumentOutOfRangeException.ThrowIfLessThan(timeoutSeconds, 1);
        ArgumentOutOfRangeException.ThrowIfGreaterThan(timeoutSeconds, 600);
        _database = database;
        _employeeAccess = employeeAccess ?? (_ => false);
        _timeoutSeconds = timeoutSeconds;
    }

    /// <inheritdoc />
    public IReadOnlyList<GoldQueryDataset> Catalog() => GoldQueryCatalog.Datasets;

    /// <inheritdoc />
    public GoldQueryResult Run(GoldQuerySpec specification, CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(specification);
        var dataset = Catalog().FirstOrDefault(d => d.Name == specification.Dataset)
            ?? throw Refuse("unknown_dataset", "No such dataset; read the catalogue for its names.");
        ValidateShape(specification, dataset);
        var plan = Build(specification, dataset);
        var employee = plan.Columns.Any(c => c.Sensitivity == "employee_level") || (dataset.EmployeeLevel && specification.Measures.Count == 0);
        if (employee && !_employeeAccess(specification.ClientId))
        {
            throw Refuse("employee_level_not_allowed", "Employee-level results require an entitled first-party channel and must never be sent to a model.");
        }
        var rows = Execute(specification.ClientId, plan, specification.Limit + 1, cancellationToken);
        var kept = rows.Take(specification.Limit).Select(row => Shape(row, plan.Columns)).ToArray();
        return new GoldQueryResult(plan.Columns.Select(c => c.Name).ToArray(), kept, rows.Count > specification.Limit, employee);
    }

    private IReadOnlyList<IReadOnlyDictionary<string, object?>> Execute(long clientId, Built plan, int maximumRows, CancellationToken cancellationToken)
    {
        try
        {
            using var session = _database.Open();
            return session.QueryBounded(clientId, plan.Sql, maximumRows, _timeoutSeconds, cancellationToken, plan.Values);
        }
        catch (OperationCanceledException error)
        {
            var cancelled = cancellationToken.IsCancellationRequested;
            throw new GoldQueryException(cancelled ? "query_cancelled" : "query_timeout",
                cancelled ? "The query was cancelled." : "The query exceeded its time limit and was cancelled.", error);
        }
        catch (TimeoutException error)
        {
            throw new GoldQueryException("query_timeout", "The query exceeded its time limit and was cancelled.", error);
        }
        catch (DbException error)
        {
            if (cancellationToken.IsCancellationRequested)
            {
                throw new GoldQueryException("query_cancelled", "The query was cancelled.", error);
            }
            var timeout = error is SqlException { Number: -2 } or SqliteException { SqliteErrorCode: 9 };
            throw new GoldQueryException(timeout ? "query_timeout" : "query_failed",
                timeout ? "The query exceeded its time limit and was cancelled." : "The data source could not run the query.", error);
        }
    }

    /// <inheritdoc />
    public GoldQueryResult DistinctValues(long clientId, string dataset, string column, IReadOnlyList<int>? taxYears = null, int limit = 50, CancellationToken cancellationToken = default)
    {
        if (limit is < 1 or > 100)
        {
            throw Refuse("malformed_spec", "Distinct-value limit must be between 1 and 100.");
        }
        var model = Catalog().FirstOrDefault(d => d.Name == dataset) ?? throw Refuse("unknown_dataset", "Unknown dataset.");
        var category = Resolve(model, column);
        if (category.Sensitivity != "public_aggregate" || category.Role is not "dimension" and not "flag")
        {
            throw Refuse("column_not_listable", "Only public category columns can be listed.");
        }
        var result = Run(new GoldQuerySpec
        {
            Dataset = dataset,
            ClientId = clientId,
            TaxYears = taxYears ?? [],
            Select = [column],
            GroupBy = [column],
            Measures = [new("*", "count", "row_count")],
            OrderBy = [new(column)],
            Limit = Math.Min(500, limit * 2),
        }, cancellationToken);
        var values = result.Rows.GroupBy(r => r[column]).Select(g => (IReadOnlyDictionary<string, object?>)new Dictionary<string, object?>
        {
            ["value"] = g.Key,
            ["row_count"] = g.Sum(r => Convert.ToInt64(r["row_count"], CultureInfo.InvariantCulture)),
        }).ToArray();
        return new GoldQueryResult(["value", "row_count"], values.Take(limit).ToArray(), result.Truncated || values.Length > limit, false);
    }

    private static void ValidateShape(GoldQuerySpec spec, GoldQueryDataset dataset)
    {
        if (spec.Select is null || spec.Measures is null || spec.Filters is null || spec.GroupBy is null || spec.OrderBy is null || spec.TaxYears is null ||
            spec.Measures.Any(m => m is null) || spec.Filters.Any(f => f is null) || spec.OrderBy.Any(o => o is null))
        {
            throw Refuse("malformed_spec", "Query lists and their entries must not be null.");
        }
        if (spec.ClientId <= 0 || spec.Limit < 1 || spec.Limit > 500)
        {
            throw Refuse("malformed_spec", "A positive client and a limit between 1 and 500 are required.");
        }
        if (spec.Select.Count > 12 || spec.Measures.Count > 6 || spec.Filters.Count > 8 || spec.GroupBy.Count > 8 || spec.OrderBy.Count > 4 || spec.TaxYears.Count > 12)
        {
            throw Refuse("malformed_spec", "The specification exceeds the bounded query shape.");
        }
        if (spec.TaxYears.Any(y => y is < 2000 or > 2100))
        {
            throw Refuse("tax_year_out_of_range", "Tax years must be between 2000 and 2100.");
        }
        if (spec.Method is not null && (!dataset.HasMethod || spec.Method is not "both" and not "min_max" and not "pay_period"))
        {
            throw Refuse("method_not_applicable", "Use a supported method only on a dataset holding statutory readings.");
        }
        if (spec.Select.Count == 0 && spec.Measures.Count == 0)
        {
            throw Refuse("empty_query", "Select at least one column or measure.");
        }
    }

    private static GoldQueryColumn Resolve(GoldQueryDataset dataset, string name)
    {
        var column = dataset.Columns.FirstOrDefault(c => c.Name == name) ?? throw Refuse("unknown_column", "No such catalogue column.");
        if (column.Sensitivity == "blocked")
        {
            throw Refuse("blocked_column", "That column can never be queried.");
        }
        return column;
    }

    private static Dictionary<string, object?> Shape(IReadOnlyDictionary<string, object?> row, IReadOnlyList<GoldQueryColumn> columns) =>
        columns.ToDictionary(c => c.Name, c =>
        {
            var value = row[c.Name];
            if (value is null)
            {
                return null;
            }
            return c.Unit == "USD" ? value is double number ? PyFloat.Repr(number) : Convert.ToString(value, CultureInfo.InvariantCulture) :
                c.Type == "decimal" ? Convert.ToDouble(value, CultureInfo.InvariantCulture) :
                c.Type == "int" ? (object)Convert.ToInt64(value, CultureInfo.InvariantCulture) :
                c.Type == "bool" ? Convert.ToInt32(value, CultureInfo.InvariantCulture) != 0 : value;
        }, StringComparer.Ordinal);

    private static GoldQueryException Refuse(string code, string message) => new(code, message);
    [GeneratedRegex(@"\A[A-Za-z_][A-Za-z0-9_]{0,63}\z", RegexOptions.CultureInvariant)]
    private static partial Regex Identifier();
}
