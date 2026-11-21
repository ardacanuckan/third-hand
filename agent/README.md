# agent/ · BRAIN workstream

Owner: BRAIN. The MCP server and everything Claude needs to run the build: tools, instructions, vision checks, the board planner.

Deliverables B1–B6 are in [docs/05-team-plan.md](../docs/05-team-plan.md); the tool list is in [docs/06-contracts.md](../docs/06-contracts.md).

Suggested layout:

```
agent/
  server.py          B2  MCP server (start from the June winner's station_mcp.py, credit them)
  instructions.md    B2  appended to Claude Code with --append-system-prompt
  planner.py         B3  pick-and-place + BOM -> contracts/build_plan.json
  vision.py          B4  cup check (side camera), joint classifier (wrist camera)
  eval_vision.py     B4  scores vision.py on board/photos
  recovery.py        B5  retry rules and spoken explanations
```

Run Claude Code against the server with the MCP config in this folder, and restart the session after editing the server (it does not hot-reload).
