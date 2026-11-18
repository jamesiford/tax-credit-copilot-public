using System.Text;
using TaxCredit.Application.Features.ClaimsArtifactsRules.Rules;
using TaxCredit.Domain.Programs;

namespace TaxCredit.ServiceDefaults.Hosting;

/// <summary>Contract mode freezes the metadata source using the harness protocol; deployed hosts read the file.</summary>
internal sealed class RuntimeRuleFileMetadata(IRulePackSource source, RuntimeConfiguration settings, RuntimeSources clock)
    : IRuleFileMetadata
{
    public DateTimeOffset ModifiedAt(string fileName)
    {
        if (!source.IsFile(fileName) || Path.GetFileName(fileName) != fileName)
        {
            throw new FileNotFoundException("Known rule file is missing.");
        }
        return settings.Get("CONTRACT_HOOKS") == "1"
            ? clock.UtcNow.AddDays(-30).AddSeconds(Crc32(fileName) % (20 * 86400))
            : new DateTimeOffset(File.GetLastWriteTimeUtc(Path.Combine(source.RulesDirectory, fileName)));
    }

    private static uint Crc32(string value)
    {
        var crc = uint.MaxValue;
        foreach (var octet in Encoding.UTF8.GetBytes(value))
        {
            crc ^= octet;
            for (var bit = 0; bit < 8; bit++)
            {
                crc = (crc >> 1) ^ ((crc & 1) == 0 ? 0 : 0xedb88320);
            }
        }
        return ~crc;
    }
}
