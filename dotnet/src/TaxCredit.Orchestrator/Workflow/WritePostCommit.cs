using System.Text.Json;

namespace TaxCredit.Orchestrator.Workflow;

internal static class WritePostCommit
{
    private const string LinkTool = "claim_package_link";
    private const string LinkUnavailable = "The package was built, but its link is unavailable.";
    private static readonly string[] LinkArguments = ["client_id", "tax_year"];

    internal static async Task<WriteResult> EnrichAsync(
        WriteExecutionContext execution, HeldCommand held, WriteResult committed, CancellationToken cancellationToken)
    {
        if (held.Prepare.Tool != "claim_package_create_prepare")
        {
            return committed;
        }

        WriteResult unavailable = committed with { Note = LinkUnavailable };
        // The SDK may observe cancellation before the supplementary read unwinds.
        execution.Completed = unavailable;
        try
        {
            Dictionary<string, JsonElement> wanted = new(StringComparer.Ordinal);
            foreach (string key in LinkArguments)
            {
                if (held.Prepare.Arguments.TryGetProperty(key, out JsonElement value))
                {
                    wanted.Add(key, value);
                }
            }

            WriteGatewayReply reply = await execution.Gateway(execution.Owner,
                new(LinkTool, JsonSerializer.SerializeToElement(wanted)), cancellationToken).ConfigureAwait(false);
            return reply.IsSuccess
                ? committed with { FollowUps = [new(LinkTool, WriteEnvelope.Sanitize(reply, held.Token))] }
                : unavailable;
        }
        catch (Exception)
        {
            return unavailable;
        }
    }
}
