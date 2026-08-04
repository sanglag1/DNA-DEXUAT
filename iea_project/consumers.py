import json
from channels.generic.websocket import AsyncWebsocketConsumer
from collections import defaultdict

# Biến toàn cục để lưu trữ lịch sử log cho mỗi phòng
LOG_HISTORY = defaultdict(list)

class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.app_name = self.scope['url_route']['kwargs']['app_name']
        self.group_name = f"log_gurobi_solver_{self.app_name}"

        await self.channel_layer.group_add(
            self.group_name,
            self.channel_name
        )
        await self.accept()

        # Gửi lịch sử log cho client vừa kết nối
        history = LOG_HISTORY.get(self.group_name, [])
        for message in history:
            await self.send(text_data=json.dumps({"message": message}))

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(
            self.group_name,
            self.channel_name
        )

    async def chat_message(self, event):
        message = event["message"]
        await self.send(text_data=json.dumps({"message": message}))