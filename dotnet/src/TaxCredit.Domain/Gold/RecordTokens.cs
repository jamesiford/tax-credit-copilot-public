using System.Numerics;
using System.Security.Cryptography;
using TaxCredit.Domain.Numerics;

namespace TaxCredit.Domain.Gold;

/// <summary>Python <c>tools/tokens.py</c>: the opaque per-employee handle every drill-in is keyed by.</summary>
public static class RecordTokens
{
    /// <summary>
    /// Python <c>record_token(account_id, program_code, tax_year, employee_id)</c>: the first 24 hex digits of SHA-256 over
    /// <c>f"{account_id}\0{program_code}\0{tax_year}\0{employee_id}"</c> encoded as UTF-8.
    /// </summary>
    /// <remarks>
    /// Why it lives in one place: the token minted by one read must resolve in another, and a second derivation is a drill URL that 404s on every row.
    /// A <c>None</c> account is the text <c>None</c> (f-string), and a lone surrogate in the id raises <see cref="PyUnicodeEncodeError"/>
    /// from <c>str.encode()</c> rather than hashing a replacement character.
    /// </remarks>
    /// <param name="accountId">The client (account) id; <c>null</c> is Python <c>None</c>.</param>
    /// <param name="programCode">The programme code.</param>
    /// <param name="taxYear">The tax year.</param>
    /// <param name="employeeId">The employee id.</param>
    /// <returns>24 lowercase hex digits.</returns>
    /// <exception cref="PyUnicodeEncodeError">When a text holds a lone surrogate.</exception>
    public static string RecordToken(BigInteger? accountId, string programCode, BigInteger taxYear, string employeeId)
    {
        ArgumentNullException.ThrowIfNull(programCode);
        ArgumentNullException.ThrowIfNull(employeeId);
        var account = accountId is { } id ? GoldValues.Str(id) : "None";
        var seed = $"{account}\0{programCode}\0{GoldValues.Str(taxYear)}\0{employeeId}";
        return Convert.ToHexString(SHA256.HashData(PyUtf8.Encode(seed))).ToLowerInvariant()[..24];
    }
}
