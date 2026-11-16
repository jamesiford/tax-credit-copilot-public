namespace TaxCredit.Application.Features.ReadsCalc;

/// <summary>Display-only legacy fixture dimensions; source-schema units deliberately fall back to their own key.</summary>
public static class SiteLabels
{
    private static readonly Dictionary<string, (string Name, string County, string City)> Sites =
        new Dictionary<string, (string, string, string)>(StringComparer.Ordinal)
        {
            ["GA_ATL_HQ"] = ("Atlanta HQ", "Fulton", "Atlanta"),
            ["GA_SAV_DC"] = ("Savannah Distribution Center", "Chatham", "Savannah"),
            ["GA_MAC_OPS"] = ("Macon Operations", "Bibb", "Macon"),
            ["GA_CUM_OPS"] = ("Cumberland Center", "Cobb", "Cumberland"),
            ["NY_NYC_OFC"] = ("Manhattan Office", "New York", "New York"),
            ["NY_BKN_HUB"] = ("Brooklyn Hub", "Kings", "Brooklyn"),
            ["SC_CHS_PORT"] = ("Charleston Port Ops", "Charleston", "Charleston"),
            ["SC_GVL_FAC"] = ("Greenville Facility", "Greenville", "Greenville"),
            ["TX_AUS_TECH"] = ("Austin Tech Hub", "Travis", "Austin"),
            ["TX_HOU_HUB"] = ("Houston Distribution Hub", "Harris", "Houston"),
            ["TX_DAL_REG"] = ("Dallas Regional", "Dallas", "Dallas"),
            ["NC_CLT_DC"] = ("Charlotte Distribution Center", "Mecklenburg", "Charlotte"),
            ["NC_RDU_OFC"] = ("Raleigh-Durham Office", "Wake", "Raleigh"),
            ["TN_BNA_DC"] = ("Nashville Distribution Center", "Davidson", "Nashville"),
            ["TN_MEM_DC"] = ("Memphis Fulfillment Center", "Shelby", "Memphis"),
            ["FL_JAX_HUB"] = ("Jacksonville Hub", "Duval", "Jacksonville"),
            ["FL_MIA_OFC"] = ("Miami Regional Office", "Miami-Dade", "Miami"),
            ["OH_CMH_FAC"] = ("Columbus Facility", "Franklin", "Columbus"),
            ["OH_CVG_HUB"] = ("Cincinnati Hub", "Hamilton", "Cincinnati"),
            ["CO_DEN_OFC"] = ("Denver Regional Office", "Denver", "Denver"),
            ["VA_IAD_HUB"] = ("Northern Virginia Hub", "Fairfax", "Tysons Corner"),
        };

    /// <summary>A label is never guessed for an unknown unit.</summary>
    public static string Name(string worksite) => Sites.TryGetValue(worksite, out var site) ? site.Name : worksite;

    /// <summary>The legacy catalogue is display metadata, not a payroll-derived location.</summary>
    public static Portfolio.PortfolioWorksite? Reference(string worksite) => Sites.TryGetValue(worksite, out var site)
        ? new(site.Name, site.County, site.City) : null;

    internal static object Dimension(string worksite)
    {
        var known = Sites.TryGetValue(worksite, out var site);
        return ReadValues.Map(("worksite_id", worksite), ("name", known ? site.Name : worksite),
            ("county", known ? site.County : ""), ("city", known ? site.City : ""));
    }
}
