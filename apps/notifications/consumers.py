import json
import asyncio
from channels.generic.websocket import AsyncWebsocketConsumer

class NotificationConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.user = self.scope["user"]
        if self.user.is_authenticated:
            self.group_name = f"user_{self.user.id}"
            await self.channel_layer.group_add(
                self.group_name,
                self.channel_name
            )
            await self.accept()

            # Start pinging after every 30 seconds to keep the connection alive
            self.ping_task = asyncio.create_task(self.ping())

        else:
            await self.close(code=4001)  # Unauthorized connection

    async def disconnect(self, close_code):
        if self.user.is_authenticated:
            await self.channel_layer.group_discard(
                self.group_name,
                self.channel_name
            )
        
        # Cancel the ping task when the connection closes
        if hasattr(self, 'ping_task'):
            self.ping_task.cancel()

    async def send_notification(self, event):
        await self.send(text_data=json.dumps(event["data"]))

    async def ping(self):
        while True:
            try:
                # Send ping message to keep the connection alive
                await self.send(text_data=json.dumps({"ping": "ping"}))
                await asyncio.sleep(30)  # Wait for 30 seconds before sending the next ping
            except Exception as e:
                # Handle any exceptions, if WebSocket connection is closed
                break
