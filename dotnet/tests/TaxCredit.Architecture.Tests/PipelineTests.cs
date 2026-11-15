using Microsoft.Extensions.DependencyInjection;
using TaxCredit.Application;
using TaxCredit.Application.Messaging;
using TaxCredit.Application.Pipeline;
using TaxCredit.Application.Queries;
using TaxCredit.Infrastructure;

namespace TaxCredit.Architecture.Tests;

/// <summary>The mediator pipeline contract: Authorization, Validation, Handler, Audit (failed writes are audited too).</summary>
public sealed class PipelineTests
{
    private sealed record WriteThing(bool Valid = true) : ICommand<int>, IRequirePolicy, IValidatable
    {
        public Policy Policy => Policy.Writer;

        public IReadOnlyList<string> Validate() => Valid ? [] : ["bad"];
    }

    private sealed class WriteThingHandler : IRequestHandler<WriteThing, int>
    {
        public ValueTask<int> Handle(WriteThing request, CancellationToken cancellationToken) => ValueTask.FromResult(42);
    }

    private sealed class Allow(bool entitled) : IAuthorizer
    {
        public bool IsEntitled(Policy policy) => entitled;
    }

    private static (IMediator Mediator, InMemoryAuditLog Audit) Build(IAuthorizer? authorizer)
    {
        var services = new ServiceCollection().AddApplication().AddInfrastructure();
        services.AddTransient<IRequestHandler<WriteThing, int>, WriteThingHandler>();
        if (authorizer is not null)
        {
            services.AddSingleton(authorizer);
        }

        var provider = services.BuildServiceProvider();
        return (provider.GetRequiredService<IMediator>(), provider.GetRequiredService<InMemoryAuditLog>());
    }

    [Fact]
    public async Task A_query_flows_through_the_pipeline_and_is_audited()
    {
        var (mediator, audit) = Build(null);
        var info = await mediator.Send(new GetEngineInfoQuery());
        Assert.Contains("reference engine", info.Oracle, StringComparison.Ordinal);
        Assert.Equal("ok", Assert.Single(audit.Snapshot()).Outcome);
    }

    [Fact]
    public async Task A_command_with_a_policy_and_no_authorizer_is_refused_not_waved_through()
    {
        var (mediator, audit) = Build(null);
        await Assert.ThrowsAsync<RefusedException>(async () => await mediator.Send(new WriteThing()));
        Assert.Equal("refused", Assert.Single(audit.Snapshot()).Outcome);
    }

    [Fact]
    public async Task An_entitled_person_runs_the_command()
    {
        var (mediator, _) = Build(new Allow(true));
        Assert.Equal(42, await mediator.Send(new WriteThing()));
    }

    [Fact]
    public async Task An_unentitled_person_is_refused()
    {
        var (mediator, _) = Build(new Allow(false));
        await Assert.ThrowsAsync<RefusedException>(async () => await mediator.Send(new WriteThing()));
    }

    [Fact]
    public async Task An_invalid_command_is_rejected_and_audited_as_invalid()
    {
        var (mediator, audit) = Build(new Allow(true));
        await Assert.ThrowsAsync<ValidationFailedException>(async () => await mediator.Send(new WriteThing(Valid: false)));
        Assert.Equal("invalid", Assert.Single(audit.Snapshot()).Outcome);
    }
}
