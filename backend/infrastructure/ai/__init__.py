"""Model-access adapters: the ONLY place SDKs and HTTP model calls live. [AI-02]

`tests/test_architecture.py` fails the build if an SDK (`agent_framework*`,
`azure.ai.*`, `openai`) or `httpx` for a model call is imported anywhere else.
Each adapter implements one port from `application/ai/ports.py`.
"""
