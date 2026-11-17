using System.Text;
using TaxCredit.Application.Ports.Ai;

namespace TaxCredit.Infrastructure.Ai.Gateway;

/// <summary>Bounds allocation before parsing and keeps transport messages out of the error surface.</summary>
internal static class BoundedResponseReader
{
    private const int MaxChars = 1_048_576;
    public static async Task<Stream> OpenAsync(HttpContent content, CancellationToken ct)
    {
        try { return await content.ReadAsStreamAsync(ct).ConfigureAwait(false); }
        catch (OperationCanceledException) when (ct.IsCancellationRequested) { throw; }
        catch (Exception) { throw new ModelException(ModelErrorKind.Unavailable, "stream_transport_failed"); }
    }
    public static async Task<string> WholeAsync(StreamReader reader, CancellationToken ct)
    {
        var text = new StringBuilder();
        char[] buffer = new char[4096];
        int read;
        while ((read = await ReadAsync(reader, buffer, ct).ConfigureAwait(false)) > 0)
        {
            if (text.Length + read > MaxChars)
            {
                throw new ModelException(ModelErrorKind.Unavailable, "event_too_large");
            }
            text.Append(buffer, 0, read);
        }
        return text.ToString();
    }
    public static async Task<string?> LineAsync(StreamReader reader, CancellationToken ct)
    {
        var text = new StringBuilder();
        char[] buffer = new char[1];
        while (await ReadAsync(reader, buffer, ct).ConfigureAwait(false) > 0)
        {
            if (buffer[0] == '\n')
            {
                return text.ToString().TrimEnd('\r');
            }
            if (text.Length >= MaxChars)
            {
                throw new ModelException(ModelErrorKind.Unavailable, "event_too_large");
            }
            text.Append(buffer[0]);
        }
        return text.Length == 0 ? null : text.ToString();
    }
    private static async Task<int> ReadAsync(StreamReader reader, char[] buffer, CancellationToken ct)
    {
        try { return await reader.ReadAsync(buffer.AsMemory(), ct).ConfigureAwait(false); }
        catch (OperationCanceledException) when (ct.IsCancellationRequested) { throw; }
        catch (Exception) { throw new ModelException(ModelErrorKind.Unavailable, "stream_transport_failed"); }
    }
}
