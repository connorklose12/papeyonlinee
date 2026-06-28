import json
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
            # list of past fills: each is {trail, x, y} so late joiners can replay
            "fills": [],
        }

        # Tell this player their ID and give them existing players' state + fill history
        existing = {}
        for pid, pdata in rooms[self.room_name].items():
            if pid != self.player_id:
                existing[pid] = {
                    "x": pdata["x"],
                    "y": pdata["y"],
                    "trail": pdata["trail"],
                    "fills": pdata["fills"],
                }

        await self.send(text_data=json.dumps({
            "myId": self.player_id,
            "room": self.room_name,
            "totalOnline": total_players_online(),
            "existing": existing,
        }))
        await self.broadcast_positions()

    async def disconnect(self, close_code):
        room_players = rooms.get(self.room_name, {})
        room_players.pop(self.player_id, None)
        await self.channel_layer.group_discard(self.room_name, self.channel_name)
        if not room_players:
            rooms.pop(self.room_name, None)
        else:
            await self.channel_layer.group_send(self.room_name, {
                "type": "game_message",
                "data": {"__left__": self.player_id},
            })

    async def receive(self, text_data):
        data = json.loads(text_data)
        room_players = rooms.get(self.room_name)
        if not room_players or self.player_id not in room_players:
            return

        p = room_players[self.player_id]

        if data.get("type") == "fill":
            # Store fill so late joiners can replay it
            fill_record = {"trail": data["trail"], "x": data["x"], "y": data["y"]}
            p["fills"].append(fill_record)
            p["trail"] = []
            p["x"] = data["x"]
            p["y"] = data["y"]
            # Broadcast fill event to everyone in the room
            await self.channel_layer.group_send(self.room_name, {
                "type": "game_message",
                "data": {
                    "__fill__": {
                        "id": self.player_id,
                        "trail": data["trail"],
                        "x": data["x"],
                        "y": data["y"],
                    }
                },
            })
        else:
            # Normal position update
            p["x"] = data["x"]
            p["y"] = data["y"]
            p["trail"] = data["trail"]
            await self.broadcast_positions()

    async def broadcast_positions(self):
        room_players = rooms.get(self.room_name, {})
        positions = {
            pid: {"x": pd["x"], "y": pd["y"], "trail": pd["trail"]}
            for pid, pd in room_players.items()
        }
        await self.channel_layer.group_send(self.room_name, {
            "type": "game_message",
            "data": {"__positions__": positions},
        })

    async def game_message(self, event):
        await self.send(text_data=json.dumps(event["data"]))