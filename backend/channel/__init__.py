"""The channel gateway: the only new public surface of the M365 channel. [CH-06, ADR-008]

A third FastAPI app (`channel.main:app`) that authenticates a caller, checks what it
may do, audits every call per user and passes the call to the API, where the Gold
reads and sealed runs are warm. It holds no business rule: it imports the catalog,
the envelope types, the audit port and the numeric guard, and nothing that
calculates.
"""
