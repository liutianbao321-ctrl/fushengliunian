import asyncio
from collections import defaultdict
from typing import Any


class EventBus:
    def __init__(self) -> None:
        self._subscribers: dict[str, list[asyncio.Queue[dict[str, Any]]]] = defaultdict(list)

    async def publish(self, project_id: str, event: dict[str, Any]) -> None:
        for queue in list(self._subscribers[project_id]):
            await queue.put(event)

    async def subscribe(self, project_id: str) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._subscribers[project_id].append(queue)
        return queue

    def unsubscribe(self, project_id: str, queue: asyncio.Queue[dict[str, Any]]) -> None:
        subscribers = self._subscribers.get(project_id, [])
        if queue in subscribers:
            subscribers.remove(queue)
        if not subscribers and project_id in self._subscribers:
            del self._subscribers[project_id]


event_bus = EventBus()
