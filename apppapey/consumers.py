import json
import asyncio
from channels.generic.websocket import AsyncWebsocketConsumer

MAX_PLAYERS_PER_ROOM = 10
BROADCAST_HZ = 20  # position updates per second

rooms = {}  # room_name -> { player_id -> player_dict }

# ── helpers ───────────────────────────────────────────────────────────────────

def total_players_online():
    return sum(len(p) for p in rooms.values())

def find_room():
    open_rooms = [(name, players) for name, players in rooms.items()
                  if 0 < len(players) < MAX_PLAYERS_PER_ROOM]
    if open_rooms:
        return min(open_rooms, key=lambda r: len(r[1]))[0]
    new_name = f"room{len(rooms) + 1}"
    rooms[new_name] = {}
    return new_name

_next_id = 0
def make_player_id():
    global _next_id
    _next_id += 1
    return str(_next_id)

# ── broadcast loop (one per room, runs as an asyncio task) ────────────────────

room_tasks = {}  # room_name -> asyncio.Task

async def room_broadcast_loop(room_name, channel_layer):
    """Broadcast positions + trails at BROADCAST_HZ; skips territory PNGs."""
    try:
        while room_name in rooms and rooms[room_name]:
            players = rooms.get(room_name, {})
            if players:
                snapshot = {
                    pid: {
                        "x":            p["x"],
                        "y":            p["y"],
                        "trail":        p["trail"],
                        "filledPixels": p["filledPixels"],
                    }
                    for pid, p in players.items()
                }
                await channel_layer.group_send(room_name, {
                    "type": "game_positions",
                    "snapshot": snapshot,
                })
            await asyncio.sleep(1 / BROADCAST_HZ)
    finally:
        room_tasks.pop(room_name, None)

# ── consumer ──────────────────────────────────────────────────────────────────

class GameConsumer(AsyncWebsocketConsumer):

    # ── lifecycle ─────────────────────────────────────────────────────────────

    async def connect(self):
        self.player_id = make_player_id()
        self.room_name = find_room()

        await self.channel_layer.group_add(self.room_name, self.channel_name)
        await self.accept()

        # Register this player
        rooms[self.room_name][self.player_id] = {
            "x": 500, "y": 500,
            "trail": [],
            "filledPixels": 100,
            "territoryPng": None,  # stored server-side; only sent to newcomers
        }

        # Send identity + full state of existing players (including territory PNGs
        # so the newcomer can render everyone's filled zones from the start)
        existing = {
            pid: {k: v for k, v in pdata.items()}
            for pid, pdata in rooms[self.room_name].items()
            if pid != self.player_id
        }
        await self.send(text_data=json.dumps({
            "myId":        self.player_id,
            "room":        self.room_name,
            "totalOnline": total_players_online(),
            "existing":    existing,
        }))

        # Also tell the new player the totalOnline count (caught by lobby peek too)
        await self.send(text_data=json.dumps({"totalOnline": total_players_online()}))

        # Start the room's broadcast loop if not already running
        if self.room_name not in room_tasks or room_tasks[self.room_name].done():
            task = asyncio.create_task(
                room_broadcast_loop(self.room_name, self.channel_layer)
            )
            room_tasks[self.room_name] = task

    async def disconnect(self, close_code):
        room_players = rooms.get(self.room_name, {})
        room_players.pop(self.player_id, None)

        await self.channel_layer.group_discard(self.room_name, self.channel_name)

        if not room_players:
            rooms.pop(self.room_name, None)
        else:
            # Notify remaining players that this player left
            await self.channel_layer.group_send(self.room_name, {
                "type": "player_left",
                "player_id": self.player_id,
            })

    async def receive(self, text_data):
        data = json.loads(text_data)
        room_players = rooms.get(self.room_name)
        if not room_players or self.player_id not in room_players:
            return

        p = room_players[self.player_id]
        p["x"]    = data.get("x", p["x"])
        p["y"]    = data.get("y", p["y"])
        p["trail"] = data.get("trail", p["trail"])
        if "filledPixels" in data:
            p["filledPixels"] = data["filledPixels"]

        # Territory PNG — only sent after a fill, forward immediately (it's big,
        # don't include it in the normal broadcast loop)
        if "territoryPng" in data:
            p["territoryPng"] = data["territoryPng"]
            await self.channel_layer.group_send(self.room_name, {
                "type":         "territory_update",
                "player_id":    self.player_id,
                "territoryPng": data["territoryPng"],
            })

    # ── group message handlers ────────────────────────────────────────────────

    async def game_positions(self, event):
        """Periodic position broadcast — sent to every player in the room."""
        await self.send(text_data=json.dumps(event["snapshot"]))

    async def territory_update(self, event):
        """Fired once when a player fills territory; skip sending to the filler."""
        if event["player_id"] == self.player_id:
            return
        await self.send(text_data=json.dumps({
            "__territory__": event["player_id"],
            "territoryPng":  event["territoryPng"],
        }))

    async def player_left(self, event):
        """Notify clients that a player disconnected."""
        await self.send(text_data=json.dumps({
            "__left__": event["player_id"],
        }))