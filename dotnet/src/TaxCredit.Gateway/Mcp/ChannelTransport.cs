using System.Threading.Channels;
using ModelContextProtocol.Protocol;

namespace TaxCredit.Gateway.Mcp;

// HTTP owns authentication, sessions and errors; the SDK owns JSON-RPC method execution.
internal sealed class ChannelTransport(string sessionId) : ITransport
{
    private readonly Channel<JsonRpcMessage> _incoming = Channel.CreateBounded<JsonRpcMessage>(32);
    private readonly Channel<JsonRpcMessage> _outgoing = Channel.CreateBounded<JsonRpcMessage>(32);
    public string SessionId => sessionId;
    public ChannelReader<JsonRpcMessage> MessageReader => _incoming.Reader;
    public Task SendMessageAsync(JsonRpcMessage message, CancellationToken cancellationToken = default) =>
        _outgoing.Writer.WriteAsync(message, cancellationToken).AsTask();
    internal ValueTask ReceiveAsync(JsonRpcMessage message, CancellationToken ct) => _incoming.Writer.WriteAsync(message, ct);
    internal ValueTask<JsonRpcMessage> ReplyAsync(CancellationToken ct) => _outgoing.Reader.ReadAsync(ct);
    public ValueTask DisposeAsync()
    {
        _incoming.Writer.TryComplete();
        _outgoing.Writer.TryComplete();
        return ValueTask.CompletedTask;
    }
}
