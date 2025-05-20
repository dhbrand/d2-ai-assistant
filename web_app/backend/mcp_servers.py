import os
import asyncio
import json
from agents.mcp import MCPServerStdio
from agents import Agent, Runner

# --- Debug patch for invoke_mcp_tool ---
from agents.mcp.util import MCPUtil

original_invoke = MCPUtil.invoke_mcp_tool

def debug_invoke_mcp_tool(server, tool, context, input_json):
    print("\n[DEBUG] MCP Tool Call:")
    print("  Tool name:", tool.name)
    print("  Server endpoint:", getattr(server, 'endpoint_url', 'stdio'))
    # Robustly extract the context dict
    context_dict = None
    if hasattr(context, 'context'):
        inner = getattr(context, 'context')
        if isinstance(inner, dict):
            context_dict = inner
        elif hasattr(inner, 'context'):
            context_dict = getattr(inner, 'context')
    if context_dict is not None:
        print("  tool_context.context:", context_dict)
    else:
        print("  tool_context.context: <not found>")
    payload = {
        "tool_input": input_json,
        "tool_context": {
            "tool_name": tool.name,
            "invocation_id": getattr(context, 'invocation_id', None),
            "agent_name": getattr(context, 'agent_name', None),
            "context": context_dict
        }
    }
    print("  Payload:", json.dumps(payload, indent=2))
    return original_invoke(server, tool, context, input_json)

MCPUtil.invoke_mcp_tool = debug_invoke_mcp_tool
# --- End debug patch ---

SUPABASE_ACCESS_TOKEN = os.getenv("SUPABASE_ACCESS_TOKEN", "<your-personal-access-token>")

async def main():
    # Launch the Supabase MCP server as a subprocess
    async with MCPServerStdio(
        params={
            "command": "npx",
            "args": [
                "-y",
                "@supabase/mcp-server-supabase@latest",
                "--access-token",
                SUPABASE_ACCESS_TOKEN,
            ],
        }
    ) as supabase_server:
        print("Supabase MCP server launched.")
        tools = await supabase_server.list_tools()
        print("Available tools from Supabase MCP:")
        # for tool in tools:
        #     print("-", tool.name, '-', tool.description)
            # For debugging, you can also print: print(vars(tool))

        agent = Agent(
            name="MCP Agent",
            instructions=(
                "You are a helpful assistant with access to Supabase tools via MCP.\n"
                "- You are given a context object that includes a `user_uuid`, which is a valid UUID.\n"
                "- When generating SQL queries, you MUST extract the actual UUID from the context and interpolate it into the query.\n"
                "- Do NOT use hardcoded UUIDs. Do NOT use placeholders like 'user_uuid'.\n"
                "- Also, NEVER use invalid UUIDs like 'abcd-1234'.\n"
                "- Example of correct usage (with a fake UUID, do not copy):\n"
                "  SELECT * FROM user_weapon_inventory WHERE user_id = '0f4e9f63-0e9c-4567-987d-0c8b0c5d8f11'\n"
                "- Again, this is only an example — always use the UUID from context.user_uuid.\n"
                "- The query should end with a semicolon if needed, but never insert semicolons inside quoted values.\n"
                "- Repeat back the UUID you used in your response to confirm you're using context correctly."
            ),
            mcp_servers=[supabase_server]
        )

        print("Type 'exit' or 'quit' to end the conversation.")
        while True:
            user_input = input("You: ").strip()
            if user_input.lower() in {"exit", "quit"}:
                print("Exiting conversation.")
                break
            context = {"user_uuid": "e4122dcd-f5e8-47fb-83c7-effb7176261b", "debug": True}
            print("[DEBUG] Sending context to agent:", context)
            result = await Runner.run(agent, input=user_input, context=context)
            print("Agent:", result)

if __name__ == "__main__":
    asyncio.run(main()) 