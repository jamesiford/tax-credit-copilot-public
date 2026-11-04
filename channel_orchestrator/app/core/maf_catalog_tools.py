"""One MAF `FunctionTool` per tool the catalog offers a model, generated and never written. [RM-07]

The catalog (`application.capabilities.catalog`) is the only place a tool's name, description, argument
schema and kind are defined. This module turns each `CapabilitySpec` a model may name into a framework
tool by reading those four things and nothing else; it holds no tool name, no description and no schema
of its own (`test_architecture_catalog_only.py` fails if one appears).

A tool is built ONCE and carries no state. The turn it runs for (who is asking, the conversation, the
gateway) arrives per request in `function_invocation_kwargs` and is read from `FunctionInvocationContext`
by the body, which only forwards: it computes, rounds, ranks and defaults nothing. Whether a call may run,
and with which arguments, is decided by the function middleware around it (`maf_tool_rules`), and what the
model is told about the answer is decided there too.
"""
from collections.abc import Awaitable, Callable
from typing import Any

from agent_framework import SKIP_PARSING, FunctionInvocationContext, FunctionTool

from application.capabilities import catalog

#: The key under which a turn travels in `function_invocation_kwargs`.
TURN = "turn"
#: What a tool does with a call: the spec it was built from and the arguments, in the framework's context.
ToolBody = Callable[[FunctionInvocationContext, catalog.CapabilitySpec, dict[str, Any]], Awaitable[Any]]


async def forward_to_gateway(ctx: FunctionInvocationContext, spec: catalog.CapabilitySpec, args: dict[str, Any]) -> Any:
    """The default body: one gateway call as the acting person, answered with the gateway's reply untouched."""
    turn = ctx.kwargs[TURN]
    return await turn.forward(spec, args)


def catalog_tool(spec: catalog.CapabilitySpec, body: ToolBody = forward_to_gateway) -> FunctionTool:
    """The framework tool for `spec`: name, description and kind from the catalog, the model's schema derived from it."""
    async def call(ctx: FunctionInvocationContext, **args: Any) -> Any:
        return await body(ctx, spec, args)

    return FunctionTool(
        name=spec.name, description=spec.description, func=call, input_model=catalog.model_schema(spec),
        result_parser=SKIP_PARSING,
    )


def catalog_tools(body: ToolBody = forward_to_gateway) -> list[FunctionTool]:
    """A tool for every capability a model may name, in name order. A commit is not among them."""
    return [catalog_tool(spec, body) for spec in sorted(catalog.model_offered(), key=lambda s: s.name)]
