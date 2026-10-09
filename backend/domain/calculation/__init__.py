"""Pure calculation. No I/O, no framework, no persistence.

Everything in this package is deterministic: same inputs, same rules, same
bytes out. That property is what makes a run replayable years later when a
return is examined, and it is why these modules may not import from `api`,
`infrastructure`, or `data`.

- `onezero`    the statutory One/Zero engine — Min Max and Pay Period methods
- `headcount`  the shared definition of which rows a state-year is computed from
- `proximity`  distance from the statutory line, and the lever that closes it
- `trail`      the derivation record every figure carries

The certified figures (10,236 / 539 / 656) flow through `onezero`. Changing
behaviour here changes filed numbers.
"""
