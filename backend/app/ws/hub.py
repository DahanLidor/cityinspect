"""
WebSocket connection hub with basic role-based filtering.
"""
from __future__ import annotations

import json
from typing import Dict, List, Optional

from fastapi import WebSocket

from app.core.logging import get_logger

logger = get_logger(__name__)


class WSHub:
    """Manages active WebSocket connections and broadcasts events."""

    def __init__(self) -> None:
        # Maps websocket → metadata dict (role, user_id)
        self._connections: Dict[WebSocket, dict] = {}

    async def connect(self, ws: WebSocket, user_id: Optional[int] = None, role: str = "viewer") -> None:
        await ws.accept()
        self._connections[ws] = {"user_id": user_id, "role": role}
        logger.info("WS connected", extra={"user_id": user_id, "role": role, "total": len(self._connections)})

    def disconnect(self, ws: WebSocket) -> None:
        self._connections.pop(ws, None)

    async def broadcast(self, data: dict, min_role: Optional[str] = None) -> None:
        """
        Send JSON data to all connected clients.
        Optional min_role: only send to clients whose role is in the allowed set.
        """
        role_order = {"viewer": 0, "field_team": 1, "admin": 2}
        allowed_floor = role_order.get(min_role, 0) if min_role else 0

        dead: List[WebSocket] = []
        payload = json.dumps(data, ensure_ascii=False, default=str)

        for ws, meta in list(self._connections.items()):
            if role_order.get(meta.get("role", "viewer"), 0) < allowed_floor:
                continue
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)

        for ws in dead:
            self.disconnect(ws)
            logger.warning("Removed dead WS connection")

    @property
    def connection_count(self) -> int:
        return len(self._connections)


# Module-level singleton shared across the application
hub = WSHub()
