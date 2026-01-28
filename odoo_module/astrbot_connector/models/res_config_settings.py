# -*- coding: utf-8 -*-

import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class ResConfigSettings(models.TransientModel):
    """Inherit res.config.settings to add AstrBot configuration"""

    _inherit = "res.config.settings"

    # AstrBot configuration fields
    astrbot_enabled = fields.Boolean(
        string="Enable AstrBot",
        config_parameter="astrbot_connector.enabled",
        help="Enable or disable AstrBot integration",
    )
    astrbot_webhook_url = fields.Char(
        string="AstrBot Webhook URL",
        config_parameter="astrbot_connector.webhook_url",
        help="The webhook URL of AstrBot server (e.g., http://localhost:6185/api/platform/webhook/{uuid})",
    )
    astrbot_api_key = fields.Char(
        string="API Key",
        config_parameter="astrbot_connector.api_key",
        help="API key for authenticating requests between Odoo and AstrBot",
    )
    astrbot_bot_name = fields.Char(
        string="Bot Display Name",
        config_parameter="astrbot_connector.bot_name",
        default="AstrBot",
        help="Display name of the bot in Discuss",
    )

    @api.model
    def get_astrbot_config(self):
        """Get AstrBot configuration as dictionary

        Returns:
            dict: AstrBot configuration
        """
        IrConfig = self.env["ir.config_parameter"].sudo()
        return {
            "enabled": IrConfig.get_param("astrbot_connector.enabled", "False")
            == "True",
            "webhook_url": IrConfig.get_param("astrbot_connector.webhook_url", ""),
            "api_key": IrConfig.get_param("astrbot_connector.api_key", ""),
            "bot_name": IrConfig.get_param("astrbot_connector.bot_name", "AstrBot"),
        }

    @api.model
    def get_astrbot_bot_partner(self):
        """Get or create the AstrBot bot partner

        Returns:
            res.partner: The bot partner record
        """
        bot_partner = self.env.ref(
            "astrbot_connector.partner_astrbot",
            raise_if_not_found=False,
        )
        if not bot_partner:
            # Fallback: search by name
            bot_partner = (
                self.env["res.partner"]
                .sudo()
                .search(
                    [
                        ("name", "=", "AstrBot"),
                        ("is_company", "=", False),
                    ],
                    limit=1,
                )
            )
        return bot_partner

    @api.model
    def get_astrbot_bot_user(self):
        """Get the AstrBot bot user

        Returns:
            res.users: The bot user record or None
        """
        bot_user = self.env.ref(
            "astrbot_connector.user_astrbot",
            raise_if_not_found=False,
        )
        if not bot_user:
            # Fallback: search by login
            bot_user = (
                self.env["res.users"]
                .sudo()
                .search([("login", "=", "astrbot")], limit=1)
            )
        return bot_user

    @api.model
    def ensure_astrbot_user_exists(self):
        """Ensure AstrBot user and partner exist

        Creates them if they don't exist. This is useful when the module
        was installed before the user record was added to data files.

        Returns:
            res.users: The bot user record
        """
        bot_user = self.get_astrbot_bot_user()
        if bot_user:
            return bot_user

        # Create partner first
        bot_partner = self.get_astrbot_bot_partner()
        if not bot_partner:
            bot_partner = (
                self.env["res.partner"]
                .sudo()
                .create(
                    {
                        "name": "AstrBot",
                        "is_company": False,
                        "active": True,
                        "type": "contact",
                        "email": "astrbot@localhost",
                        "comment": "AstrBot AI Assistant",
                    }
                )
            )
            _logger.info("AstrBot: Created bot partner: %s", bot_partner.id)

        # Create user
        bot_user = (
            self.env["res.users"]
            .sudo()
            .create(
                {
                    "name": "AstrBot",
                    "login": "astrbot",
                    "partner_id": bot_partner.id,
                    "active": True,
                    "groups_id": [(4, self.env.ref("base.group_user").id)],
                }
            )
        )
        _logger.info("AstrBot: Created bot user: %s", bot_user.id)

        return bot_user

    def action_open_astrbot_chat(self):
        """Open a chat window with AstrBot

        This action can be called from settings to start chatting with the bot.
        """
        self.ensure_one()

        # Ensure bot user exists
        bot_user = self.ensure_astrbot_user_exists()
        if not bot_user:
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": "Error",
                    "message": "Failed to create AstrBot user",
                    "type": "danger",
                },
            }

        bot_partner = bot_user.partner_id
        current_partner = self.env.user.partner_id

        # Find or create DM channel with bot
        channel = (
            self.env["discuss.channel"]
            .sudo()
            .search(
                [
                    ("channel_type", "=", "chat"),
                    ("channel_member_ids.partner_id", "in", [bot_partner.id]),
                    ("channel_member_ids.partner_id", "in", [current_partner.id]),
                ],
                limit=1,
            )
        )

        if not channel:
            # Create new DM channel
            channel = (
                self.env["discuss.channel"]
                .sudo()
                .create(
                    {
                        "name": f"{current_partner.name}, {bot_partner.name}",
                        "channel_type": "chat",
                        "channel_member_ids": [
                            (0, 0, {"partner_id": current_partner.id}),
                            (0, 0, {"partner_id": bot_partner.id}),
                        ],
                    }
                )
            )
            _logger.info("AstrBot: Created chat channel: %s", channel.id)

        # Return action to open Discuss with this channel
        return {
            "type": "ir.actions.act_url",
            "url": f"/web#action=mail.action_discuss&active_id=mail.channel_{channel.id}",
            "target": "self",
        }

    def action_test_sync_api(self):
        """Open wizard to test synchronous API call to AstrBot"""
        return {
            "type": "ir.actions.act_window",
            "res_model": "astrbot.test.wizard",
            "view_mode": "form",
            "target": "new",
            "name": "Test AstrBot Sync API",
        }

    def action_test_webhook_connection(self):
        """Test webhook connection to AstrBot

        Sends a ping request to the configured webhook URL.
        """
        self.ensure_one()

        import requests

        IrConfig = self.env["ir.config_parameter"].sudo()
        webhook_url = IrConfig.get_param("astrbot_connector.webhook_url", "")
        api_key = IrConfig.get_param("astrbot_connector.api_key", "")

        if not webhook_url:
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": "配置错误",
                    "message": "Webhook URL 未配置",
                    "type": "warning",
                    "sticky": False,
                },
            }

        try:
            headers = {"Content-Type": "application/json"}
            if api_key:
                headers["X-Odoo-API-Key"] = api_key

            payload = {
                "type": "ping",
                "api_key": api_key,
            }

            response = requests.post(
                webhook_url,
                json=payload,
                headers=headers,
                timeout=10,
            )

            if response.status_code == 200:
                return {
                    "type": "ir.actions.client",
                    "tag": "display_notification",
                    "params": {
                        "title": "Webhook 连接成功",
                        "message": f"状态码: {response.status_code}\nAstrBot Webhook 可达",
                        "type": "success",
                        "sticky": False,
                    },
                }
            else:
                return {
                    "type": "ir.actions.client",
                    "tag": "display_notification",
                    "params": {
                        "title": "Webhook 连接失败",
                        "message": f"状态码: {response.status_code}\n响应: {response.text[:200]}",
                        "type": "danger",
                        "sticky": True,
                    },
                }

        except requests.exceptions.Timeout:
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": "连接超时",
                    "message": "请检查 Webhook URL 是否正确，AstrBot 服务是否运行",
                    "type": "danger",
                    "sticky": True,
                },
            }
        except Exception as e:
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": "连接异常",
                    "message": f"错误: {str(e)}",
                    "type": "danger",
                    "sticky": True,
                },
            }
