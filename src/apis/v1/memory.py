import asyncio
import logging

from fastapi import APIRouter, BackgroundTasks, status

from schemas.conversation import ConversationIn
from layers.l1 import storage as l1

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/memory", tags=["memory"])


async def _store_conversation(data: ConversationIn, delay: float = 0) -> None:
    try:
        if delay > 0:
            logger.info(f"Simulating slow task ({delay}s)...")
            await asyncio.sleep(delay)
        await l1.store(data.user_id, data.human_message, data.ai_message)
        logger.info(f"Conversation stored for user={data.user_id}")
    except Exception:
        logger.exception("Failed to store conversation")


@router.post("/conversations", status_code=status.HTTP_201_CREATED)
async def create_conversation(
    data: ConversationIn,
    background_tasks: BackgroundTasks,
    delay: float = 5,
):
    """Backend에서 호출 → 즉시 201 반환, 백그라운드로 저장.

    Args:
        delay: 테스트용. graceful shutdown 검증 시 초 단위 지연값 전달.
    """
    background_tasks.add_task(_store_conversation, data, delay)
    return {"status": "accepted"}
