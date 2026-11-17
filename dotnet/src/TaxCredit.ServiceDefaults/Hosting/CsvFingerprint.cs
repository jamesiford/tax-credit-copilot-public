using System.Globalization;
using System.Security.Cryptography;
using System.Text;
using TaxCredit.Application.Ports.Sources;

namespace TaxCredit.ServiceDefaults.Hosting;

internal sealed class CsvFingerprint(IClientPayrollSource payroll, string path) : ISourceFingerprintReader
{
    public SourceFingerprint Fingerprint(long accountId)
    {
        var count = payroll.LoadPayPeriods(accountId).Count;
        var maximum = File.GetLastWriteTimeUtc(path).ToString("O", CultureInfo.InvariantCulture);
        var encoding = string.Create(CultureInfo.InvariantCulture, $"csv-count-max-modified-v1:{count}:{maximum}");
        return new SourceFingerprint("csv-count-max-modified-v1", count, maximum, count == 0 ? "empty" : "present",
            encoding, Convert.ToHexStringLower(SHA256.HashData(Encoding.UTF8.GetBytes(encoding))), "committed-csv",
            ["Not a historical snapshot; count/max-preserving edits are undetectable."]);
    }
}
