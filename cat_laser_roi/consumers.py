import json
from channels.generic.websocket import AsyncWebsocketConsumer

class LogConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        # The group name is hardcoded for simplicity.
        # In a real app, you might use a dynamic name, e.g., from the URL.
        self.room_group_name = "log_solver_cat_laser_roi"

        # Join room group
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )

        await self.accept()

    async def disconnect(self, close_code):
        # Leave room group
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    # This method is called when a message is sent to the group.
    # We receive it here and forward it to the WebSocket client.
    async def chat_message(self, event):
        message = event['message']

        # Send message to WebSocket
        await self.send(text_data=json.dumps({
            'message': message
        }))