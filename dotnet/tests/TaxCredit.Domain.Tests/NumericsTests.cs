using TaxCredit.Domain.Numerics;

namespace TaxCredit.Domain.Tests;

/// <summary>Readable spot checks of the compatibility layer; the exhaustive proof is the golden replay in the Parity tests.</summary>
public sealed class NumericsTests
{
    [Theory]
    [InlineData(2.675, 2, 2.67)]
    [InlineData(1.005, 2, 1.0)]
    [InlineData(0.125, 2, 0.12)]
    [InlineData(0.375, 2, 0.38)]
    [InlineData(2.5, 0, 2.0)]
    [InlineData(3.5, 0, 4.0)]
    public void Round_follows_python_half_even_on_the_exact_binary_value(double x, int digits, double expected) =>
        Assert.Equal(expected, PyRound.Round(x, digits));

    [Fact]
    public void Quantize_half_up_differs_from_half_even_on_a_decimal_tie()
    {
        var d = PyDecimal.FromFloatViaStr(0.125);
        Assert.Equal("0.13", d.Quantize(2, PyRoundingMode.HalfUp).ToString());
        Assert.Equal("0.12", d.Quantize(2, PyRoundingMode.HalfEven).ToString());
    }

    [Fact]
    public void Quantize_raises_invalid_operation_past_28_digits() =>
        Assert.Throws<PyInvalidOperation>(() => PyDecimal.FromFloatViaStr(1e300).Quantize(2, PyRoundingMode.HalfUp));

    [Theory]
    [InlineData(1e16, "1e+16")]
    [InlineData(1e-5, "1e-05")]
    [InlineData(100.0, "100.0")]
    [InlineData(-0.0, "-0.0")]
    [InlineData(0.1, "0.1")]
    public void Repr_uses_pythons_layout(double x, string expected) => Assert.Equal(expected, PyFloat.Repr(x));

    [Fact]
    public void Compensated_sum_of_ten_tenths_is_exactly_one() =>
        Assert.Equal(1.0, PySum.Sum(Enumerable.Repeat(0.1, 10).ToList()));

    [Fact]
    public void Floor_division_and_modulo_follow_the_divisors_sign()
    {
        Assert.Equal(-4, (int)PyArith.FloorDiv((System.Numerics.BigInteger)(-7), 2));
        Assert.Equal(1, (int)PyArith.Mod((System.Numerics.BigInteger)(-7), 2));
        Assert.Equal(-1.0, PyArith.Mod(7.0, -2.0));
    }

    [Fact]
    public void Division_by_zero_raises_instead_of_returning_infinity() =>
        Assert.Throws<PyZeroDivisionError>(() => PyArith.TrueDiv(1.0, 0.0));

    [Fact]
    public void Replace_raises_value_error_for_a_nonexistent_day() =>
        Assert.Throws<PyValueError>(() => PyDate.Replace(new DateOnly(2023, 1, 31), month: 2));

    [Fact]
    public void Upper_expands_sharp_s_unlike_the_bcl() => Assert.Equal("STRASSE", PyStr.Upper("straße"));
}
