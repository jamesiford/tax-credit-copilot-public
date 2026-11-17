using System.Globalization;
using System.Numerics;
using TaxCredit.Domain.Calculation;
using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Pipeline;

namespace TaxCredit.Application.Features.ReadsCalc.Portfolio;

internal static class PortfolioValues
{
    internal static object? Get(PyDict row, string key) => row.TryGetValue(key, out var value) ? value : null;
    internal static double Number(PyDict row, string key) => Number(Get(row, key));
    internal static double Number(object? value) => value switch
    {
        null => 0.0,
        BigInteger number => (double)number,
        PyNumber number => number.IsInt ? number.IntValue : number.FloatValue,
        PyDecimal number => number.ToDouble(),
        _ => System.Convert.ToDouble(value, CultureInfo.InvariantCulture),
    };
    internal static string Text(PyDict row, string key) => Get(row, key) as string ?? "";
    internal static PyDict Dict(PyDict row, string key) => Get(row, key) as PyDict ?? new PyDict();
    internal static string Iso(DateOnly value) => value.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture);
    internal static string Display(double value) => PyFloat.Repr(value);
    internal static string DisplayValue(object? value) => value switch
    {
        null => "",
        PyDateTime instant => instant.IsoFormat(),
        _ => System.Convert.ToString(value, CultureInfo.InvariantCulture) ?? "",
    };
    internal static List<object?> List<T>(IEnumerable<T> values) => values.Select(v => (object?)v).ToList();
    internal static PyDict Tree(IReadOnlyDictionary<string, object?> row) =>
        row.Aggregate(new PyDict(), (result, pair) => result.Add(pair.Key, Convert(pair.Value)));

    internal static BigInteger Integer(object? value) => value switch
    {
        BigInteger number => number,
        long number => number,
        int number => number,
        _ => PyRound.RoundToInteger(Number(value)),
    };

    internal static OneZeroResult Run(ClientRun run, string method)
    {
        var args = run.EngineKwargs();
        var rows = run.Rows.Select(r => r.Row).ToList();
        return method == "min_max"
            ? MinMaxMethod.Run(rows, args.TaxYear, args.AnalysisStartMonth, args.Pack, fiscalWindow: args.FiscalWindow)
            : PayPeriodMethod.Run(rows, args.TaxYear, args.AnalysisStartMonth, args.Pack, fiscalWindow: args.FiscalWindow);
    }

    internal static void ValidateMethod(string method)
    {
        if (method is not ("min_max" or "pay_period"))
        {
            throw new ArgumentException("method must be min_max or pay_period", nameof(method));
        }
    }

    private static object? Convert(object? value) => value switch
    {
        IReadOnlyDictionary<string, object?> row => Tree(row),
        IEnumerable<IReadOnlyDictionary<string, object?>> rows => List(rows.Select(Tree)),
        _ => value,
    };
}
