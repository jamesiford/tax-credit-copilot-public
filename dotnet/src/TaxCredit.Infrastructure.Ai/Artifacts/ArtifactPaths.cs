using TaxCredit.Application.Ports.Ai.Artifacts;

namespace TaxCredit.Infrastructure.Ai.Artifacts;

internal static class ArtifactPaths
{
    internal static string[] Validate(string container, string path)
    {
        if (string.IsNullOrWhiteSpace(container) || container.Length > 63 ||
            !container.All(c => char.IsAsciiLetterOrDigit(c) || c is '_' or '-') ||
            container[0] is '_' or '-' || IsDeviceName(container) || string.IsNullOrEmpty(path) || path.Length > 1024 ||
            path.IndexOfAny(['\\', ':', '\0']) >= 0 || path.StartsWith('/') ||
            path.Any(char.IsControl))
        {
            throw InvalidPath();
        }

        string[] parts = path.Split('/');
        if (parts.Any(p => p.Length == 0 || p is "." or ".." || p.EndsWith('.') || p.EndsWith(' ') ||
            p.IndexOfAny(['<', '>', '"', '|', '?', '*']) >= 0 || IsDeviceName(p)))
        {
            throw InvalidPath();
        }
        return parts;
    }

    private static bool IsDeviceName(string segment)
    {
        string stem = segment.Split('.')[0];
        return stem.Equals("CON", StringComparison.OrdinalIgnoreCase) ||
            stem.Equals("PRN", StringComparison.OrdinalIgnoreCase) ||
            stem.Equals("AUX", StringComparison.OrdinalIgnoreCase) ||
            stem.Equals("NUL", StringComparison.OrdinalIgnoreCase) ||
            (stem.Length == 4 && (stem.StartsWith("COM", StringComparison.OrdinalIgnoreCase) ||
                stem.StartsWith("LPT", StringComparison.OrdinalIgnoreCase)) && stem[3] is >= '1' and <= '9');
    }

    internal static ArtifactByteException InvalidPath() =>
        new("invalid_artifact_path", 422, "The artifact path is not a safe relative object path.");

    internal static ArtifactByteException Conflict() =>
        new("artifact_exists", 409, "This artifact path is already occupied; artifacts are immutable.");

    internal static ArtifactByteException Unavailable() =>
        new("artifact_store_unavailable", 503, "The artifact byte store is unavailable.");
}
