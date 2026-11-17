using System.Security.Cryptography;

namespace TaxCredit.Infrastructure.Persistence;

internal sealed class HashingReadStream(Stream input, IncrementalHash hash) : Stream
{
    public override bool CanRead => true;
    public override bool CanSeek => false;
    public override bool CanWrite => false;
    public override long Length => throw new NotSupportedException();
    public override long Position { get => throw new NotSupportedException(); set => throw new NotSupportedException(); }
    public override void Flush() => throw new NotSupportedException();
    public override long Seek(long offset, SeekOrigin origin) => throw new NotSupportedException();
    public override void SetLength(long value) => throw new NotSupportedException();
    public override void Write(byte[] buffer, int offset, int count) => throw new NotSupportedException();

    public override int Read(byte[] buffer, int offset, int count)
    {
        var read = input.Read(buffer, offset, count);
        hash.AppendData(buffer, offset, read);
        return read;
    }

    public override int Read(Span<byte> buffer)
    {
        var read = input.Read(buffer);
        hash.AppendData(buffer[..read]);
        return read;
    }
}
