import json
import logging
from typing import Dict, List, Set
from fastapi import WebSocket

logger = logging.getLogger("smart_ambulance.ws")

class ConnectionManager:
    def __init__(self):
        # Channels maps
        self.trip_connections: Dict[int, Set[WebSocket]] = {}
        self.driver_connections: Dict[int, Set[WebSocket]] = {}
        self.hospital_connections: Dict[int, Set[WebSocket]] = {}
        self.traffic_connections: Set[WebSocket] = set()
        self.admin_connections: Set[WebSocket] = set()

    async def connect_trip(self, trip_id: int, websocket: WebSocket):
        await websocket.accept()
        if trip_id not in self.trip_connections:
            self.trip_connections[trip_id] = set()
        self.trip_connections[trip_id].add(websocket)
        logger.info(f"WebSocket connected to trip channel {trip_id}")

    def disconnect_trip(self, trip_id: int, websocket: WebSocket):
        if trip_id in self.trip_connections:
            self.trip_connections[trip_id].discard(websocket)
            if not self.trip_connections[trip_id]:
                del self.trip_connections[trip_id]

    async def connect_driver(self, driver_id: int, websocket: WebSocket):
        await websocket.accept()
        if driver_id not in self.driver_connections:
            self.driver_connections[driver_id] = set()
        self.driver_connections[driver_id].add(websocket)
        logger.info(f"WebSocket connected to driver channel {driver_id}")

    def disconnect_driver(self, driver_id: int, websocket: WebSocket):
        if driver_id in self.driver_connections:
            self.driver_connections[driver_id].discard(websocket)
            if not self.driver_connections[driver_id]:
                del self.driver_connections[driver_id]

    async def connect_hospital(self, hospital_id: int, websocket: WebSocket):
        await websocket.accept()
        if hospital_id not in self.hospital_connections:
            self.hospital_connections[hospital_id] = set()
        self.hospital_connections[hospital_id].add(websocket)

    def disconnect_hospital(self, hospital_id: int, websocket: WebSocket):
        if hospital_id in self.hospital_connections:
            self.hospital_connections[hospital_id].discard(websocket)
            if not self.hospital_connections[hospital_id]:
                del self.hospital_connections[hospital_id]

    async def connect_traffic(self, websocket: WebSocket):
        await websocket.accept()
        self.traffic_connections.add(websocket)

    def disconnect_traffic(self, websocket: WebSocket):
        self.traffic_connections.discard(websocket)

    async def connect_admin(self, websocket: WebSocket):
        await websocket.accept()
        self.admin_connections.add(websocket)

    def disconnect_admin(self, websocket: WebSocket):
        self.admin_connections.discard(websocket)

    # Broadcast Methods
    async def broadcast_to_trip(self, trip_id: int, message: dict):
        if trip_id in self.trip_connections:
            dead_sockets = set()
            payload = json.dumps(message, default=str)
            for socket in list(self.trip_connections[trip_id]):
                try:
                    await socket.send_text(payload)
                except Exception as e:
                    logger.warning(f"Error sending to trip socket: {e}")
                    dead_sockets.add(socket)
            for ds in dead_sockets:
                self.trip_connections[trip_id].discard(ds)

    async def notify_driver(self, driver_id: int, message: dict):
        if driver_id in self.driver_connections:
            dead_sockets = set()
            payload = json.dumps(message, default=str)
            for socket in list(self.driver_connections[driver_id]):
                try:
                    await socket.send_text(payload)
                except Exception as e:
                    logger.warning(f"Error sending to driver socket: {e}")
                    dead_sockets.add(socket)
            for ds in dead_sockets:
                self.driver_connections[driver_id].discard(ds)

    async def notify_hospital(self, hospital_id: int, message: dict):
        if hospital_id in self.hospital_connections:
            dead_sockets = set()
            payload = json.dumps(message, default=str)
            for socket in list(self.hospital_connections[hospital_id]):
                try:
                    await socket.send_text(payload)
                except Exception as e:
                    logger.warning(f"Error sending to hospital socket: {e}")
                    dead_sockets.add(socket)
            for ds in dead_sockets:
                self.hospital_connections[hospital_id].discard(ds)

    async def broadcast_traffic(self, message: dict):
        dead_sockets = set()
        payload = json.dumps(message, default=str)
        for socket in list(self.traffic_connections):
            try:
                await socket.send_text(payload)
            except Exception as e:
                dead_sockets.add(socket)
        for ds in dead_sockets:
            self.traffic_connections.discard(ds)

    async def broadcast_admin(self, message: dict):
        dead_sockets = set()
        payload = json.dumps(message, default=str)
        for socket in list(self.admin_connections):
            try:
                await socket.send_text(payload)
            except Exception as e:
                dead_sockets.add(socket)
        for ds in dead_sockets:
            self.admin_connections.discard(ds)

manager = ConnectionManager()
