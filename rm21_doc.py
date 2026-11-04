import re
from pathlib import Path

DOCS = [
    ("backend/application/agent_audit.py", "prompt_hash", "The digest the audit stores in place of the prompt, so a row names the prompt without keeping its text."),
    ("backend/application/ai/safety/injection.py", "letters_only", "The text reduced to a-z, so spacing, punctuation and digits cannot hide a phrase from the scan."),
    ("backend/application/auth_policy.py", "auth_tenant_id", "The tenant tokens must come from: `AUTH_TENANT_ID`, else the platform's `AZURE_TENANT_ID`."),
    ("backend/application/auth_policy.py", "anonymous_synthetic_allowed", "Anonymous access needs the explicit flag AND synthetic data, so a customer's data is never served unauthenticated."),
    ("backend/application/confirmations.py", "token_sha256", "The digest a confirmation is stored and looked up by; the token itself is shown once and never kept."),
    ("backend/application/identity.py", "set_ambient_principal", "Record who the current request acts for, so lower layers can authorize without the person being threaded through every call."),
    ("backend/application/identity.py", "ambient_principal", "The person the current request acts for, or None outside a request."),
    ("backend/application/open_year.py", "today", "The one clock read in this module, so a test can pin the date."),
    ("backend/application/warmup.py", "should_warm", "Warm only against the real lakehouse and only when not opted out: any other source has no slow start to hide."),
    ("backend/application/client_book.py", "is_placeholder_year", "Whether the year's statute is still marked to-verify; a year that cannot resolve is not a placeholder."),
    ("backend/application/commands/set_base_year.py", "recalculation_running", "Whether a re-run for this client is in flight, so a second base-year change is not started under it."),
    ("channel_orchestrator/app/main.py", "main", "Start the hosted agent: set up logging, then run the host. The root `main.py` calls this."),
    ("channel_orchestrator/app/core/state.py", "remember", "Keep a bounded history: each entry is cut to 500 characters and only the last few survive, because it is routing context, not a transcript."),
    ("channel_orchestrator/app/core/state.py", "forget", "Drop a conversation's state so a finished turn leaves nothing behind."),
    ("channel_orchestrator/app/core/gateway_client.py", "close", "Release the pooled HTTP connections at shutdown."),
    ("backend/channel/api_client.py", "close", "Release the pooled HTTP connections at shutdown."),
]

for rel, name, doc in DOCS:
    path = Path(rel)
    raw = path.read_bytes().decode("utf-8")
    eol = "\r\n" if "\r\n" in raw else "\n"
    lines = raw.split(eol)
    hits = [i for i, l in enumerate(lines) if re.match(rf"^(\s*)(async )?def {name}\(", l)]
    done = False
    for i in hits:
        j = i
        while not lines[j].rstrip().endswith(":"):
            j += 1
        nxt = lines[j + 1].strip()
        if nxt.startswith(('"""', "'''")):
            continue
        indent = re.match(r"^(\s*)", lines[i])[1] + "    "
        lines.insert(j + 1, f'{indent}"""{doc}"""')
        done = True
        break
    assert done, (rel, name)
    path.write_bytes(eol.join(lines).encode("utf-8"))
print("ok")
