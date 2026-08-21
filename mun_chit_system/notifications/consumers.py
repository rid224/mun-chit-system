"""
Django Channels consumer scaffold (not wired to a live ASGI/Redis deployment
in v1 — see README "Real-time notifications" section for activation steps).

To activate:
1. `pip install channels channels-redis`
2. Add "channels" to INSTALLED_APPS and set CHANNEL_LAYERS in settings.
3. Route this consumer in config/asgi.py via ProtocolTypeRouter.
4. Replace the polling call in notifications/views.py with a WebSocket
   connection that subscribes to `user_{id}_notifications`.
"""

try:
    from channels.generic.websocket import AsyncJsonWebsocketConsumer

    class NotificationConsumer(AsyncJsonWebsocketConsumer):
        async def connect(self):
            user = self.scope["user"]
            if not user or not user.is_authenticated:
                await self.close()
                return
            self.group_name = f"user_{user.id}_notifications"
            await self.channel_layer.group_add(self.group_name, self.channel_name)
            await self.accept()

        async def disconnect(self, close_code):
            if hasattr(self, "group_name"):
                await self.channel_layer.group_discard(self.group_name, self.channel_name)

        async def notify(self, event):
            await self.send_json(event["payload"])

except ImportError:
    # channels not installed — polling fallback is used instead (see views.py)
    NotificationConsumer = None
