using TaxCredit.Domain.Gold;
using TaxCredit.Domain.Warehouse;

namespace TaxCredit.Infrastructure.Persistence;

internal static class SeedTables
{
    internal static IReadOnlyDictionary<string, IReadOnlyList<string>> Source { get; } = new Dictionary<string, IReadOnlyList<string>>(StringComparer.Ordinal)
    {
        ["pay_periods"] = ["Tax_Year", "Employee_ID", "Job_Title", "Worksite_ID", "Pay_Period_Start", "Pay_Period_End", "Pay_Date", "Entity_FEIN", "Hours_Worked", "Gross_Wages", "Pay_Code"],
        ["Account"] = ["AccountId", "AccountEid", "Name", "BillingState", "BillingCity", "BillingPostalCode", "IndustryTypeId", "AccountStatusId", "AccountTypeId", "ActualNumberOfEmployees", "ExternalName", "CreateDate"],
        ["Address"] = ["AddressId", "StreetAddress1", "CityName", "StateCountyZipId", "ZipCodeOriginal", "StateOriginal", "Latitude", "Longitude"],
        ["Employment"] = ["EmploymentId", "EmployeeId", "HireLocationId", "CurrentLocationId", "Status", "JobTitle", "HireDate", "StartDate", "TerminationDate", "TerminationReason", "EmploymentType", "WageType", "EmploymentStatus", "DepartmentNumber", "DepartmentName"],
        ["Entity"] = ["EntityId", "AccountId", "Name", "FederalTaxId", "StateTaxId", "ParentEntityId", "EntityBusinessTypeId", "FiscalYearRulesId", "InceptionDate", "DissolutionDate"],
        ["EntityFiscalYearRules"] = ["FiscalYearRulesId", "Name", "FiscalYearBegin", "FiscalYearEnd", "RuleExpression", "Inferred"],
        ["Location"] = ["LocationId", "AccountId", "EntityId", "LocationName", "AddressId", "ClientLocationId", "Dba", "OpenDate", "CloseDate", "LocationStatusId", "ScreeningStatusId"],
        ["PayCode"] = ["PayCodeId", "AccountId", "PayCode", "Description", "IsAca", "IsFuta", "PayCodeCategoryId"],
        ["PayFrequency"] = ["PayFrequencyId", "Name", "Inferred"],
        ["Payroll"] = ["PayrollId", "AccountId", "EmployeeId", "EntityId", "LocationId", "PayFrequencyId", "PayPeriodStart", "PayPeriodEnd", "PayDate", "Hours", "Wages", "ClientEmployeeId", "HourlyRate", "IsFullTime", "IsSalaried", "PayCodeId", "WorksiteLocationId", "InloadPayrollId", "CreateDate", "ModifyDate", "CreatedBy", "ModifiedBy"],
        ["StateCountyZip"] = ["StateCountyZipId", "StateAbbr", "StateName", "CountyName", "ZipCode"],
    };

    internal static Dictionary<string, IReadOnlyList<string>> Expected(string profile, IReadOnlyDictionary<string, IReadOnlyList<StorageColumn>> schema)
    {
        var result = GoldColumns.All.ToDictionary(p => "gold/" + p.Key + ".jsonl.gz", p => p.Value, StringComparer.Ordinal);
        result.Add("ops/run_manifest.jsonl.gz", WarehouseVocabulary.RunManifestColumns);
        foreach (var table in new[] { "program_claim", "program_engagement" })
        {
            IReadOnlyList<string> columns = table == "program_claim"
                ? ["claim_id", "client_id", "entity_id", "program_code", "tax_year", "status", "provenance", "identified_usd", "claimed_usd", "certified_usd",
                    "average_headcount", "base_average_headcount", "threshold_jobs", "is_base_year", "identified_run_id", "assumption_set_id", "rule_pack_version",
                    "filed_on", "filing_reference", "decided_by", "decided_at", "decline_reason", "effective_from", "effective_to"]
                : schema["ops." + table].Select(c => c.Name).ToArray();
            result.Add("operational/" + table + ".jsonl.gz", columns);
        }

        foreach (var (table, columns) in Source.Where(p => profile == "P1" ? p.Key == "pay_periods" : p.Key != "pay_periods"))
        {
            result.Add("source/" + table + ".jsonl.gz", columns);
        }

        return result;
    }
}
