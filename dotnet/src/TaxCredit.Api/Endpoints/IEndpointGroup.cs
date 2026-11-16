namespace TaxCredit.Api.Endpoints;

/// <summary>A route group owns its registration, so parallel slices never edit a shared route list.</summary>
public interface IEndpointGroup
{
    /// <summary>Maps this group's implemented operations.</summary>
    void Map(IEndpointRouteBuilder endpoints);
}
