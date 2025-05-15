import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any

# AsyncClient is the Supabase async client
from supabase import AsyncClient

async def log_api_performance(
    sb_client: AsyncClient,
    endpoint: str,
    operation: str,
    duration_ms: int,
    user_id: Optional[str] = None,
    request_id: Optional[str] = None,
    extra_data: Optional[Dict[str, Any]] = None,
    conversation_id: Optional[str] = None,
    message_id: Optional[str] = None
):
    """
    Logs profiling/timing data to the api_performance_logs table in Supabase.

    Args:
        sb_client (AsyncClient): The Supabase async client instance.
        endpoint (str): The API endpoint or function name.
        operation (str): Description of the operation (e.g., 'get_profile').
        duration_ms (int): Duration in milliseconds.
        user_id (str, optional): User or Bungie ID.
        request_id (str, optional): Correlate logs for a single request.
        extra_data (dict, optional): Any additional context (will be stored as JSONB).
        conversation_id (str, optional): Conversation UUID.
        message_id (str, optional): Message UUID.

    Example usage:
        import time
        start = time.time()
        ... # your API call or operation
        duration_ms = int((time.time() - start) * 1000)
        await log_api_performance(
            sb_client,
            endpoint="/api/assistants/chat",
            operation="get_profile",
            duration_ms=duration_ms,
            user_id=current_user.bungie_id,
            request_id=request_id,
            conversation_id=conversation_id,
            message_id=message_id,
            extra_data={"status": "success"}
        )
    """
    log_entry = {
        "id": str(uuid.uuid4()),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "endpoint": endpoint,
        "operation": operation,
        "duration_ms": duration_ms,
        "user_id": user_id,
        "request_id": request_id,
        "extra_data": extra_data or {},
        "conversation_id": conversation_id,
        "message_id": message_id,
    }
    await sb_client.table("api_performance_logs").insert(log_entry).execute() 