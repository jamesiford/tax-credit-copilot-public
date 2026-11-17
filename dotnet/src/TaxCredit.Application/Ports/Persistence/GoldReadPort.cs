namespace TaxCredit.Application.Ports.Persistence;

/// <summary>Narrowing of a unit's independent counted and near-miss cohorts.</summary>
public sealed record UnitDrillOptions
{
    /// <summary>One-based measuring month, or all months.</summary>
    public int? Month { get; init; }
    /// <summary>Whitelisted ordering column.</summary>
    public string? Sort { get; init; }
    /// <summary>Ascending only when explicitly requested.</summary>
    public string? Order { get; init; }
    /// <summary>Absolute lower hours bound for the near cohort.</summary>
    public double? NearMinHours { get; init; }
    /// <summary>Optional row cap.</summary>
    public int? Limit { get; init; }
    /// <summary>Counted-cohort grid grammar.</summary>
    public string? EmployeeFilters { get; init; }
    /// <summary>Near-cohort grid grammar.</summary>
    public string? NearFilters { get; init; }
    /// <summary>Program whose live run should answer.</summary>
    public string? ProgramCode { get; init; }
}

/// <summary>Eligibility paging does not narrow the population summary.</summary>
public sealed record EligibilityOptions
{
    /// <summary>Fraction below either statutory floor considered near.</summary>
    public double Band { get; init; } = 0.05;
    /// <summary>Both, either method only, neither, or all.</summary>
    public string Status { get; init; } = "all";
    /// <summary>Restrict to the failing side's near-floor band.</summary>
    public bool NearFloor { get; init; }
    /// <summary>Literal case-insensitive employee search.</summary>
    public string Q { get; init; } = "";
    /// <summary>Page size.</summary>
    public int Limit { get; init; } = 50;
    /// <summary>Rows skipped after ordering.</summary>
    public int Offset { get; init; }
    /// <summary>Whitelisted sort key.</summary>
    public string Sort { get; init; } = "employee_id";
    /// <summary>Ascending or descending.</summary>
    public string Order { get; init; } = "asc";
    /// <summary>Program whose live run should answer.</summary>
    public string? ProgramCode { get; init; }
}

/// <summary>Statutory floors and band applied only to displayed risk, not stored verdicts.</summary>
/// <param name="MinWeeklyHours">Resolved hours floor.</param>
/// <param name="MinWeeklyWages">Resolved wages floor.</param>
/// <param name="Band">Relative at-risk band.</param>
/// <param name="WidestBandHours">Absolute reachable-cohort band.</param>
/// <param name="ProgramCode">Program whose live run should answer.</param>
public sealed record RiskOptions(double MinWeeklyHours, double MinWeeklyWages,
    double Band = 0.10, double WidestBandHours = 5, string? ProgramCode = null);

/// <summary>A page of stored unit-year rows and its unpaged count.</summary>
/// <param name="Items">All stored columns plus month-calendar metadata.</param>
/// <param name="Total">Count before paging.</param>
public sealed record GoldRowsPage(IReadOnlyList<IReadOnlyDictionary<string, object?>> Items, int Total);

/// <summary>The read connection can be warmed without running calculation.</summary>
public interface IGoldConnection
{
    /// <summary>Checks connectivity.</summary>
    int Keepalive();
    /// <summary>Warms up to the requested number of links.</summary>
    int Prewarm(int count = 1);
}

/// <summary>The entire 25-member Gold surface. Null run and empty rows mean not calculated, never zero credit.</summary>
public interface IGoldReadPort
{
    /// <summary>The connection boundary available to startup warmup.</summary>
    IGoldConnection Connection { get; }
    /// <summary>Holds one database connection across a page's reads.</summary>
    IDisposable Scope();
    /// <summary>Latest unsuperseded successful run, independent of requested tax year.</summary>
    IReadOnlyDictionary<string, object?>? LatestRun(long clientId, string? programCode = null);
    /// <summary>A running manifest younger than the stranded-run deadline.</summary>
    IReadOnlyDictionary<string, object?>? RunInFlight(long clientId);
    /// <summary>Unit grid with months, annual credit columns and lifetime totals.</summary>
    IReadOnlyDictionary<string, object?> UnitPage(long clientId, string method, int? taxYear = null, string? programCode = null, int limit = 25, int offset = 0);
    /// <summary>Stored unit-year rows ordered before paging.</summary>
    GoldRowsPage UnitYears(long clientId, string method, int? taxYear = null, string? programCode = null, int limit = 25, int offset = 0);
    /// <summary>One stored current unit-year.</summary>
    IReadOnlyDictionary<string, object?>? Unit(long clientId, string worksiteId, int taxYear, string method, string? programCode = null);
    /// <summary>One unit's twelve stored measuring months.</summary>
    IReadOnlyDictionary<string, object?>? UnitMonths(long clientId, string worksiteId, int taxYear, string method, string runId);
    /// <summary>Month grain for all units reached by a run.</summary>
    IReadOnlyList<IReadOnlyDictionary<string, object?>> MonthSummaries(long clientId, string method, string runId, int? taxYear = null);
    /// <summary>Creation-year credit installments, without recomputing them.</summary>
    IReadOnlyList<IReadOnlyDictionary<string, object?>> Installments(long clientId, string method, string? programCode = null);
    /// <summary>Exact SQL-summed installments by unit and tax year.</summary>
    IReadOnlyList<IReadOnlyDictionary<string, object?>> CreditColumns(long clientId, string method, string? programCode = null);
    /// <summary>Exact SQL-summed annual and lifetime credit by unit.</summary>
    IReadOnlyList<IReadOnlyDictionary<string, object?>> UnitTotals(long clientId, string method, string? programCode = null);
    /// <summary>Employees actually contributing to a measuring month.</summary>
    IReadOnlyList<IReadOnlyDictionary<string, object?>> UnitEmployees(long clientId, string worksiteId, int taxYear, string method, string runId, int? month = null);
    /// <summary>Distinct ineligible people placed at a worksite by consumed pay periods.</summary>
    IReadOnlyList<IReadOnlyDictionary<string, object?>> UnitNearThreshold(long clientId, string worksiteId, int taxYear, string method, string runId);
    /// <summary>Unit drawer with independently filtered cohorts.</summary>
    IReadOnlyDictionary<string, object?> UnitDrill(long clientId, string worksiteId, int taxYear, string method, UnitDrillOptions? options = null);
    /// <summary>Monthly client headcount and recorded annual average.</summary>
    IReadOnlyDictionary<string, object?> HeadcountSeries(long clientId, int taxYear, string method, string? programCode = null);
    /// <summary>Every reached year and its recorded conclusion.</summary>
    IReadOnlyDictionary<string, object?> ClientYearSeries(long clientId, string method = "pay_period", string? programCode = null);
    /// <summary>Recorded allocation, method summary and unit/FEIN rollup.</summary>
    IReadOnlyDictionary<string, object?> OnezeroMatrix(long clientId, int taxYear, string method, string? programCode = null);
    /// <summary>Already-qualified employees near either floor and their whole-population denominator.</summary>
    IReadOnlyDictionary<string, object?> AtRisk(long clientId, int taxYear, string method, RiskOptions options);
    /// <summary>Necessary-condition-bounded averaged cohort with unbounded population counts.</summary>
    IReadOnlyDictionary<string, object?> ProximityCandidates(long clientId, int taxYear, string method, RiskOptions options);
    /// <summary>Consumed periods grouped by distinct requested record tokens.</summary>
    IReadOnlyDictionary<string, IReadOnlyList<IReadOnlyDictionary<string, object?>>> CohortPeriods(long clientId, int taxYear, string runId, IReadOnlyList<string> tokens);
    /// <summary>Both verdicts pivoted by employee, with population summary independent of filters.</summary>
    IReadOnlyDictionary<string, object?> EligibilityPopulation(long clientId, int taxYear, double minWeeklyHours, double minWeeklyWages, EligibilityOptions? options = null);
    /// <summary>Stored verdicts, allocation and consumed periods resolved by record token.</summary>
    IReadOnlyDictionary<string, object?> EmployeeDrill(long clientId, int taxYear, string recordToken, string? programCode = null);
    /// <summary>One token's eligibility rows for a named run.</summary>
    IReadOnlyList<IReadOnlyDictionary<string, object?>> Employee(string recordToken, long clientId, int taxYear, string runId);
    /// <summary>One token's unit allocations for a named run and method.</summary>
    IReadOnlyList<IReadOnlyDictionary<string, object?>> EmployeeUnits(string recordToken, long clientId, int taxYear, string runId, string method);
}

/// <summary>A named aggregate over one reviewed catalogue column, never caller SQL.</summary>
/// <param name="Column">Catalogue column, or * only for row count.</param>
/// <param name="Aggregation">count, count_distinct, sum, avg, min or max.</param>
/// <param name="Alias">Optional validated result label.</param>
public sealed record GoldQueryMeasure(string Column, string Aggregation, string? Alias = null);

/// <summary>A typed predicate over a reviewed column.</summary>
/// <param name="Column">Catalogue column.</param>
/// <param name="Operator">eq, in, between, gte, lte or contains.</param>
/// <param name="Value">Bound scalar or list of bound scalars.</param>
public sealed record GoldQueryFilter(string Column, string Operator, object? Value);

/// <summary>A result ordering, never an SQL expression.</summary>
/// <param name="Column">Selected column or aggregate label.</param>
/// <param name="Direction">asc or desc.</param>
public sealed record GoldQueryOrder(string Column, string Direction = "asc");

/// <summary>Governed Gold question. The client is explicitly scoped independently of all filter values.</summary>
public sealed record GoldQuerySpec
{
    /// <summary>Reviewed dataset name.</summary>
    public required string Dataset { get; init; }
    /// <summary>Positive client identifier whose entitlement the caller checks.</summary>
    public required long ClientId { get; init; }
    /// <summary>At most twelve statutory tax-year labels.</summary>
    public IReadOnlyList<int> TaxYears { get; init; } = [];
    /// <summary>At most twelve whitelisted projections.</summary>
    public IReadOnlyList<string> Select { get; init; } = [];
    /// <summary>At most six supported measures.</summary>
    public IReadOnlyList<GoldQueryMeasure> Measures { get; init; } = [];
    /// <summary>At most eight predicates, with every value bound.</summary>
    public IReadOnlyList<GoldQueryFilter> Filters { get; init; } = [];
    /// <summary>At most eight selected dimensions.</summary>
    public IReadOnlyList<string> GroupBy { get; init; } = [];
    /// <summary>At most four selected columns or measure aliases.</summary>
    public IReadOnlyList<GoldQueryOrder> OrderBy { get; init; } = [];
    /// <summary>Result cap, 1..500, probed with one extra row.</summary>
    public int Limit { get; init; } = 100;
    /// <summary>min_max, pay_period or both. Both always remains a result dimension.</summary>
    public string? Method { get; init; }
}

/// <summary>Catalogue column metadata with sensitivity and allowed operations.</summary>
/// <param name="Name">Logical and physical reviewed identifier.</param>
/// <param name="Type">text, decimal, int, date, datetime or bool.</param>
/// <param name="Role">dimension, measure, identifier or flag.</param>
/// <param name="Sensitivity">public_aggregate, employee_level or blocked.</param>
/// <param name="Aggregations">Allowed aggregate names.</param>
/// <param name="Operators">Allowed predicates.</param>
/// <param name="Unit">USD where the result must remain decimal text.</param>
public sealed record GoldQueryColumn(string Name, string Type, string Role, string Sensitivity,
    IReadOnlyList<string> Aggregations, IReadOnlyList<string> Operators, string? Unit = null);

/// <summary>A closed query dataset; callers never name a physical table.</summary>
/// <param name="Name">Reviewed dataset name.</param>
/// <param name="Currency">is_current, live_run or none.</param>
/// <param name="EmployeeLevel">Raw rows describe people and must not enter model context.</param>
/// <param name="HasMethod">Both readings must be kept apart.</param>
/// <param name="Columns">Reviewed columns, including explicitly blocked identifiers.</param>
public sealed record GoldQueryDataset(string Name, string Currency, bool EmployeeLevel, bool HasMethod,
    IReadOnlyList<GoldQueryColumn> Columns);

/// <summary>Capped rows plus their audience and truncation, never a silent partial result.</summary>
/// <param name="Columns">Labels in projection order.</param>
/// <param name="Rows">Kept rows only.</param>
/// <param name="Truncated">One extra probe row existed.</param>
/// <param name="EmployeeLevel">Deliver only through an entitled first-party channel, never to a model.</param>
public sealed record GoldQueryResult(IReadOnlyList<string> Columns,
    IReadOnlyList<IReadOnlyDictionary<string, object?>> Rows, bool Truncated, bool EmployeeLevel);

/// <summary>Governed Gold reads expose specifications, not an arbitrary SQL execution endpoint.</summary>
public interface IGoldDataQueryPort
{
    /// <summary>Every reviewed Gold dataset and run-manifest column, including blocked columns.</summary>
    IReadOnlyList<GoldQueryDataset> Catalog();
    /// <summary>Validates, binds one client, caps the query and labels its audience.</summary>
    GoldQueryResult Run(GoldQuerySpec specification, CancellationToken cancellationToken = default);
    /// <summary>Lists only public category values, merging counts across both methods.</summary>
    GoldQueryResult DistinctValues(long clientId, string dataset, string column, IReadOnlyList<int>? taxYears = null, int limit = 50, CancellationToken cancellationToken = default);
}
