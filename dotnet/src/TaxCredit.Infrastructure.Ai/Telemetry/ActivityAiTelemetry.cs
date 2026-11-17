using System.Collections.Concurrent;
using System.Diagnostics;
using System.Diagnostics.Metrics;
using TaxCredit.Application.Ports.Ai;

namespace TaxCredit.Infrastructure.Ai.Telemetry;

/// <summary>OpenTelemetry listeners/exporters are host-owned. Only registered low-cardinality labels leave this adapter.</summary>
public sealed class ActivityAiTelemetry : IAiTelemetry, IDisposable
{
    /// <summary>Register this ActivitySource and Meter in the host's OpenTelemetry pipeline.</summary>
    public const string InstrumentationName = "TaxCredit.Ai";
    private readonly ActivitySource _activities;
    private readonly Meter _meter;
    private readonly Histogram<double> _duration;
    private readonly Histogram<long> _tokens;
    private readonly ConcurrentDictionary<string, Counter<long>> _counters = new();
    private readonly HashSet<string> _labels;
    private readonly TimeProvider _clock;
    private static readonly HashSet<string> Metrics = ["ai.retries", "ai.breaker_opens", "ai.bulkhead_rejections",
        "ai.budget_refusals", "ai.injection_blocked", "ai.egress_refusals", "ai.degraded"];
    /// <summary>Accepts only root-registered metadata labels; all other labels become unknown.</summary>
    public ActivityAiTelemetry(IEnumerable<string> registeredLabels, TimeProvider? clock = null,
        ActivitySource? activities = null, Meter? meter = null)
    {
        _labels = registeredLabels.Where(v => v.Length <= 64).ToHashSet(StringComparer.Ordinal);
        _clock = clock ?? TimeProvider.System;
        _activities = activities ?? new ActivitySource(InstrumentationName);
        _meter = meter ?? new Meter(InstrumentationName);
        _duration = _meter.CreateHistogram<double>("gen_ai.client.operation.duration", "s");
        _tokens = _meter.CreateHistogram<long>("gen_ai.client.token.usage", "{token}");
    }
    private string Label(string? value) => value is not null && _labels.Contains(value) ? value : "unknown";
    /// <inheritdoc/>
    public IAiCallSpan StartCall(AiCallInfo info)
    {
        var labels = new Dictionary<string, object?>
        {
            ["gen_ai.operation.name"] = "chat",
            ["gen_ai.provider.name"] = Label(info.Provider),
            ["gen_ai.agent.name"] = Label(info.Agent),
            ["tcc.role"] = info.Role.ToString().ToLowerInvariant()
        };
        if (info.Model is not null)
        {
            labels["gen_ai.request.model"] = Label(info.Model);
        }

        return new Span(this, _activities.StartActivity("chat", ActivityKind.Client), labels, _clock.GetTimestamp());
    }
    /// <inheritdoc/>
    public void Count(string metric, long value = 1, string? provider = null, string? scope = null)
    {
        if (!Metrics.Contains(metric))
        {
            return;
        }

        var tags = new TagList { { "provider", Label(provider) } };
        if (scope is "overall" or "per-user")
        {
            tags.Add("scope", scope);
        }

        _counters.GetOrAdd(metric, n => _meter.CreateCounter<long>(n)).Add(value, tags);
    }
    /// <inheritdoc/>
    public void Dispose() { _activities.Dispose(); _meter.Dispose(); }
    private sealed class Span(ActivityAiTelemetry owner, Activity? activity,
        Dictionary<string, object?> labels, long started) : IAiCallSpan
    {
        private int _ended;
        public void Finish(AiCallResult result)
        {
            if (Interlocked.Exchange(ref _ended, 1) != 0)
            {
                return;
            }

            labels["tcc.outcome"] = result.Outcome is "ok" or "error" or "cancelled" or "abandoned" ? result.Outcome : "unknown";
            labels["tcc.prompt_chars"] = result.PromptChars;
            labels["tcc.output_chars"] = result.OutputChars;
            if (result.ErrorType is not null)
            {
                labels["error.type"] = Enum.TryParse<ModelErrorKind>(result.ErrorType, out var kind) ? kind.ToString() : "provider_error";
            }

            if (result.End is { } end)
            {
                labels["gen_ai.response.model"] = owner.Label(end.Model);
                labels["tcc.hops"] = string.Join(",", (end.Hops ?? []).Select(owner.Label));
                labels["tcc.fallback_used"] = end.FallbackUsed;
                labels["tcc.agent_version"] = owner.Label(end.AgentVersion);
                labels["tcc.degraded"] = end.FinishReason is "degraded" or "interrupted";
                if (end.FinishReason is "stop" or "length" or "tool_calls" or "content_filter" or "degraded" or "interrupted")
                {
                    labels["gen_ai.response.finish_reason"] = end.FinishReason;
                }
            }
            RecordUsage(result.Usage);
            foreach (var pair in labels)
            {
                activity?.SetTag(pair.Key, pair.Value);
            }

            if (result.Outcome == "error")
            {
                activity?.SetStatus(ActivityStatusCode.Error, "model_error");
            }

            activity?.Stop();
            owner._duration.Record(owner._clock.GetElapsedTime(started).TotalSeconds, new TagList(labels.ToArray()));
        }
        private void RecordUsage(ModelUsage? usage)
        {
            if (usage is null)
            {
                return;
            }

            labels["tcc.estimated_usage"] = usage.Estimated;
            foreach (var (type, count) in new[] { ("input", usage.InputTokens), ("output", usage.OutputTokens) })
            {
                if (count is null)
                {
                    continue;
                }

                activity?.SetTag($"gen_ai.usage.{type}_tokens", count);
                var tags = new TagList(labels.ToArray()) { { "gen_ai.token.type", type } };
                owner._tokens.Record(count.Value, tags);
            }
        }
    }
}
