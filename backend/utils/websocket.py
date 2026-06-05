from typing import List, Dict
from fastapi import WebSocket
from datetime import datetime
import json


class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def send_personal_message(self, message: dict, websocket: WebSocket):
        try:
            await websocket.send_json(message)
        except Exception as e:
            print(f"发送个人消息失败: {e}")

    async def broadcast(self, message: dict):
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                print(f"广播消息失败: {e}")
                disconnected.append(connection)
        for conn in disconnected:
            self.disconnect(conn)

    async def broadcast_alarm(self, alarm_data: dict):
        await self.broadcast({
            "type": "alarm",
            "data": alarm_data,
            "timestamp": datetime.utcnow().isoformat()
        })

    async def broadcast_device_update(self, device_data: dict):
        await self.broadcast({
            "type": "device_update",
            "data": device_data,
            "timestamp": datetime.utcnow().isoformat()
        })


manager = ConnectionManager()
