import os
import asyncio
from agents.mcp import MCPServerStdio
from agents import Agent, Runner

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
        for tool in tools:
            print("-", tool.name, '-', tool.description)
            # For debugging, you can also print: print(vars(tool))

        agent = Agent(
            name="MCP Agent",
            instructions="You are a helpful assistant with access to Supabase tools.",
            mcp_servers=[supabase_server],
        )

        print("Type 'exit' or 'quit' to end the conversation.")
        while True:
            user_input = input("You: ").strip()
            if user_input.lower() in {"exit", "quit"}:
                print("Exiting conversation.")
                break
            result = await Runner.run(agent, input=user_input)
            print("Agent:", result)

if __name__ == "__main__":
    asyncio.run(main()) 