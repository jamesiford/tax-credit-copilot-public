using TaxCredit.Application.Ports.Contract;
using TaxCredit.Application.Ports.Sources;
using TaxCredit.Domain.Pipeline;
using TaxCredit.Domain.Programs;

namespace TaxCredit.Application.Features.ReadsCalc.Stored;

/// <summary>Gold reads resolve statute lazily; an unconfigured payroll adapter cannot prevent reading accepted rows.</summary>
public sealed class ReadStatutes(Func<ClientRunResolver> resolver, RuleLibrary library,
    ProgramDefaults defaults, IRuntimeConfiguration configuration)
{
    /// <summary>A missing fiscal source uses the existing explicitly labelled calendar assumption, never a payroll replay.</summary>
    public ResolvedStatute ResolveStatute(long? account, string? state, long year, string? program = null, bool requireProgram = false)
    {
        try
        {
            return resolver().ResolveStatute(account, state, year, program, requireProgram);
        }
        catch (SourceNotConfigured) when ((state is not null || program is not null)
            && configuration.Get("FISCAL_RULES_POLICY") != "strict")
        {
            var fallback = new ClientRunResolver(library, defaults,
                new FiscalSource(library, new NoFiscalRules()), new UnavailablePayroll());
            return fallback.ResolveStatute(account, state, year, program, requireProgram);
        }
    }

    private sealed class UnavailablePayroll : IPayrollSource
    {
        public IReadOnlyList<PayRow> LoadPayPeriods(long? accountId) => throw new SourceNotConfigured();
    }
}
