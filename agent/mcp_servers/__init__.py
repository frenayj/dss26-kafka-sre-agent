"""The agent's own MCP servers: Confluence and Slack.

PagerDuty and GitHub ship official MCP servers, which the agent connects to
directly (see :mod:`agent.mcp_clients`). Confluence and Slack don't have one
the agent can use as-is, so these two stdio servers own the tool contract the
prompts are written against and put guardrails around the vendor APIs.

Each server's tools sit on a back-end object. ``build_server(backend)`` returns
a FastMCP server over any back-end with the same methods; ``main()`` serves
the live one. The harness's offline test doubles (``harness/stubs/``) reuse
the same contract with fixture back-ends.
"""
