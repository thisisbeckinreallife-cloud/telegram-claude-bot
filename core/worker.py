"""Task queue y worker pool para procesar mensajes asíncronamente.

- TASK_QUEUE: asyncio.Queue global de Tasks.
- task_worker_loop: corutina consumidora (se lanzan N instancias en bot.py).
- enqueue_task: helper para handlers.
"""
import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

logger = logging.getLogger(__name__)


@dataclass
class Task:
    chat_id: int
    handler: Callable[..., Awaitable[None]]
    args: tuple
    kwargs: dict


TASK_QUEUE: asyncio.Queue[Task] = asyncio.Queue()


async def enqueue_task(chat_id: int, handler, *args, **kwargs) -> None:
    await TASK_QUEUE.put(Task(chat_id, handler, args, kwargs))


async def task_worker_loop(worker_id: int) -> None:
    logger.info("Worker %d arrancado", worker_id)
    while True:
        task = await TASK_QUEUE.get()
        try:
            await task.handler(*task.args, **task.kwargs)
        except Exception:
            logger.exception("Worker %d crash en task chat=%d", worker_id, task.chat_id)
        finally:
            TASK_QUEUE.task_done()
