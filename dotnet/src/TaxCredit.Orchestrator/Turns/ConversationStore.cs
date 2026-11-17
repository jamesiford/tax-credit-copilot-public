using System.Text.Json.Nodes;

namespace TaxCredit.Orchestrator.Turns;

/// <summary>Mutable selection belongs to a verified person/conversation, never a singleton tool definition.</summary>
public sealed class ConversationState
{
    /// <summary>A conversation can retain a reader-selected client, never a model-selected one.</summary>
    public int? ClientId { get; set; }
    /// <summary>Read-only questions can inherit the last successfully read year.</summary>
    public int? TaxYear { get; set; }
    /// <summary>Only the resolver's numbered choices are valid follow-up selections.</summary>
    public JsonArray Candidates { get; set; } = [];
    /// <summary>The original question survives a numbered client or review-year clarification.</summary>
    public string Question { get; set; } = "";
    /// <summary>History is bounded routing context, not numeric authority.</summary>
    public List<JsonObject> History { get; } = [];

    /// <summary>Retain enough referential context without keeping unbounded reader payroll text.</summary>
    public void Remember(string role, string text)
    {
        History.Add(new JsonObject { ["role"] = role, ["text"] = text[..Math.Min(text.Length, 500)] });
        if (History.Count > 6) { History.RemoveRange(0, History.Count - 6); }
    }
}

/// <summary>Serializes a whole turn, including confirmation, without expiring an active lease.</summary>
public sealed class ConversationStore(TimeSpan ttl, TimeProvider? timeProvider = null)
{
    private readonly Dictionary<string, Entry> _entries = new(StringComparer.Ordinal);
    private readonly object _sync = new();
    private readonly TimeProvider _clock = timeProvider ?? TimeProvider.System;

    /// <summary>A count carries no conversation keys or identity.</summary>
    public int Count { get { lock (_sync) { return _entries.Count; } } }

    /// <summary>Callers must construct the key from verified identity and the selected conversation.</summary>
    public async ValueTask<Lease> AcquireAsync(string key, CancellationToken cancellationToken)
    {
        Entry entry;
        bool isNew;
        lock (_sync)
        {
            var now = _clock.GetTimestamp();
            foreach (var expired in _entries.Where(pair => pair.Value.Borrowers == 0 &&
                _clock.GetElapsedTime(pair.Value.Touched, now) >= ttl).Select(pair => pair.Key).ToArray())
            {
                _entries[expired].Dispose();
                _entries.Remove(expired);
            }
            isNew = !_entries.TryGetValue(key, out entry!);
            if (isNew) { _entries[key] = entry = new Entry(now); }
            entry.Borrowers++;
        }
        try { await entry.Gate.WaitAsync(cancellationToken).ConfigureAwait(false); }
        catch
        {
            lock (_sync) { entry.Borrowers--; }
            throw;
        }
        return new Lease(entry.State, isNew, () =>
        {
            lock (_sync)
            {
                entry.Touched = _clock.GetTimestamp();
                entry.Borrowers--;
                entry.Gate.Release();
            }
        });
    }

    private sealed class Entry(long touched) : IDisposable
    {
        public readonly ConversationState State = new();
        public readonly SemaphoreSlim Gate = new(1, 1);
        public long Touched = touched;
        public int Borrowers;
        public void Dispose() => Gate.Dispose();
    }

    /// <summary>Selection and checkpoint access are valid only while this lease is held.</summary>
    public sealed class Lease(ConversationState state, bool isNew, Action release) : IDisposable
    {
        private Action? _release = release;
        /// <summary>The serialized reader state.</summary>
        public ConversationState State { get; } = state;
        /// <summary>A newly allocated conversation cannot inherit a checkpoint left behind by an expired selection.</summary>
        public bool IsNew { get; } = isNew;
        /// <inheritdoc/>
        public void Dispose() => Interlocked.Exchange(ref _release, null)?.Invoke();
    }
}
