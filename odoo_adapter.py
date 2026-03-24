"""
Odoo Platform Adapter for AstrBot
Connects AstrBot with Odoo 18 Discuss module via Webhook
"""

import asyncio
import time
import uuid
from typing import Any, cast

import aiohttp

from astrbot import logger
from astrbot.api.event import MessageChain
from astrbot.api.platform import (
    AstrBotMessage,
    MessageMember,
    MessageType,
    Platform,
    PlatformMetadata,
)
from astrbot.core.platform.astr_message_event import MessageSesion
from astrbot.core.platform.register import register_platform_adapter
from astrbot.core.utils.webhook_utils import log_webhook_info

from .odoo_event import OdooMessageEvent


@register_platform_adapter(
    "odoo",
    "Odoo 18 平台适配器，连接 AstrBot 与 Odoo Discuss 模块",
    default_config_tmpl={
        "odoo_callback_url": "http://localhost:8069/astrbot/callback",
        "odoo_api_key": "",
        "bot_name": "AstrBot",
        "unified_webhook_mode": True,
        "webhook_uuid": "",
    },
    adapter_display_name="Odoo 18",
    support_streaming_message=False,
)
class OdooPlatformAdapter(Platform):
    """Odoo platform adapter using unified webhook mode"""

    def __init__(
        self,
        platform_config: dict,
        platform_settings: dict,
        event_queue: asyncio.Queue,
    ) -> None:
        super().__init__(platform_config, event_queue)

        # Odoo callback URL for sending replies
        self.odoo_callback_url = platform_config.get(
            "odoo_callback_url", "http://localhost:8069/astrbot/callback"
        )
        # API Key for request validation
        self.odoo_api_key = platform_config.get("odoo_api_key", "")
        # Bot display name
        self.bot_name = platform_config.get("bot_name", "AstrBot")
        # Unified webhook mode
        self.unified_webhook_mode = platform_config.get("unified_webhook_mode", True)

        # Auto-generate webhook_uuid if unified webhook mode is enabled but uuid is missing
        if self.unified_webhook_mode and not platform_config.get("webhook_uuid"):
            generated_uuid = uuid.uuid4().hex[:16]
            platform_config["webhook_uuid"] = generated_uuid
            # Also update self.config which is the reference used by run()
            self.config["webhook_uuid"] = generated_uuid
            logger.info(f"[Odoo] Auto-generated webhook_uuid: {generated_uuid}")

        # Event deduplication (prevent duplicate message processing)
        self.event_id_timestamps: dict[str, float] = {}

        # Shutdown event for unified webhook mode
        self._shutdown_event = asyncio.Event()

        # HTTP client session
        self._http_session: aiohttp.ClientSession | None = None

        # Pending sync requests: message_id -> Future(reply_text)
        self._sync_reply_futures: dict[str, asyncio.Future[str]] = {}

    def _clean_expired_events(self):
        """Clean events older than 30 minutes"""
        current_time = time.time()
        expired_keys = [
            event_id
            for event_id, timestamp in self.event_id_timestamps.items()
            if current_time - timestamp > 1800
        ]
        for event_id in expired_keys:
            del self.event_id_timestamps[event_id]

    def _is_duplicate_event(self, event_id: str) -> bool:
        """Check if event is duplicate"""
        self._clean_expired_events()
        if event_id in self.event_id_timestamps:
            return True
        self.event_id_timestamps[event_id] = time.time()
        return False

    def meta(self) -> PlatformMetadata:
        return PlatformMetadata(
            name="odoo",
            description="Odoo 18 平台适配器",
            id=cast(str, self.config.get("id")),
            support_streaming_message=False,
        )

    async def _get_http_session(self) -> aiohttp.ClientSession:
        """Get or create HTTP client session"""
        if self._http_session is None or self._http_session.closed:
            self._http_session = aiohttp.ClientSession()
        return self._http_session

    async def send_to_odoo(
        self,
        session_id: str,
        message_chain: MessageChain,
        reply_to: str | None = None,
    ):
        """Send message to Odoo

        Args:
            session_id: Session ID (channel ID)
            message_chain: Message chain to send
            reply_to: Original message ID being replied to
        """
        # For sync_chat requests, capture reply directly instead of callbacking Odoo.
        if reply_to and reply_to in self._sync_reply_futures:
            future = self._sync_reply_futures.get(reply_to)
            if future and not future.done():
                future.set_result(self._extract_sync_reply_text(message_chain))
            return

        # Convert message chain to Odoo format
        content = OdooMessageEvent.convert_chain_to_odoo(message_chain)

        payload = {
            "session_id": session_id,
            "content": content,
            "reply_to": reply_to,
            "bot_name": self.bot_name,
            "timestamp": int(time.time()),
        }

        headers = {
            "Content-Type": "application/json",
        }
        if self.odoo_api_key:
            headers["X-Odoo-API-Key"] = self.odoo_api_key

        try:
            http_session = await self._get_http_session()
            async with http_session.post(
                self.odoo_callback_url,
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as response:
                if response.status != 200:
                    response_text = await response.text()
                    logger.error(
                        f"[Odoo] Failed to send message: HTTP {response.status}, {response_text}"
                    )
                else:
                    logger.debug(f"[Odoo] Message sent successfully: {session_id}")
        except aiohttp.ClientError as e:
            logger.error(f"[Odoo] Network error when sending message: {e}")
        except Exception as e:
            logger.error(f"[Odoo] Error when sending message: {e}", exc_info=True)

    @staticmethod
    def _extract_sync_reply_text(message_chain: MessageChain) -> str:
        """Flatten message chain into plain text for sync API response."""
        content = OdooMessageEvent.convert_chain_to_odoo(message_chain)
        parts: list[str] = []
        for item in content:
            item_type = item.get("type")
            if item_type == "text":
                text = str(item.get("data", "")).strip()
                if text:
                    parts.append(text)
            elif item_type == "image":
                parts.append("[image]")
        return "\n".join(parts).strip()

    async def send_by_session(
        self,
        session: MessageSesion,
        message_chain: MessageChain,
    ):
        """Send message by session"""
        await self.send_to_odoo(session.session_id, message_chain)
        await super().send_by_session(session, message_chain)

    async def convert_message(self, data: dict) -> AstrBotMessage | None:
        """Convert Odoo message to AstrBotMessage

        Args:
            data: Message data from Odoo

        Returns:
            Converted AstrBotMessage or None if conversion fails
        """
        try:
            abm = AstrBotMessage()

            # Message type: private or group
            message_type = data.get("message_type", "private")
            abm.type = (
                MessageType.GROUP_MESSAGE
                if message_type == "group"
                else MessageType.FRIEND_MESSAGE
            )

            # Group ID (if group chat)
            if abm.type == MessageType.GROUP_MESSAGE:
                abm.group_id = data.get("group_id", "")

            # Bot identifier
            abm.self_id = self.bot_name

            # Message content
            abm.message_str = data.get("content", "")
            abm.message = OdooMessageEvent.parse_odoo_content(data.get("content", ""))

            # Message ID
            abm.message_id = data.get("message_id", "")

            # Sender info
            abm.sender = MessageMember(
                user_id=data.get("user_id", ""),
                nickname=data.get("user_name", "Unknown"),
            )

            # Session ID
            abm.session_id = data.get("session_id", abm.sender.user_id)

            # Timestamp
            abm.timestamp = data.get("timestamp", int(time.time()))

            # Raw message
            abm.raw_message = data

            return abm

        except Exception as e:
            logger.error(f"[Odoo] Failed to convert message: {e}", exc_info=True)
            return None

    async def handle_message(self, abm: AstrBotMessage):
        """Handle message and commit to event queue"""
        event = OdooMessageEvent(
            message_str=abm.message_str,
            message_obj=abm,
            platform_meta=self.meta(),
            session_id=abm.session_id,
            adapter=self,
        )
        self.commit_event(event)

    async def handle_webhook_event(self, data: dict) -> dict:
        """Handle webhook event

        Args:
            data: Webhook request data

        Returns:
            Response data
        """
        event_type = data.get("type", "message")

        # Validate API Key
        request_api_key = data.get("api_key", "")
        if self.odoo_api_key and request_api_key != self.odoo_api_key:
            logger.warning("[Odoo] API Key validation failed")
            return {"success": False, "error": "Invalid API Key"}

        if event_type == "message":
            # Handle message event (async - response via callback)
            message_id = data.get("message_id", "")
            if message_id and self._is_duplicate_event(message_id):
                logger.debug(f"[Odoo] Skipping duplicate message: {message_id}")
                return {"success": True, "message": "Duplicate event ignored"}

            abm = await self.convert_message(data)
            if abm:
                await self.handle_message(abm)
                return {"success": True, "message": "Message received"}
            else:
                return {"success": False, "error": "Failed to parse message"}

        elif event_type == "sync_chat":
            # Synchronous chat - wait for AI response and return immediately
            return await self._handle_sync_chat(data)

        elif event_type == "ping":
            # Health check
            return {
                "success": True,
                "message": "pong",
                "bot_name": self.bot_name,
                "platform": "odoo",
            }

        else:
            logger.debug(f"[Odoo] Unknown event type: {event_type}")
            return {"success": False, "error": f"Unknown event type: {event_type}"}

    async def _handle_sync_chat(self, data: dict) -> dict:
        """Handle synchronous chat request

        Processes message through AstrBot normal event pipeline and returns reply.

        Args:
            data: Request data with message, session_id, user_name

        Returns:
            Response with AI reply
        """
        message_id = data.get("message_id", f"odoo_sync_{uuid.uuid4().hex}")
        future: asyncio.Future[str] | None = None
        try:
            message = data.get("message", "").strip()
            session_id = data.get("session_id", "odoo_sync")
            user_name = data.get("user_name", "Odoo User")
            user_id = data.get("user_id", f"odoo_sync_user_{session_id}")
            timeout = int(data.get("timeout", 60) or 60)
            timeout = max(5, min(timeout, 180))

            if not message:
                return {"success": False, "error": "Message is required"}

            logger.debug(
                f"[Odoo] Sync chat: user={user_name}, session={session_id}, message={message[:50]}..."
            )

            # Build a standard message event so AstrBot full pipeline is applied:
            # provider selection, persona, plugins, knowledge base, etc.
            event_payload = {
                "message_id": message_id,
                "content": message,
                "user_id": user_id,
                "user_name": user_name,
                "session_id": session_id,
                "message_type": data.get("message_type", "private"),
                "timestamp": int(time.time()),
            }

            abm = await self.convert_message(event_payload)
            if not abm:
                return {"success": False, "error": "Failed to parse sync message"}

            loop = asyncio.get_running_loop()
            future = loop.create_future()
            self._sync_reply_futures[message_id] = future

            await self.handle_message(abm)
            reply = await asyncio.wait_for(future, timeout=timeout)
            if not reply:
                return {"success": False, "error": "Empty reply from AstrBot pipeline"}

            logger.debug(f"[Odoo] Sync chat reply: {reply[:100]}...")

            return {
                "success": True,
                "reply": reply,
                "session_id": session_id,
            }

        except asyncio.TimeoutError:
            logger.warning(
                f"[Odoo] Sync chat timeout: session={data.get('session_id', 'odoo_sync')}, "
                f"message_id={message_id}"
            )
            return {"success": False, "error": "Sync chat timeout"}
        except Exception as e:
            logger.error(f"[Odoo] Sync chat error: {e}", exc_info=True)
            return {"success": False, "error": str(e)}
        finally:
            if future and not future.done():
                future.cancel()
            self._sync_reply_futures.pop(message_id, None)

    async def webhook_callback(self, request: Any) -> Any:
        """Unified webhook callback entry point

        Supports Quart request object
        """
        try:
            data = await request.get_json()
            if not data:
                return {"success": False, "error": "Empty request body"}, 400

            result = await self.handle_webhook_event(data)
            status_code = 200 if result.get("success") else 400
            return result, status_code

        except Exception as e:
            logger.error(f"[Odoo] Webhook processing failed: {e}", exc_info=True)
            return {"success": False, "error": str(e)}, 500

    async def run(self):
        """Run the adapter"""
        webhook_uuid = self.config.get("webhook_uuid")
        if self.unified_webhook_mode and webhook_uuid:
            log_webhook_info(f"{self.meta().id}(Odoo)", webhook_uuid)
            logger.info("[Odoo] Adapter started in unified webhook mode")
            logger.info(f"[Odoo] Callback URL to Odoo: {self.odoo_callback_url}")
            # Wait for shutdown in unified webhook mode
            await self._shutdown_event.wait()
        elif self.unified_webhook_mode and not webhook_uuid:
            logger.warning(
                "[Odoo] Unified webhook mode enabled but webhook_uuid not configured"
            )
            logger.info(
                "[Odoo] Please save the platform config to auto-generate webhook_uuid"
            )
            await self._shutdown_event.wait()
        else:
            logger.warning(
                "[Odoo] Unified webhook mode is disabled, adapter cannot receive messages"
            )
            logger.info(
                "[Odoo] Please enable unified webhook mode in platform settings"
            )
            await self._shutdown_event.wait()

    async def terminate(self):
        """Terminate the adapter"""
        self._shutdown_event.set()
        if self._http_session and not self._http_session.closed:
            await self._http_session.close()
        logger.info("[Odoo] Adapter stopped")

    def unified_webhook(self) -> bool:
        """Check if using unified webhook mode"""
        return self.config.get("unified_webhook_mode", True) and bool(
            self.config.get("webhook_uuid")
        )

    def get_client(self):
        """Get client object"""
        return None
