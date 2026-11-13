"""The program catalog capability's catalog entry: one read, list and detail. [F05.11]

Split from `catalog` by size, like `catalog_runs`. `program_catalog` names no client and takes at most a program code: omit it
for the list, give it for one program. It reads the registry and the packs through the same queries as the portal's Program
manager, so the channel and the page cannot disagree. Drafts are not here: a draft is a proposal with no runtime authority and
no agent can see one.
"""
from __future__ import annotations

from application.capabilities.catalog_types import CapabilitySpec, _read

PROGRAM_READS: tuple[CapabilitySpec, ...] = (
    _read(
        "program_catalog",
        "The programs the platform knows: lifecycle, authored tax years, whether each can be calculated and why not, and engagement "
        "counts. Omit program_code for the list; give it for one program's pack, years and what blocks calculation. Names no client. "
        "Every program is NOT VERIFIED: say so, and never call a program's statute values correct.",
        {"program_code": {"type": "string", "maxLength": 64, "description": "A program code such as GA_JTC. Omit to list every program."}},
        needs_client=False,
    ),
)
