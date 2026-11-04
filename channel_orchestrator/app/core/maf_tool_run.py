"""One named tool, through the same rules, for the modes that have no model loop. [RM-08]

The json and keyword modes choose their tools without a tool-calling model (a provider that cannot call tools,
or no model at all), so there is no framework loop to run the middleware. The rules must not be written a second
time for them, so one call is made the way the framework makes every call: a one-shot `Agent` whose chat client
asks for exactly that tool and then stops, with the same generated tool and the same function middleware. What
the model-visible answer would have been is read back from the tool result.

A name a model may not call never gets that far: it is refused and recorded here, which is what
`RecordUnregisteredCalls` does for the tools mode.
"""
import json
from collections.abc import Awaitable
from typing import Any

from agent_framework import Agent, BaseChatClient, ChatResponse, Content, FunctionInvocationLayer, Message

from app.core.maf_catalog_tools import TURN, catalog_tool
from app.core.maf_tool_call import CallAndCapture
from app.core.maf_tool_rules import tool_rules
from app.core.toolset import model_tools, refusal


class OneCall(FunctionInvocationLayer, BaseChatClient):
    """A chat client that asks for one tool call and, once it has the result, says nothing."""

    def __init__(self, name: str, arguments: dict[str, Any]) -> None:
        super().__init__(function_invocation_configuration={"max_iterations": 3, "allow_concurrent_invocation": False})
        self._name, self._arguments = name, arguments

    def _inner_get_response(self, *, messages: Any, stream: bool, options: Any, **kwargs: Any) -> Awaitable[ChatResponse]:
        if stream:
            raise NotImplementedError("a single tool call is not streamed")
        asked = any(c.type == "function_result" for m in messages for c in m.contents)

        async def respond() -> ChatResponse:
            if asked:
                return ChatResponse(messages=[Message("assistant", [""])])
            call = Content.from_function_call(call_id="one-call", name=self._name, arguments=json.dumps(self._arguments, default=str))
            return ChatResponse(messages=[Message("assistant", [call])])

        return respond()


def _answer_of(response: Any) -> dict[str, Any] | None:
    for message in response.messages:
        for content in message.contents:
            if content.type == "function_result":
                return json.loads(content.result) if isinstance(content.result, str) else None
    return None


async def run_through_the_rules(turn: Any, name: str, proposed: dict[str, Any]) -> dict[str, Any]:
    """Run `name` as `turn`'s tool with `proposed` arguments; the answer a model may see (names, never values)."""
    spec = model_tools().get(name)
    if spec is None:
        turn.refuse(name)
        return refusal("unknown_tool", f"{name} is not a tool you may call")
    agent = Agent(
        OneCall(name, proposed), "", tools=[catalog_tool(spec)], middleware=[*tool_rules(), CallAndCapture()],
        default_options={"additional_function_arguments": {TURN: turn}},
    )
    answer = _answer_of(await agent.run("call"))
    return answer if answer is not None else refusal("no_answer", f"{name} gave no answer")
