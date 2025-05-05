# Placeholder for DestinyAgentService class

import os
from agents import Agent, Runner, function_tool
from .weapon_api import WeaponAPI # Use relative import
from .catalyst import CatalystAPI # Use relative import
from .manifest import ManifestManager # Use relative import
import logging
import functools # Import functools
import asyncio # Import asyncio

logger = logging.getLogger(__name__)

# --- Tool Implementation Functions (outside class) ---

def _get_user_info_impl(service: 'DestinyAgentService') -> dict:
    """(Implementation) Fetch the user's Destiny membership info."""
    logger.debug("Agent Tool Impl: get_user_info called")
    if not service._current_access_token:
        logger.error("Agent Tool Impl Error: Access token not set in get_user_info")
        raise Exception("Access token not available for get_user_info.")
    try:
        info = service.weapon_api.get_membership_info(service._current_access_token)
        if not info:
            raise Exception("Could not fetch user info. Check access token or Bungie API status.")
        logger.debug(f"Agent Tool Impl: get_user_info returning: {info}")
        return info
    except Exception as e:
        logger.error(f"Agent Tool Impl Error in get_user_info: {e}", exc_info=True)
        raise

def _get_weapons_impl(service: 'DestinyAgentService', membership_type: int, membership_id: str) -> list:
    """(Implementation) Fetch all weapons for a user."""
    logger.debug(f"Agent Tool Impl: get_weapons called with type={membership_type}, id={membership_id}")
    if not service._current_access_token:
        logger.error("Agent Tool Impl Error: Access token not set in get_weapons")
        raise Exception("Access token not available for get_weapons.")
    try:
        weapons = service.weapon_api.get_all_weapons(
            access_token=service._current_access_token, 
            membership_type=membership_type, 
            destiny_membership_id=membership_id
        )
        weapons_dict = [w.model_dump() if hasattr(w, 'model_dump') else w.__dict__ if hasattr(w, '__dict__') else w for w in weapons]
        logger.debug(f"Agent Tool Impl: get_weapons returning {len(weapons_dict)} items")
        return weapons_dict
    except Exception as e:
        logger.error(f"Agent Tool Impl Error in get_weapons: {e}", exc_info=True)
        raise

def _get_catalysts_impl(service: 'DestinyAgentService') -> list:
    """(Implementation) Fetch all catalyst progress for a user."""
    logger.debug("Agent Tool Impl: get_catalysts called")
    if not service._current_access_token:
        logger.error("Agent Tool Impl Error: Access token not set in get_catalysts")
        raise Exception("Access token not available for get_catalysts.")
    try:
        catalysts_data = service.catalyst_api.get_catalysts(service._current_access_token)
        logger.debug(f"Agent Tool Impl: get_catalysts returning {len(catalysts_data)} items")
        return catalysts_data
    except Exception as e:
        logger.error(f"Agent Tool Impl Error in get_catalysts: {e}", exc_info=True)
        raise

# --- Agent Service Class ---

class DestinyAgentService:
    def __init__(self, bungie_api_key: str, openai_api_key: str, manifest_manager: ManifestManager):
        if not openai_api_key:
            raise ValueError("OpenAI API key is required for DestinyAgentService")
        
        logger.info("Initializing DestinyAgentService...")
        self.bungie_api_key = bungie_api_key
        self.openai_api_key = openai_api_key # Store OpenAI key if needed later for client
        self.manifest_manager = manifest_manager
        
        # Initialize API clients within the service
        self.weapon_api = WeaponAPI(api_key=self.bungie_api_key, manifest_manager=self.manifest_manager)
        self.catalyst_api = CatalystAPI(api_key=self.bungie_api_key, manifest_manager=self.manifest_manager)
        
        # Placeholder for the access token needed by tools during a run
        self._current_access_token: str | None = None 
        
        # Define the agent (tools will be added later)
        self.agent = self._create_agent()
        logger.info("DestinyAgentService initialized.")

    def _create_agent(self) -> Agent:
        """Creates the Agent instance with instructions and tools."""
        
        # Create partials first (these hold the 'self' context)
        partial_get_user_info = functools.partial(_get_user_info_impl, service=self)
        partial_get_weapons = functools.partial(_get_weapons_impl, service=self)
        partial_get_catalysts = functools.partial(_get_catalysts_impl, service=self)

        # Now, define wrapper functions that call the partials.
        # Decorate these wrappers with @function_tool.
        
        @function_tool
        def get_user_info_tool() -> dict:
            """Fetch the user's Destiny membership info (type and id) from Bungie."""
            return partial_get_user_info()

        @function_tool
        def get_weapons_tool(membership_type: int, membership_id: str) -> list:
            """Fetch all weapons for a user from Bungie given their membership type and id."""
            return partial_get_weapons(membership_type=membership_type, membership_id=membership_id)
        
        @function_tool
        def get_catalysts_tool() -> list:
            """Fetch all catalyst progress for a user from Bungie."""
            return partial_get_catalysts()

        # The agent needs the decorated wrapper functions
        agent_tools = [
            get_user_info_tool, 
            get_weapons_tool, 
            get_catalysts_tool
        ]
        
        agent = Agent(
            name="Destiny2Agent",
            instructions=(
                "You are a Destiny 2 assistant. Use the tools to fetch user info, weapons, and catalysts as needed. "
                "When using the get_weapons tool, you MUST first use the get_user_info tool to get the required membership_type and membership_id. "
                "When presenting catalyst information, list completed catalysts separately from incomplete ones. "
                "For incomplete catalysts, ALWAYS include the specific objective description(s) along with the progress (e.g., 'Targets defeated: 150/500'). Do not just show a percentage."
            ),
            tools=agent_tools,
        )
        return agent

    # --- Run Method (now async) ---
    
    async def run_chat(self, prompt: str, access_token: str) -> str:
        """Runs the agent asynchronously for a given prompt and access token."""
        if not self.agent:
             logger.error("Agent not initialized in DestinyAgentService.")
             return "Error: Agent is not available."
        if not access_token:
             logger.error("Access token missing in run_chat.")
             return "Error: Authentication token is missing."

        # Set the access token for this specific run
        self._current_access_token = access_token 
        
        try:
            logger.info(f"Running agent async for prompt: '{prompt[:50]}...' Access token set.")
            # Use await Runner.run()
            result = await Runner.run(self.agent, prompt) 
            final_output = result.final_output if result else "(No response)"
            logger.info("Agent run completed.")
            return final_output
            
        except Exception as e:
            logger.error(f"Error during agent run: {e}", exc_info=True)
            return f"Error processing your request: {e}"
        finally:
             # Clear the token after the run
            self._current_access_token = None 