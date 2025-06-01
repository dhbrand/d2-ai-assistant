"""
common_agent_tools.py

Shared tools for all Destiny 2 agents (e.g., web search, utilities).
Import COMMON_AGENT_TOOLS in any agent module to access these tools.
"""
import os
from langchain_community.tools.tavily_search import TavilySearchResults

# Tavily Web Search Tool
TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY")
if not TAVILY_API_KEY:
    raise RuntimeError("TAVILY_API_KEY must be set in the environment.")

tavily_search_tool = TavilySearchResults(api_key=TAVILY_API_KEY)

COMMON_AGENT_TOOLS = [
    tavily_search_tool,
] 