from typing import Dict
from fastapi import WebSocket

class ConnectionManager:
    """Manages active real-time WebSocket connections between ATM screens and the server."""
    def __init__(self):
        # Map session_id -> WebSocket
        self.active_connections: Dict[str, WebSocket] = {}

    async def connect(self, session_id: str, websocket: WebSocket):
        await websocket.accept()
        self.active_connections[session_id] = websocket

    def disconnect(self, session_id: str):
        if session_id in self.active_connections:
            del self.active_connections[session_id]

    async def send_event(self, session_id: str, data: dict):
        if session_id in self.active_connections:
            websocket = self.active_connections[session_id]
            await websocket.send_json(data)
            return True
        return False

manager = ConnectionManager()

