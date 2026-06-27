import json
from channels.generic.websocket import AsyncWebsocketConsumer

# Simple in-memory matchmaking: each room is just a string name like
# "room1", "room2", etc. rooms[name] is the dict of players in that room,
# keyed by channel name -> {"x":.., "y":.., "trail":[...]}.
MAX_PLAYERS_PER_ROOM = 10
rooms = {}


def total_players_online():
    """Used by the menu screen to show 'X players online' before joining."""
    return sum(len(players) for players in rooms.values())


def find_room_for_new_player():
    """Put the new player in whichever room has the fewest people, so
    rooms stay evenly loaded instead of filling one up before starting
    the next. Only opens a new room once every existing one is full."""
    open_rooms = [(name, players) for name, players in rooms.items() if len(players) < MAX_PLAYERS_PER_ROOM]
    if open_rooms:
        name, _ = min(open_rooms, key=lambda r: len(r[1]))
        return name
    new_name = f"room{len(rooms) + 1}"
    rooms[new_name] = {}
    return new_name


class GameConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.player_id = self.channel_name
        self.room_name = find_room_for_new_player()

        await self.channel_layer.group_add(self.room_name, self.channel_name)
        await self.accept()

        rooms[self.room_name][self.player_id] = {"x": 250, "y": 250, "trail": []}

        # tell the player their own id, their room, and how many people total are online
        await self.send(text_data=json.dumps({
            "myId": self.player_id,
            "room": self.room_name,
            "totalOnline": total_players_online(),
        }))
        await self.broadcast()

    async def disconnect(self, close_code):
        room_players = rooms.get(self.room_name, {})
        room_players.pop(self.player_id, None)
        await self.channel_layer.group_discard(self.room_name, self.channel_name)
        # clean up empty rooms so they can be reused
        if not room_players:
            rooms.pop(self.room_name, None)
        else:
            await self.broadcast()

    async def receive(self, text_data):
        data = json.loads(text_data)
        room_players = rooms.get(self.room_name)
        if room_players and self.player_id in room_players:
            room_players[self.player_id]["x"] = data["x"]
            room_players[self.player_id]["y"] = data["y"]
            room_players[self.player_id]["trail"] = data["trail"]
        await self.broadcast()

    async def broadcast(self):
        await self.channel_layer.group_send(self.room_name, {
            "type": "game_update",
            "players": rooms.get(self.room_name, {}),
        })

    async def game_update(self, event):
        await self.send(text_data=json.dumps(event["players"]))