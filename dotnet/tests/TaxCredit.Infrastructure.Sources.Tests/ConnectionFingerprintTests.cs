using Microsoft.Data.SqlClient;
using Azure.Core;
using Azure.Identity;
using TaxCredit.Application.Ports.Sources;
using TaxCredit.Infrastructure.Sources.Sql;

namespace TaxCredit.Infrastructure.Sources.Tests;

public sealed class ConnectionFingerprintTests
{
    [Fact]
    public async Task EntraAdapterAcceptsOnlyDatabaseScopeAndRedactsCredentialFailures()
    {
        var credential = new FakeCredential();
        var provider = new EntraAnalyticsTokenProvider(credential);
        _ = await provider.AcquireAsync(AnalyticsConnectionFactory.DatabaseScope, CancellationToken.None);
        Assert.Equal(AnalyticsConnectionFactory.DatabaseScope, Assert.Single(credential.Scopes!));
        await Assert.ThrowsAsync<ArgumentException>(() => provider.AcquireAsync("https://synthetic.invalid/.default", CancellationToken.None));
        credential.Failure = new AuthenticationFailedException("synthetic secret-bearing upstream diagnostic");
        var failure = await Assert.ThrowsAsync<SourceUnavailable>(() =>
            provider.AcquireAsync(AnalyticsConnectionFactory.DatabaseScope, CancellationToken.None));
        Assert.Null(failure.InnerException);
        Assert.DoesNotContain("synthetic secret", failure.Message, StringComparison.Ordinal);
    }

    [Fact]
    public async Task AnalyticsFactoryIsEncryptedPoolSeparatedAndUsesInjectedRefreshWithDatabaseScope()
    {
        var tokens = new TokenDouble();
        var factory = new AnalyticsConnectionFactory(new AnalyticsConnectionOptions("synthetic.invalid", "synthetic"), tokens);
        using var first = factory.Create();
        using var second = factory.Create();
        Assert.Equal(0, tokens.Calls);
        var settings = new SqlConnectionStringBuilder(first.ConnectionString);
        Assert.Equal(SqlConnectionEncryptOption.Mandatory, settings.Encrypt);
        Assert.False(settings.TrustServerCertificate);
        Assert.True(settings.Pooling);
        Assert.Equal(4, settings.MaxPoolSize);
        Assert.Equal("TaxCredit.SourceAnalytics", settings.ApplicationName);
        Assert.Empty(settings.UserID);
        Assert.Empty(settings.Password);
        Assert.Same(first.AccessTokenCallback, second.AccessTokenCallback);
        _ = await first.AccessTokenCallback!(null!, CancellationToken.None);
        _ = await second.AccessTokenCallback!(null!, CancellationToken.None);
        Assert.Equal(2, tokens.Calls);
        Assert.Equal(AnalyticsConnectionFactory.DatabaseScope, tokens.Scope);
        Assert.DoesNotContain("synthetic", new AnalyticsConnectionOptions("synthetic", "synthetic").ToString(), StringComparison.Ordinal);
        Assert.Equal("AnalyticsAccessToken(redacted)", new AnalyticsAccessToken("synthetic secret", DateTimeOffset.UtcNow).ToString());
    }

    [Fact]
    public async Task CallbackPropagatesCancellationWithoutAcquiringLiveCredentials()
    {
        var tokens = new TokenDouble();
        var factory = new AnalyticsConnectionFactory(new AnalyticsConnectionOptions("synthetic.invalid", "synthetic"), tokens);
        using var connection = factory.Create();
        using var cancellation = new CancellationTokenSource();
        await cancellation.CancelAsync();
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => connection.AccessTokenCallback!(null!, cancellation.Token));
        Assert.Equal(cancellation.Token, tokens.Cancellation);
        var blank = new AnalyticsConnectionFactory(new AnalyticsConnectionOptions("", ""), tokens);
        Assert.False(blank.IsConfigured);
        Assert.Throws<SourceNotConfigured>(() => blank.Create());
    }

    [Fact]
    public void FingerprintRepeatedEmptyCountDateAndOtherTenantChangesHaveDefinedSemantics()
    {
        var tables = SourceTestData.MiniTables();
        var (_, scanner, transport) = SourceTestData.Source(tables);
        var reader = new SourceFingerprintReader(scanner);
        var first = reader.Fingerprint(7);
        Assert.Equal(first, reader.Fingerprint(7) with { Limitations = first.Limitations });
        Assert.Equal(2, first.RowCount);
        Assert.Equal("present", first.ModifiedStatus);
        Assert.Equal("empty", reader.Fingerprint(999).ModifiedStatus);
        ((Dictionary<string, object?>)tables["Payroll"][2])["ModifyDate"] = "2029-01-01T00:00:00";
        Assert.Equal(first.Sha256, reader.Fingerprint(7).Sha256);
        ((Dictionary<string, object?>)tables["Payroll"][0])["ModifyDate"] = "2025-01-01T00:00:00";
        var changedDate = reader.Fingerprint(7);
        Assert.NotEqual(first.Sha256, changedDate.Sha256);
        ((Dictionary<string, object?>)tables["Payroll"][1])["Wages"] = "9999";
        Assert.Equal(changedDate.Sha256, reader.Fingerprint(7).Sha256);
        tables["Payroll"] = [.. tables["Payroll"], new Dictionary<string, object?>(tables["Payroll"][0])];
        Assert.NotEqual(changedDate.Sha256, reader.Fingerprint(7).Sha256);
        var query = transport.Queries.First(q => q.Kind == "fingerprint");
        Assert.Contains("COUNT_BIG(*)", query.Sql, StringComparison.Ordinal);
        Assert.Contains("MAX([ModifyDate])", query.Sql, StringComparison.Ordinal);
        Assert.Contains("WHERE [AccountId] = @p0", query.Sql, StringComparison.Ordinal);
        Assert.DoesNotContain("account_id", first.Encoding, StringComparison.Ordinal);
        Assert.Equal(64, first.Sha256.Length);
        Assert.Equal(4, first.Limitations.Count);
    }

    [Theory]
    [InlineData(false, "all_null")]
    [InlineData(true, "column_missing")]
    public void MissingAndNullModificationMetadataAreExplicit(bool missing, string expected)
    {
        var tables = SourceTestData.MiniTables();
        foreach (var row in tables["Payroll"].Cast<Dictionary<string, object?>>())
        {
            if (missing) { row.Remove("ModifyDate"); }
            else { row["ModifyDate"] = null; }
        }
        var scanner = SourceTestData.Source(tables).Scanner;
        var marker = new SourceFingerprintReader(scanner).Fingerprint(7);
        Assert.Equal(expected, marker.ModifiedStatus);
        Assert.Null(marker.MaximumModified);
    }

    [Fact]
    public void SourceCancellationStopsStreamingAndDisposesReader()
    {
        var (_, scanner, transport) = SourceTestData.Source();
        using var cancellation = new CancellationTokenSource();
        cancellation.Cancel();
        Assert.ThrowsAny<OperationCanceledException>(() => scanner.Scan("Payroll", 7, cancellationToken: cancellation.Token));
        Assert.Empty(transport.Queries);
    }

    private sealed class TokenDouble : IAnalyticsTokenProvider
    {
        internal int Calls { get; private set; }
        internal string? Scope { get; private set; }
        internal CancellationToken Cancellation { get; private set; }
        public Task<AnalyticsAccessToken> AcquireAsync(string scope, CancellationToken cancellationToken)
        {
            Calls++;
            Scope = scope;
            Cancellation = cancellationToken;
            cancellationToken.ThrowIfCancellationRequested();
            return Task.FromResult(new AnalyticsAccessToken("ephemeral-synthetic-token", DateTimeOffset.UtcNow.AddHours(1)));
        }

    }

    private sealed class FakeCredential : TokenCredential
    {
        internal string[]? Scopes { get; private set; }
        internal Exception? Failure { get; set; }
        public override AccessToken GetToken(TokenRequestContext requestContext, CancellationToken cancellationToken)
        {
            cancellationToken.ThrowIfCancellationRequested();
            Scopes = requestContext.Scopes;
            if (Failure is not null) { throw Failure; }
            return new AccessToken("ephemeral-synthetic", DateTimeOffset.UtcNow.AddHours(1));
        }
        public override ValueTask<AccessToken> GetTokenAsync(TokenRequestContext requestContext, CancellationToken cancellationToken) =>
            ValueTask.FromResult(GetToken(requestContext, cancellationToken));
    }
}
