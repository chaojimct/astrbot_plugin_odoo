# -*- coding: utf-8 -*-

import json
import logging
import threading
import time
import uuid

import requests

from odoo import api, models

_logger = logging.getLogger(__name__)


class AstrBotService(models.AbstractModel):
    """AstrBot AI Service - provides unified interface for AI chat

    This service provides two modes:
    1. chat_sync() - Synchronous call via Webhook (recommended for auto-reply)
    2. chat_async() - Asynchronous call via Webhook (for Discuss integration)

    Usage in other modules:
        service = self.env['astrbot.service']
        reply = service.chat_sync(
            message="Hello",
            session_id="douyin_123456",
        )
    """

    _name = "astrbot.service"
    _description = "AstrBot AI Service"

    # Store pending async requests and their results
    _pending_requests = {}
    _pending_lock = threading.Lock()

    @api.model
    def _get_config(self):
        """Get AstrBot configuration

        Returns:
            dict: Configuration dictionary
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
    def chat_sync(self, message, session_id, user_name="User", timeout=60):
        """Synchronous chat - call AstrBot API via Webhook and wait for response

        Args:
            message (str): User message content
            session_id (str): Session ID for context (e.g., 'douyin_123456')
            user_name (str): User display name
            timeout (int): Request timeout in seconds

        Returns:
            str: AI reply text, or empty string on error

        Example:
            reply = self.env['astrbot.service'].chat_sync(
                message="What is the weather today?",
                session_id="douyin_user_123",
                timeout=30,
            )
        """
        config = self._get_config()

        if not config.get("enabled"):
            _logger.warning("AstrBot service is not enabled")
            return ""

        webhook_url = config.get("webhook_url", "")
        if not webhook_url:
            _logger.error("AstrBot webhook_url is not configured")
            return ""

        api_key = config.get("api_key", "")

        headers = {
            "Content-Type": "application/json",
        }

        payload = {
            "type": "sync_chat",
            "message": message,
            "session_id": session_id,
            "user_name": user_name,
            "api_key": api_key,
        }

        _logger.debug(
            "Calling AstrBot Sync Chat API: %s, session=%s", webhook_url, session_id
        )

        try:
            response = requests.post(
                webhook_url,
                json=payload,
                headers=headers,
                timeout=timeout,
            )

            if response.status_code != 200:
                _logger.error(
                    "AstrBot Sync Chat API error: HTTP %s, %s",
                    response.status_code,
                    response.text[:500],
                )
                return ""

            result = response.json()
            if result.get("success"):
                return result.get("reply", "")
            else:
                _logger.error(
                    "AstrBot Sync Chat API error: %s",
                    result.get("error", "Unknown error"),
                )
                return ""

        except requests.exceptions.Timeout:
            _logger.error("AstrBot Sync Chat API timeout")
            return ""
        except json.JSONDecodeError as e:
            _logger.error("AstrBot Sync Chat API: Invalid JSON response: %s", e)
            return ""
        except Exception as e:
            _logger.error("AstrBot Sync Chat API error: %s", e, exc_info=True)
            return ""

    @api.model
    def chat_async(
        self,
        message,
        session_id,
        user_id,
        user_name="User",
        callback_model=None,
        callback_method=None,
        timeout=60,
    ):
        """Asynchronous chat - send message via Webhook and receive callback

        This method sends a message to AstrBot via Webhook. The response will
        be received through the callback endpoint. Useful when you don't need
        to wait for the response immediately.

        Args:
            message (str): User message content
            session_id (str): Session ID for context
            user_id (str): User ID
            user_name (str): User display name
            callback_model (str): Model name for callback (optional)
            callback_method (str): Method name for callback (optional)
            timeout (int): Timeout for waiting response (if blocking)

        Returns:
            dict: Request info with 'request_id' for tracking

        Example:
            result = self.env['astrbot.service'].chat_async(
                message="Hello",
                session_id="douyin_conv_123",
                user_id="user_456",
            )
            # Result: {'request_id': 'xxx', 'status': 'pending'}
        """
        config = self._get_config()

        if not config.get("enabled"):
            _logger.warning("AstrBot service is not enabled")
            return {"error": "Service not enabled"}

        webhook_url = config.get("webhook_url", "")
        if not webhook_url:
            _logger.error("AstrBot webhook_url is not configured")
            return {"error": "Webhook URL not configured"}

        request_id = str(uuid.uuid4())

        # Prepare payload
        payload = {
            "type": "message",
            "message_id": request_id,
            "content": message,
            "user_id": user_id,
            "user_name": user_name,
            "session_id": session_id,
            "message_type": "private",
            "timestamp": int(time.time()),
            "api_key": config.get("api_key", ""),
            # Callback info for tracking
            "_callback_model": callback_model,
            "_callback_method": callback_method,
            "_request_id": request_id,
        }

        headers = {
            "Content-Type": "application/json",
        }
        if config.get("api_key"):
            headers["X-Odoo-API-Key"] = config["api_key"]

        try:
            response = requests.post(
                webhook_url,
                json=payload,
                headers=headers,
                timeout=30,
            )

            if response.status_code == 200:
                _logger.debug("AstrBot async request sent: %s", request_id)
                return {
                    "request_id": request_id,
                    "status": "pending",
                    "session_id": session_id,
                }
            else:
                _logger.error(
                    "AstrBot async request failed: HTTP %s, %s",
                    response.status_code,
                    response.text[:500],
                )
                return {
                    "error": f"HTTP {response.status_code}",
                    "request_id": request_id,
                }

        except requests.RequestException as e:
            _logger.error("AstrBot async request error: %s", e)
            return {"error": str(e), "request_id": request_id}

    @api.model
    def chat_sync_via_webhook(
        self, message, session_id, user_id, user_name="User", timeout=60
    ):
        """Synchronous chat via Webhook with blocking wait

        WARNING: This method may not work reliably in multi-process Odoo
        environments. Use chat_sync() instead for reliable synchronous calls.

        This method sends a message via Webhook and blocks until the callback
        is received or timeout occurs. Use this when you need sync behavior
        but want to use the Webhook flow (e.g., for consistent session handling).

        Args:
            message (str): User message content
            session_id (str): Session ID for context
            user_id (str): User ID
            user_name (str): User display name
            timeout (int): Maximum wait time in seconds

        Returns:
            str: AI reply text, or empty string on timeout/error
        """
        _logger.warning(
            "chat_sync_via_webhook may not work in multi-process environments. "
            "Consider using chat_sync() instead."
        )
        request_id = str(uuid.uuid4())

        # Register pending request
        with self._pending_lock:
            self._pending_requests[request_id] = {
                "status": "pending",
                "response": None,
                "timestamp": time.time(),
            }

        try:
            # Send async request
            result = self.chat_async(
                message=message,
                session_id=session_id,
                user_id=user_id,
                user_name=user_name,
            )

            if "error" in result:
                return ""

            # Wait for response
            start_time = time.time()
            while time.time() - start_time < timeout:
                with self._pending_lock:
                    pending = self._pending_requests.get(request_id, {})
                    if pending.get("status") == "completed":
                        response = pending.get("response", "")
                        del self._pending_requests[request_id]
                        return response

                time.sleep(0.5)

            _logger.warning("AstrBot sync_via_webhook timeout: %s", request_id)
            return ""

        finally:
            # Cleanup
            with self._pending_lock:
                self._pending_requests.pop(request_id, None)

    @api.model
    def handle_callback_response(self, request_id, response_text):
        """Handle callback response from AstrBot

        Called by the HTTP controller when receiving a callback.

        Args:
            request_id: Original request ID
            response_text: AI response text
        """
        with self._pending_lock:
            if request_id in self._pending_requests:
                self._pending_requests[request_id] = {
                    "status": "completed",
                    "response": response_text,
                    "timestamp": time.time(),
                }
                _logger.debug("AstrBot callback received: %s", request_id)

    @api.model
    def test_connection(self):
        """Test connection to AstrBot

        Returns:
            dict: Test result with status and message
        """
        config = self._get_config()

        if not config.get("enabled"):
            return {"success": False, "message": "Service not enabled"}

        # Test WebChat API
        base_url = config.get("base_url", "").rstrip("/")
        if base_url:
            try:
                response = requests.get(
                    f"{base_url}/api/stat/base",
                    timeout=10,
                )
                if response.status_code == 200:
                    return {
                        "success": True,
                        "message": "Connected to AstrBot",
                        "mode": "webchat",
                    }
            except Exception as e:
                _logger.warning("WebChat API test failed: %s", e)

        # Test Webhook
        webhook_url = config.get("webhook_url", "")
        if webhook_url:
            try:
                # Send ping request
                response = requests.post(
                    webhook_url,
                    json={"type": "ping", "api_key": config.get("api_key", "")},
                    timeout=10,
                )
                if response.status_code == 200:
                    return {
                        "success": True,
                        "message": "Connected to AstrBot via Webhook",
                        "mode": "webhook",
                    }
            except Exception as e:
                _logger.warning("Webhook test failed: %s", e)

        return {"success": False, "message": "Cannot connect to AstrBot"}
