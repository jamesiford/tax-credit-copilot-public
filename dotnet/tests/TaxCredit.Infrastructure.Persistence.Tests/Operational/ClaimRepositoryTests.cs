using TaxCredit.Domain.Claims;
using TaxCredit.Domain.Numerics;
using TaxCredit.Domain.Pipeline;
using TaxCredit.Infrastructure.Persistence.Operational;

namespace TaxCredit.Infrastructure.Persistence.Tests.Operational;

public sealed class ClaimRepositoryTests
{
    private static readonly PyDateTime Now = PyDateTime.FromIsoFormat("2026-01-02T03:04:05.123456+00:00");

    [Theory]
    [InlineData("1234.50")]
    [InlineData("1234.5")]
    [InlineData("1000.0")]
    [InlineData("0.10")]
    public void RecordedMoneyLexemesAndAllClaimFieldsSurviveRestart(string money)
    {
        using var store = new OperationalDatabase();
        var claim = ProgramClaim.Create(new ClaimSpec
        {
            ClientId = 11,
            ProgramCode = "ga_jtc",
            TaxYear = 2023,
            ClaimId = "recorded",
            Status = ClaimStatus.Claimed,
            Provenance = Provenance.FiledByUs,
            IdentifiedUsd = money,
            ClaimedUsd = "0.20",
            CertifiedUsd = "33072.0700",
            AverageHeadcount = 75.5,
            BaseAverageHeadcount = 20,
            ThresholdJobs = 2,
            IsBaseYear = false,
            EntityId = 99,
            IdentifiedRunId = "run",
            AssumptionSetId = "assumptions",
            RulePackVersion = "pack",
            FiledOn = new DateOnly(2026, 1, 1),
            FilingReference = "synthetic-filing",
            DecidedBy = "synthetic-analyst",
            DecidedAt = Now,
            DeclineReason = "",
            EffectiveFrom = Now,
        });
        new ClaimRepository(store.Database).Record(claim);
        var got = new ClaimRepository(store.Reopen()).Current(11, "ga_jtc", 2023);
        Assert.Equal(claim, got);
        Assert.Equal(money, got!.IdentifiedUsd.ToString());
        Assert.Equal("0.20", got.ClaimedUsd.ToString());
        Assert.Equal("33072.0700", got.CertifiedUsd.ToString());
    }

    [Fact]
    public void SameDayAppendRetainsEveryIdentityWithOneCurrentLast()
    {
        using var store = new OperationalDatabase();
        var repository = new ClaimRepository(store.Database);
        IClaimSink sink = repository;
        sink.Record(Claim(11, "first"));
        sink.Record(Claim(11, "second"));
        sink.Record(Claim(11, "third"));
        var history = new ClaimRepository(store.Reopen()).History(11, "ga_jtc", 2023);
        Assert.Equal(3, history.Count);
        Assert.Equal(["first", "second", "third"], history.Select(claim => claim.ClaimId!).Order().ToArray());
        Assert.Equal("third", history[^1].ClaimId);
        Assert.Single(history, claim => claim.IsCurrent);
        Assert.All(history.Take(2), claim => Assert.Equal(Now, claim.EffectiveTo));
        Assert.Equal("third", repository.Current(11, "GA_JTC", 2023)!.ClaimId);
    }

    [Fact]
    public void DuplicateIdentityConflictsWithoutClosingTheCurrentRecord()
    {
        using var store = new OperationalDatabase();
        var repository = new ClaimRepository(store.Database);
        var first = repository.Record(Claim(11, "first"));
        Assert.Throws<InvalidOperationException>(() => repository.Record(first));
        Assert.Equal(first, repository.Current(11, "GA_JTC", 2023));
        Assert.Single(repository.History(11, "GA_JTC", 2023));
        var other = repository.Record(Claim(22, "other"));
        Assert.Throws<InvalidOperationException>(() => repository.Record(ProgramClaim.Create(first.ToSpec() with { ClientId = 22 })));
        Assert.Equal(other, repository.Current(22, "GA_JTC", 2023));
    }

    [Fact]
    public void CoverageSelectorsRespectEmptyVersusNullAndTenantCellsWithEqualKeys()
    {
        using var store = new OperationalDatabase();
        var repository = new ClaimRepository(store.Database);
        repository.Record(Claim(11, "one"));
        repository.Record(Claim(22, "two"));
        repository.Record(ProgramClaim.Create(Claim(11, "other").ToSpec() with { ProgramCode = "OTHER" }));
        Assert.Equal(2, repository.Coverage(11).Count);
        Assert.Single(repository.Coverage(22));
        Assert.Empty(repository.Coverage(11, programCodes: []));
        Assert.Empty(repository.Coverage(11, taxYears: []));
        Assert.Empty(repository.PortfolioCoverage(clientIds: []));
        Assert.Empty(repository.PortfolioCoverage(taxYears: []));
        Assert.Single(repository.Coverage(11, ["ga_jtc"], [2023]));
        Assert.Empty(repository.Coverage(11, ["ga_jtc"], [2022]));
        Assert.Single(repository.PortfolioCoverage([22], [2023]));
        Assert.Equal(3, repository.PortfolioCoverage().Count);
        Assert.Null(repository.Current(33, "GA_JTC", 2023));
        Assert.Contains(store.Messages, message => message.Contains("portfolio", StringComparison.Ordinal));
    }

    [Fact]
    public void InsertFailureAfterClosingPredecessorRollsBackTheWholeClaimAppend()
    {
        using var store = new OperationalDatabase();
        var repository = new ClaimRepository(store.Database);
        var first = repository.Record(Claim(11, "first"));
        var tooPrecise = ProgramClaim.Create(first.ToSpec() with { ClaimId = "too-precise", IdentifiedUsd = "1.23456" });
        Assert.Throws<Microsoft.Data.Sqlite.SqliteException>(() => repository.Record(tooPrecise));
        Assert.Equal(first, new ClaimRepository(store.Reopen()).Current(11, "GA_JTC", 2023));
        Assert.Single(repository.History(11, "GA_JTC", 2023));
    }

    [Fact]
    public void EngagementReplacementPreservesOtherClientAndProgram()
    {
        using var store = new OperationalDatabase();
        var repository = new ClaimRepository(store.Database);
        var original = new ProgramEngagement { ClientId = 11, ProgramCode = "ga_jtc", EffectiveFrom = Now, SetAt = Now, Note = "synthetic", SetBy = "author" };
        repository.SetEngagement(original);
        repository.SetEngagement(original with { ClientId = 22, Scope = EngagementScope.OutOfScope });
        repository.SetEngagement(original with { Scope = EngagementScope.InScope });
        Assert.Equal(EngagementScope.InScope, new ClaimRepository(store.Reopen()).Engagements(11).Single().Scope);
        Assert.Equal(EngagementScope.OutOfScope, repository.Engagements(22).Single().Scope);
        using var session = store.Database.Open();
        var history = session.Query(11, "SELECT scope, effective_to FROM tcc_ops.program_engagement WHERE {tenant}");
        Assert.Equal(2, history.Count);
        Assert.Single(history, row => row["effective_to"] is null);
    }

    internal static ProgramClaim Claim(long client, string id) => ProgramClaim.Create(new ClaimSpec
    {
        ClientId = client,
        ProgramCode = "GA_JTC",
        TaxYear = 2023,
        ClaimId = id,
        Status = ClaimStatus.Assessed,
        Provenance = Provenance.Computed,
        IdentifiedUsd = "1234.50",
        EffectiveFrom = Now,
    });
}
