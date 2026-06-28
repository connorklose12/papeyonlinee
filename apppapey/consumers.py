import json
import base64
from channels.generic.websocket import AsyncWebsocketConsumer

MAX_PLAYERS_PER_ROOM = 10
rooms = {}

def total_players_online():
    return sum(len(players) for players in rooms.values())

def find_room_for_new_player():
    open_rooms = [(name, players) for name, players in rooms.items()
                  if len(players) < MAX_PLAYERS_PER_ROOM]
    if open_rooms:
        name, _ = min(open_rooms, key=lambda r: len(r[1]))
        return name
    new_name = f"room{len(rooms) + 1}"
    rooms[new_name] = {}
    return new_name

_next_id = 0
def make_player_id():
    global _next_id
    _next_id += 1
    return str(_next_id)


class GameConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.player_id = make_player_id()
        self.room_name = find_room_for_new_player()

        await self.channel_layer.group_add(self.room_name, self.channel_name)
        await self.accept()

        rooms[self.room_name][self.player_id] = {
            "x": 250, "y": 250, "trail": [],
            # base64-encoded PNG of this player's territory canvas (sent on fill)
            "territoryPng": None,
            "filledPixels": 100,
        }

        # Send this player their ID + the full current state of all existing players
        existing = {
            pid: {k: v for k, v in pdata.items()}
            for pid, pdata in rooms[self.room_name].items()
            if pid != self.player_id
        }
        await self.send(text_data=json.dumps({
            "myId": self.player_id,
            "room": self.room_name,
            "totalOnline": total_players_online(),
            "existing": existing,  # full state including territory PNGs
        }))
        await self.broadcast()

    async def disconnect(self, close_code):
        room_players = rooms.get(self.room_name, {})
        room_players.pop(self.player_id, None)
        await self.channel_layer.group_discard(self.room_name, self.channel_name)
        if not room_players:
            rooms.pop(self.room_name, None)
        else:
            await self.channel_layer.group_send(self.room_name, {
                "type": "game_update",
                "players": rooms.get(self.room_name, {}),
                "left": self.player_id,
            })

    async def receive(self, text_data):
        data = json.loads(text_data)
        room_players = rooms.get(self.room_name)
        if room_players and self.player_id in room_players:
            p = room_players[self.player_id]
            p["x"] = data["x"]
            p["y"] = data["y"]
            p["trail"] = data["trail"]
            if "territoryPng" in data:
                p["territoryPng"] = data["territoryPng"]
            if "filledPixels" in data:
                p["filledPixels"] = data["filledPixels"]
        await self.broadcast()

    async def broadcast(self):
        await self.channel_layer.group_send(self.room_name, {
            "type": "game_update",
            "players": rooms.get(self.room_name, {}),
        })

    async def game_update(self, event):
        players = event["players"]
        out = {}
        for pid, pdata in players.items():
            out[pid] = {k: v for k, v in pdata.items()}
        if "left" in event:
            out["__left__"] = event["left"]
        await self.send(text_data=json.dumps(out))