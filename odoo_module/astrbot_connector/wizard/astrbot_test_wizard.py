# -*- coding: utf-8 -*-

import logging
import uuid

from odoo import fields, models

_logger = logging.getLogger(__name__)


class AstrBotTestWizard(models.TransientModel):
    """Wizard for testing AstrBot sync API"""

    _name = "astrbot.test.wizard"
    _description = "AstrBot Test Wizard"

    message = fields.Text(
        string="Test Message",
        default="你好，这是一条来自 Odoo 的测试消息，请简短回复。",
        required=True,
    )
    response = fields.Text(
        string="Response",
        readonly=True,
    )
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("done", "Done"),
            ("error", "Error"),
        ],
        default="draft",
    )
    error_message = fields.Char(string="Error", readonly=True)

    def action_send(self):
        """Send test message to AstrBot"""
        self.ensure_one()

        # Check configuration
        IrConfig = self.env["ir.config_parameter"].sudo()
        webhook_url = IrConfig.get_param("astrbot_connector.webhook_url", "")

        if not webhook_url:
            self.write(
                {
                    "state": "error",
                    "error_message": "Webhook URL 未配置，请先在设置中配置",
                }
            )
            return self._return_wizard()

        # Get the service
        service = self.env["astrbot.service"]

        # Generate a unique test session ID
        test_session_id = f"odoo_test_{uuid.uuid4().hex[:8]}"

        try:
            # Call sync API
            reply = service.chat_sync(
                message=self.message,
                session_id=test_session_id,
                timeout=60,
            )

            if reply:
                self.write(
                    {
                        "state": "done",
                        "response": reply,
                    }
                )
            else:
                self.write(
                    {
                        "state": "error",
                        "error_message": "未收到回复，请检查 AstrBot 服务和配置",
                    }
                )

        except Exception as e:
            _logger.error("AstrBot test failed: %s", e, exc_info=True)
            self.write(
                {
                    "state": "error",
                    "error_message": str(e),
                }
            )

        return self._return_wizard()

    def _return_wizard(self):
        """Return action to keep wizard open"""
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }

    def action_reset(self):
        """Reset wizard to send another message"""
        self.write(
            {
                "state": "draft",
                "response": False,
                "error_message": False,
            }
        )
        return self._return_wizard()
