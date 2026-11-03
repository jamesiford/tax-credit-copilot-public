"""What can go wrong when a model is asked for words. [AI-02, AI-04, AI-07]

Stdlib only, like the rest of `domain/`. The taxonomy is small on purpose: a caller
decides between four things — try again later, try the next provider, fix the
request, or give up — so adapters map whatever their SDK raises onto these and
nothing finer. `domain/ai.py` re-exports every name, so `from domain.ai import
ModelUnavailable` keeps working.
"""
from __future__ import annotations


class ModelError(Exception):
    """Base of the taxonomy. `retryable` says whether the same call may succeed later."""

    retryable = False


class ModelUnavailable(ModelError):
    """The provider could not be reached or answered 5xx."""

    retryable = True


class ModelTimeout(ModelError):
    """The provider did not answer in time."""

    retryable = True


class ModelRateLimited(ModelError):
    """The provider asked us to slow down; `retry_after` is seconds, when it said."""

    retryable = True

    def __init__(self, message: str = "rate limited", retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class ModelBadRequest(ModelError):
    """The request itself was refused (4xx other than 429). Retrying cannot help."""


class EgressRefused(ModelBadRequest):
    """The egress policy would not let this prompt leave for this provider."""


class ModelAuth(ModelError):
    """The provider refused our credentials. Retrying cannot help."""


class NarrationUnavailable(Exception):
    """Every provider failed or was refused. Callers fall back to the engine's own blocks."""

    def __init__(self, message: str = "no provider could answer", hops: tuple[str, ...] = ()) -> None:
        super().__init__(message)
        self.hops = hops


class BudgetExceeded(Exception):
    """A token ceiling would be crossed. Refuses rather than overspends."""

    def __init__(self, scope: str, limit: int) -> None:
        super().__init__(f"the {scope} token budget of {limit} for today is used up")
        self.scope, self.limit = scope, limit


class SafetyRefusal(Exception):
    """A safety rule stopped model text from going out or coming in.

    `codes` name the rules that fired and never echo the offending text: the text
    is exactly what must not be repeated. `reader_sentence` is what the reader is
    told in place of the prose; the engine's figures follow it.
    """

    reader_sentence = "The assistant's reply was withheld; here are the engine's figures."

    def __init__(self, codes: tuple[str, ...]) -> None:
        super().__init__("blocked by a safety rule: " + ", ".join(codes))
        self.codes = codes


class PromptInjectionBlocked(SafetyRefusal):
    """The prompt carried text that tries to instruct the model. It was not sent."""

    reader_sentence = "This request was not sent to the assistant; here are the engine's figures."


class OutputWithheld(SafetyRefusal):
    """The model's reply broke an output rule. What was already shown was clean; the rest was dropped."""

    reader_sentence = "The rest of the assistant's reply was withheld by the output policy; here are the engine's figures."
