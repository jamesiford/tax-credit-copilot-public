"""The response composer and the pieces split out of it. [ADR-008]

`assemble` builds a reply from blocks plus a narration, `substitution` fills the narrator's
placeholders, `render` turns blocks into Markdown and a card structure, and `hedging` finds
approximation wording beside a figure. The names below are what every caller imports from
`application.composer`. Standard library only, and all of it is vendored into the orchestrator.
"""
from application.composer.assemble import Composed, compose  # noqa: F401 - the package's public surface
from application.composer.render import cards_payload, render_markdown  # noqa: F401
from application.composer.substitution import (  # noqa: F401
    PlaceholderError, narrator_brief, placeholders, substitute,
)
