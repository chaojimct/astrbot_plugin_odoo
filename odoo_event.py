"""
Odoo Message Event for AstrBot
Handles message sending and content conversion
"""

from __future__ import annotations

import base64
from typing import TYPE_CHECKING

from astrbot import logger
from astrbot.api.event import AstrMessageEvent, MessageChain
from astrbot.api.message_components import BaseMessageComponent, Image, Plain
from astrbot.api.platform import AstrBotMessage, PlatformMetadata

if TYPE_CHECKING:
    from .odoo_adapter import OdooPlatformAdapter


class OdooMessageEvent(AstrMessageEvent):
    """Odoo message event handler"""

    def __init__(
        self,
        message_str: str,
        message_obj: AstrBotMessage,
        platform_meta: PlatformMetadata,
        session_id: str,
        adapter: OdooPlatformAdapter,
    ):
        super().__init__(message_str, message_obj, platform_meta, session_id)
        self.adapter = adapter

    async def send(self, message: MessageChain):
        """Send message back to Odoo

        Args:
            message: Message chain to send
        """
        await self.adapter.send_to_odoo(
            session_id=self.session_id,
            message_chain=message,
            reply_to=self.message_obj.message_id,
        )
        await super().send(message)

    @staticmethod
    def convert_chain_to_odoo(message_chain: MessageChain) -> list[dict]:
        """Convert AstrBot message chain to Odoo format

        Args:
            message_chain: AstrBot message chain

        Returns:
            List of message components in Odoo format
        """
        result = []

        for comp in message_chain.chain:
            if isinstance(comp, Plain):
                # Text message
                result.append(
                    {
                        "type": "text",
                        "data": comp.text,
                    }
                )
            elif isinstance(comp, Image):
                # Image message - convert to base64
                try:
                    image_data = OdooMessageEvent._get_image_base64(comp)
                    if image_data:
                        result.append(
                            {
                                "type": "image",
                                "data": image_data,
                            }
                        )
                except Exception as e:
                    logger.error(f"[Odoo] Failed to process image: {e}")
                    result.append(
                        {
                            "type": "text",
                            "data": "[Image failed to load]",
                        }
                    )
            else:
                # Other types - convert to text representation
                logger.debug(f"[Odoo] Unsupported message type: {type(comp).__name__}")

        return result

    @staticmethod
    def _get_image_base64(image: Image) -> str | None:
        """Get base64 encoded image data

        Args:
            image: Image component

        Returns:
            Base64 encoded image string or None
        """
        if not image.file:
            return None

        file_path = image.file

        # Already base64 encoded
        if file_path.startswith("base64://"):
            return file_path

        # Local file path
        if file_path.startswith("file:///"):
            local_path = file_path[8:]
            try:
                with open(local_path, "rb") as f:
                    image_bytes = f.read()
                return "base64://" + base64.b64encode(image_bytes).decode()
            except Exception as e:
                logger.error(f"[Odoo] Failed to read local image: {e}")
                return None

        # URL - need to download (sync operation, not ideal but works)
        if file_path.startswith("http://") or file_path.startswith("https://"):
            # For URL images, we'll pass the URL directly
            # Odoo side will handle downloading
            return file_path

        # Plain file path
        try:
            with open(file_path, "rb") as f:
                image_bytes = f.read()
            return "base64://" + base64.b64encode(image_bytes).decode()
        except Exception as e:
            logger.error(f"[Odoo] Failed to read image file: {e}")
            return None

    @staticmethod
    def parse_odoo_content(content: str | list) -> list[BaseMessageComponent]:
        """Parse Odoo message content to AstrBot message components

        Args:
            content: Message content from Odoo (string or list of components)

        Returns:
            List of AstrBot message components
        """
        result = []

        # Simple text content
        if isinstance(content, str):
            if content:
                result.append(Plain(text=content))
            return result

        # List of components
        if isinstance(content, list):
            for comp in content:
                if not isinstance(comp, dict):
                    continue

                comp_type = comp.get("type", "")
                comp_data = comp.get("data", "")

                if comp_type == "text" and comp_data:
                    result.append(Plain(text=comp_data))
                elif comp_type == "image" and comp_data:
                    # Image can be base64 or URL
                    result.append(Image(file=comp_data))

        return result

    async def send_streaming(self, generator, use_fallback: bool = False):
        """Handle streaming messages - Odoo doesn't support streaming, buffer and send

        Args:
            generator: Message generator
            use_fallback: Whether to use fallback mode
        """
        buffer = None
        async for chain in generator:
            if not buffer:
                buffer = chain
            else:
                buffer.chain.extend(chain.chain)

        if not buffer:
            return None

        buffer.squash_plain()
        await self.send(buffer)
        return await super().send_streaming(generator, use_fallback)
