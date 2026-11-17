# Prompt agents

`AgentRoster.Load()` validates the packaged roster, all twelve prompt bodies and
the current versions against the manifest before exposing `Specs`. The default
SDK `**/*.resx` glob embeds `Resources/Prompts.resx`; no source checkout, working
directory, copy-to-output step or shared project-file change is required.

The bundle contains the read-only Python `agents.json`, prompt Markdown and
manifest as string resources. Instruction bodies retain whitespace and trailing
newlines; only platform line endings normalize. The manifest retains history,
but a historical hash cannot validate a different current version. When the
Python reference changes, regenerate the corresponding resource values together;
the tests compare packaged definitions to the reference and captured publications.

For an explicitly managed file bundle, pass
`new DirectoryAgentResources(absoluteBaseDirectory)` to `AgentRoster.Load`.
That directory contains `agents.json` and `prompts/` with the Markdown files and
`manifest.json`. No implicit repository search occurs at runtime.

`AgentPublisher` requires an injected `IAgentPublishingClient` and supplied
`ModelRole` configuration. It builds `tcc-` create-version requests, omits
unsupported sampling parameters, reuses identical definitions and supports
explicit version pins. The tests verify all twelve captured fake requests and
returned projections; they do not prove an installed Foundry SDK or live service.
No SDK transport or invocation factory is supplied by this folder.

`AgentNarrator(AgentRoster, ModelRouter)` implements the feature-owned
`IAiNarrator` using the existing W1 `NarrationService` and provider graph, without
replacing shared registrations. Disabled/unavailable provider readiness remains
unchanged. Composition must register the roster and bridge explicitly.
