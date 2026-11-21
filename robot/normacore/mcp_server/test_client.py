"""Start the server in fake mode over stdio (like Claude does), list its tools and call each one.

    uv run --project robot/normacore/mcp_server python robot/normacore/mcp_server/test_client.py [episode.parquet]
"""
import asyncio
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

HERE = Path(__file__).resolve().parent


async def main():
    params = StdioServerParameters(command=sys.executable, args=[str(HERE / "server.py")],
                                   env={**os.environ, "THIRD_HAND_FAKE": "1"})
    async with stdio_client(params) as (r, w), ClientSession(r, w) as s:
        await s.initialize()
        tools = (await s.list_tools()).tools
        print("tools:", ", ".join(t.name for t in tools))

        async def call(name, **args):
            res = await s.call_tool(name, args)
            text = " ".join(getattr(c, "text", f"<{c.type}>") for c in res.content)
            print(f"\n> {name}({args})\n{text[:900]}")
            return text

        await call("arm_status")
        await call("list_skills")
        await call("give_me", object="a red LED")                 # untrained: must refuse
        await call("give_me", object="the glue stick please")
        await call("perform", character="butler", move="bow")
        await call("go_to", pose="handover")
        await call("hand_over", timeout_s=8)
        await call("gripper", action="close")
        await call("go_to", pose="home")
        await call("describe_last_motion")
        await call("look", camera="wrist")
        await call("stop")
        if len(sys.argv) > 1:
            await call("describe_recording", path=sys.argv[1])


asyncio.run(main())
