# -*- coding: utf-8 -*-

import logging
import time

import requests

from odoo import api, models

_logger = logging.getLogger(__name__)


class DiscussChannel(models.Model):
    """Extend discuss.channel to intercept messages to AstrBot"""

    _inherit = "discuss.channel"

    def _is_astrbot_channel(self):
        """Check if this channel is a chat with AstrBot

        Returns:
            bool: True if this is an AstrBot chat channel
        """
        self.ensure_one()
        bot_partner = self.env["res.config.settings"].get_astrbot_bot_partner()
        if not bot_partner:
            return False

        # Check if bot is a member of this channel
        # Odoo 18 may use different field names for channel members
        partner_ids = []

        # Try different field names for compatibility
        if hasattr(self, "channel_partner_ids"):
            partner_ids = self.channel_partner_ids.ids
        elif hasattr(self, "channel_member_ids"):
            # channel_member_ids contains discuss.channel.member records
            partner_ids = self.channel_member_ids.mapped("partner_id").ids
        elif hasattr(self, "member_ids"):
            partner_ids = self.member_ids.mapped("partner_id").ids

        return bot_partner.id in partner_ids

    def _get_astrbot_config(self):
        """Get AstrBot configuration

        Returns:
            dict: AstrBot configuration or None if disabled
        """
        config = self.env["res.config.settings"].get_astrbot_config()
        if not config.get("enabled"):
            return None
        if not config.get("webhook_url"):
            _logger.warning("AstrBot: Webhook URL not configured")
            return None
        return config

    @api.model
    def _forward_message_to_astrbot(self, channel, message, author):
        """Forward a message to AstrBot

        Args:
            channel: The discuss.channel record
            message: The mail.message record
            author: The res.partner who sent the message
        """
        config = self._get_astrbot_config()
        if not config:
            return

        bot_partner = self.env["res.config.settings"].get_astrbot_bot_partner()
        if not bot_partner:
            _logger.warning("AstrBot: Bot partner not found")
            return

        # Don't forward bot's own messages
        if author.id == bot_partner.id:
            return

        # Prepare message payload for AstrBot
        payload = {
            "type": "message",
            "message_id": str(message.id),
            "content": message.body or "",
            "user_id": str(author.id),
            "user_name": author.name or "Unknown",
            "session_id": str(channel.id),
            "message_type": "private",  # Discuss DM
            "timestamp": int(time.time()),
            "api_key": config.get("api_key", ""),
        }

        # Strip HTML tags from body for plain text content
        if message.body:
            from html import unescape
            import re

            # Remove HTML tags
            clean_body = re.sub(r"<[^>]+>", "", message.body)
            # Unescape HTML entities
            clean_body = unescape(clean_body).strip()
            payload["content"] = clean_body

        headers = {
            "Content-Type": "application/json",
        }
        if config.get("api_key"):
            headers["X-Odoo-API-Key"] = config["api_key"]

        try:
            response = requests.post(
                config["webhook_url"],
                json=payload,
                headers=headers,
                timeout=30,
            )
            if response.status_code == 200:
                _logger.debug("AstrBot: Message forwarded successfully")
            else:
                _logger.error(
                    "AstrBot: Failed to forward message, status=%s, response=%s",
                    response.status_code,
                    response.text,
                )
        except requests.RequestException as e:
            _logger.error("AstrBot: Network error when forwarding message: %s", e)
        except Exception as e:
            _logger.error("AstrBot: Error forwarding message: %s", e, exc_info=True)

    def _message_post_after_hook(self, message, msg_values):
        """Hook called after a message is posted

        Override to intercept messages sent to AstrBot channel

        Args:
            message: The created mail.message record
            msg_values: Dictionary of values used to create the message
        """
        result = super()._message_post_after_hook(message, msg_values)

        # Check if this is an AstrBot channel and forward the message
        try:
            if self._is_astrbot_channel():
                author = message.author_id
                if author:
                    self._forward_message_to_astrbot(self, message, author)
        except Exception as e:
            _logger.error("AstrBot: Error in message hook: %s", e, exc_info=True)

        return result
