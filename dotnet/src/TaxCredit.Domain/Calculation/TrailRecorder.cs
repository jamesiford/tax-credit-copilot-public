using TaxCredit.Domain.Numerics;

namespace TaxCredit.Domain.Calculation;

/// <summary>One recorded calculation step: <c>{step, inputs, formula, output, citation}</c>.</summary>
/// <param name="Step">Step id.</param>
/// <param name="Inputs">Inputs.</param>
/// <param name="Formula">Human-readable formula.</param>
/// <param name="Output">Outputs.</param>
/// <param name="Citation">Source citation.</param>
public sealed record TrailStep(string Step, PyDict Inputs, string Formula, PyDict Output, string Citation)
{
    /// <summary>The step as a tree, key order as Python's <c>TrailStep.to_dict</c>.</summary>
    /// <returns>The tree.</returns>
    public PyDict ToDict() => new PyDict().Add("step", Step).Add("inputs", Inputs).Add("formula", Formula).Add("output", Output).Add("citation", Citation);
}

/// <summary>
/// Per-request calculation trail (Python <c>domain/calculation/trail.py</c> <c>TrailRecorder</c>).
/// <see cref="ToDict"/> stamps a SHA-256 over the canonical trail bytes, so the trail fingerprints itself.
/// </summary>
/// <param name="title">Trail title.</param>
/// <param name="citation">Trail citation.</param>
public sealed class TrailRecorder(string title = "", string citation = "")
{
    private readonly List<TrailStep> _steps = [];

    /// <summary>The trail title; the credit tools set it when it is still empty or <c>Pending</c> (Python assigns <c>recorder.title</c>).</summary>
    public string Title { get; set; } = title;

    /// <summary>The trail citation; the what-if tool sets it to the baseline credit's citation (Python assigns <c>recorder.citation</c>).</summary>
    public string Citation { get; set; } = citation;

    /// <summary>The recorded steps.</summary>
    public IReadOnlyList<TrailStep> Steps => _steps;

    /// <summary>Appends a step.</summary>
    /// <param name="step">Step id.</param>
    /// <param name="inputs">Inputs.</param>
    /// <param name="formula">Formula text.</param>
    /// <param name="output">Outputs.</param>
    /// <param name="citation">Citation.</param>
    public void Record(string step, PyDict inputs, string formula, PyDict output, string citation) =>
        _steps.Add(new TrailStep(step, inputs, formula, output, citation));

    /// <summary>The trail tree including <c>evidence_hash</c> (key order: title, citation, steps, evidence_hash).</summary>
    /// <returns>The tree.</returns>
    public PyDict ToDict()
    {
        var d = new PyDict().Add("title", Title).Add("citation", Citation).Add("steps", _steps.Select(s => (object?)s.ToDict()).ToList());
        return d.Add("evidence_hash", PyJson.EvidenceHash(d));
    }
}

/// <summary>The ambient recorder (Python <c>ContextVar</c>): each async flow sees its own.</summary>
public static class TrailContext
{
    private static readonly AsyncLocal<TrailRecorder?> Recorder = new();

    /// <summary>The recorder active for this flow, if any.</summary>
    public static TrailRecorder? Current => Recorder.Value;

    /// <summary>Makes <paramref name="recorder"/> current until the returned scope is disposed.</summary>
    /// <param name="recorder">The recorder.</param>
    /// <returns>A scope that restores the previous recorder.</returns>
    public static IDisposable Use(TrailRecorder recorder)
    {
        var previous = Recorder.Value;
        Recorder.Value = recorder;
        return new Scope(previous);
    }

    private sealed class Scope(TrailRecorder? previous) : IDisposable
    {
        public void Dispose() => Recorder.Value = previous;
    }
}

/// <summary>Helpers to put engine numbers into trail trees with Python's int/float distinction.</summary>
public static class TrailValues
{
    /// <summary>An int-or-float number as a tree value (<c>long</c> or <c>double</c>).</summary>
    /// <param name="n">The number.</param>
    /// <returns>The tree value.</returns>
    public static object Of(PyNumber n) => n.IsInt ? (object)n.IntValue : (object)n.FloatValue;

    /// <summary>Python's <c>str(n)</c> / f-string rendering of an int-or-float.</summary>
    /// <param name="n">The number.</param>
    /// <returns>The text.</returns>
    public static string Str(PyNumber n) => n.IsInt ? n.IntValue.ToString(System.Globalization.CultureInfo.InvariantCulture) : PyFloat.Repr(n.FloatValue);
}
