using System.Globalization;
using System.Net;
using System.Net.Security;
using System.Net.Sockets;
using System.Text;

namespace TaxCredit.Orchestrator.Boundary;

/// <summary>Explicitly installed real network adapter; tests replace this with a synthetic probe.</summary>
public sealed class SystemDiagnosticNetworkProbe : IDiagnosticNetworkProbe, IDisposable
{
    private readonly HttpClient http;

    /// <summary>Own a credential-free, non-redirecting HTTP transport; an optional handler supports local wire tests.</summary>
    public SystemDiagnosticNetworkProbe(HttpMessageHandler? handler = null)
    {
        http = new HttpClient(handler ?? new SocketsHttpHandler
        {
            AllowAutoRedirect = false,
            UseCookies = false,
            ConnectTimeout = TimeSpan.FromSeconds(10),
        })
        {
            Timeout = Timeout.InfiniteTimeSpan,
        };
    }

    /// <inheritdoc />
    public async Task<IReadOnlyList<string>> ResolveAsync(string host, CancellationToken cancellationToken) =>
        (await Dns.GetHostAddressesAsync(host, cancellationToken).ConfigureAwait(false))
        .Select(address => address.ToString()).Distinct(StringComparer.Ordinal).ToArray();

    /// <inheritdoc />
    public async Task ConnectAsync(string address, CancellationToken cancellationToken)
    {
        using var tcp = new TcpClient();
        await tcp.ConnectAsync(IPAddress.Parse(address), 443, cancellationToken).ConfigureAwait(false);
    }

    /// <inheritdoc />
    public async Task<int> TlsGetStatusAsync(string host, string address, CancellationToken cancellationToken)
    {
        ValidateHost(host);
        using var tcp = new TcpClient();
        await tcp.ConnectAsync(IPAddress.Parse(address), 443, cancellationToken).ConfigureAwait(false);
        await using var tls = new SslStream(tcp.GetStream());
        await tls.AuthenticateAsClientAsync(new SslClientAuthenticationOptions { TargetHost = host }, cancellationToken).ConfigureAwait(false);
        var request = Encoding.ASCII.GetBytes("GET / HTTP/1.1\r\nHost: " + host +
            "\r\nConnection: close\r\nUser-Agent: tcc-netcheck\r\n\r\n");
        await tls.WriteAsync(request, cancellationToken).ConfigureAwait(false);
        var bytes = new byte[256];
        var read = 0;
        while (read < bytes.Length)
        {
            var count = await tls.ReadAsync(bytes.AsMemory(read), cancellationToken).ConfigureAwait(false);
            if (count == 0)
            {
                break;
            }
            read += count;
            if (Array.IndexOf(bytes, (byte)'\n', 0, read) >= 0)
            {
                break;
            }
        }
        var parts = Encoding.ASCII.GetString(bytes, 0, read).Split(' ', 3);
        return parts.Length > 1 && int.TryParse(parts[1], NumberStyles.None, CultureInfo.InvariantCulture, out var status) ? status : 0;
    }

    /// <inheritdoc />
    public async Task<int> HttpGetStatusAsync(Uri uri, CancellationToken cancellationToken)
    {
        ArgumentNullException.ThrowIfNull(uri);
        if (!uri.IsAbsoluteUri || uri.Scheme != Uri.UriSchemeHttps || uri.UserInfo.Length != 0 || uri.Fragment.Length != 0)
        {
            throw new ArgumentException("Diagnostic HTTP targets must be credential-free HTTPS URLs.", nameof(uri));
        }
        using var request = new HttpRequestMessage(HttpMethod.Get, uri);
        using var response = await http.SendAsync(request, HttpCompletionOption.ResponseHeadersRead, cancellationToken).ConfigureAwait(false);
        return (int)response.StatusCode;
    }

    /// <summary>Composition owns this adapter and its pooled HTTP connections.</summary>
    public void Dispose() => http.Dispose();

    private static void ValidateHost(string host)
    {
        if (Uri.CheckHostName(host) is UriHostNameType.Unknown || host.Any(char.IsControl))
        {
            throw new ArgumentException("A diagnostic TLS host must be a DNS name or address.", nameof(host));
        }
    }
}
