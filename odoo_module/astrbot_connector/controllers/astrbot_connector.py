# -*- coding: utf-8 -*-

import base64
import json
import logging

from markupsafe import Markup

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class AstrBotController(http.Controller):
    """HTTP Controller for AstrBot callbacks"""

    @http.route(
        "/astrbot/callback",
        type="http",
        auth="public",
        csrf=False,
        methods=["POST"],
    )
    def astrbot_callback(self, **kwargs):
        """Receive callback from AstrBot and post reply to Discuss

        Expected JSON payload:
        {
            "session_id": "channel_id",
            "content": [
                {"type": "text", "data": "message text"},
                {"type": "image", "data": "base64://... or http://..."}
            ],
            "reply_to": "original_message_id",
            "bot_name": "AstrBot",
            "timestamp": 1234567890
        }

        Returns:
            dict: Response with success status
        """
        try:
            # Get JSON data from request (Odoo 18 compatible)
            data = json.loads(request.httprequest.data.decode("utf-8"))

            # Validate API Key
            if not self._validate_api_key(data):
                _logger.warning("AstrBot callback: Invalid API Key")
                return self._json_response(
                    {"success": False, "error": "Invalid API Key"}
                )

            session_id = data.get("session_id")
            content = data.get("content", [])
            # bot_name can be used for logging or future features
            # bot_name = data.get("bot_name", "AstrBot")

            if not session_id:
                return self._json_response(
                    {"success": False, "error": "Missing session_id"}
                )

            if not content:
                return self._json_response(
                    {"success": False, "error": "Missing content"}
                )

            # Find the channel
            try:
                channel_id = int(session_id)
            except (ValueError, TypeError):
                _logger.error("AstrBot callback: Invalid session_id: %s", session_id)
                return self._json_response(
                    {"success": False, "error": "Invalid session_id"}
                )

            channel = request.env["discuss.channel"].sudo().browse(channel_id)
            if not channel.exists():
                _logger.error("AstrBot callback: Channel not found: %s", session_id)
                return self._json_response(
                    {"success": False, "error": "Channel not found"}
                )

            # Get bot partner
            bot_partner = (
                request.env["res.config.settings"].sudo().get_astrbot_bot_partner()
            )
            if not bot_partner:
                _logger.error("AstrBot callback: Bot partner not found")
                return self._json_response(
                    {"success": False, "error": "Bot partner not configured"}
                )

            # Build message body
            body, attachments = self._build_message_body(content)

            # Post message as bot
            message = channel.with_context(
                mail_create_nosubscribe=True,
            ).message_post(
                body=body,
                author_id=bot_partner.id,
                message_type="comment",
                subtype_xmlid="mail.mt_comment",
                attachment_ids=[(4, att.id) for att in attachments]
                if attachments
                else None,
            )

            _logger.debug(
                "AstrBot callback: Message posted successfully, id=%s", message.id
            )
            return self._json_response({"success": True, "message_id": message.id})

        except Exception as e:
            _logger.error("AstrBot callback error: %s", e, exc_info=True)
            return self._json_response({"success": False, "error": str(e)})

    def _json_response(self, data, status=200):
        """Return JSON response for HTTP routes

        Args:
            data: Dictionary to return as JSON
            status: HTTP status code

        Returns:
            Response: HTTP response with JSON content
        """
        from werkzeug.wrappers import Response

        return Response(
            json.dumps(data),
            status=status,
            content_type="application/json",
        )

    def _validate_api_key(self, data):
        """Validate API key from request

        Args:
            data: Request data dictionary

        Returns:
            bool: True if API key is valid or not required
        """
        IrConfig = request.env["ir.config_parameter"].sudo()
        configured_key = IrConfig.get_param("astrbot_connector.api_key", "")

        if not configured_key:
            # No API key configured, allow all requests
            return True

        # Check header first
        header_key = request.httprequest.headers.get("X-Odoo-API-Key", "")
        if header_key and header_key == configured_key:
            return True

        # Check payload
        payload_key = data.get("api_key", "")
        if payload_key and payload_key == configured_key:
            return True

        return False

    def _build_message_body(self, content):
        """Build message body from content list

        Args:
            content: List of content items

        Returns:
            tuple: (body_html, attachments)
        """
        body_parts = []
        attachments = []

        for item in content:
            if not isinstance(item, dict):
                continue

            item_type = item.get("type", "")
            item_data = item.get("data", "")

            if item_type == "text" and item_data:
                # Convert Markdown to HTML
                html_content = self._markdown_to_html(item_data)
                body_parts.append(html_content)

            elif item_type == "image" and item_data:
                attachment = self._process_image(item_data)
                if attachment:
                    attachments.append(attachment)

        body = "".join(body_parts) if body_parts else "<p></p>"
        # Use Markup to mark HTML as safe for Odoo rendering
        return Markup(body), attachments

    def _markdown_to_html(self, text):
        """Convert Markdown text to HTML for Odoo Discuss

        Supports common Markdown syntax:
        - Headers (# ## ### ####)
        - Bold (**text** or __text__)
        - Italic (*text* or _text_)
        - Code blocks (```code```)
        - Inline code (`code`)
        - Unordered lists (- item or * item)
        - Ordered lists (1. item)
        - Links [text](url)
        - Blockquotes (> text)
        - Horizontal rules (---)

        Args:
            text: Markdown text

        Returns:
            str: HTML formatted text
        """
        import re
        import html as html_module

        if not text:
            return "<p></p>"

        lines = text.split("\n")
        html_lines = []
        in_code_block = False
        code_block_content = []
        in_list = False
        list_type = None  # 'ul' or 'ol'

        for line in lines:
            # Handle code blocks
            if line.strip().startswith("```"):
                if in_code_block:
                    # End code block
                    code_content = html_module.escape("\n".join(code_block_content))
                    html_lines.append(
                        f'<pre style="background-color: #f4f4f4; padding: 10px; '
                        f'border-radius: 4px; overflow-x: auto; font-family: monospace;">'
                        f"<code>{code_content}</code></pre>"
                    )
                    code_block_content = []
                    in_code_block = False
                else:
                    # Start code block - close any open list
                    if in_list:
                        html_lines.append(f"</{list_type}>")
                        in_list = False
                        list_type = None
                    in_code_block = True
                continue

            if in_code_block:
                code_block_content.append(line)
                continue

            # Check for list items
            ul_match = re.match(r"^[\s]*[-*]\s+(.+)$", line)
            ol_match = re.match(r"^[\s]*(\d+)\.\s+(.+)$", line)

            if ul_match:
                if not in_list or list_type != "ul":
                    if in_list:
                        html_lines.append(f"</{list_type}>")
                    html_lines.append("<ul>")
                    in_list = True
                    list_type = "ul"
                item_content = self._inline_markdown(ul_match.group(1))
                html_lines.append(f"<li>{item_content}</li>")
                continue
            elif ol_match:
                if not in_list or list_type != "ol":
                    if in_list:
                        html_lines.append(f"</{list_type}>")
                    html_lines.append("<ol>")
                    in_list = True
                    list_type = "ol"
                item_content = self._inline_markdown(ol_match.group(2))
                html_lines.append(f"<li>{item_content}</li>")
                continue
            else:
                # Close list if we're no longer in a list item
                if in_list:
                    html_lines.append(f"</{list_type}>")
                    in_list = False
                    list_type = None

            # Empty line
            if not line.strip():
                html_lines.append("<br/>")
                continue

            # Horizontal rule
            if re.match(r"^[-*_]{3,}\s*$", line.strip()):
                html_lines.append(
                    '<hr style="border: 1px solid #ddd; margin: 10px 0;"/>'
                )
                continue

            # Headers
            header_match = re.match(r"^(#{1,6})\s+(.+)$", line)
            if header_match:
                level = len(header_match.group(1))
                header_text = self._inline_markdown(header_match.group(2))
                sizes = {
                    1: "1.5em",
                    2: "1.3em",
                    3: "1.1em",
                    4: "1em",
                    5: "0.9em",
                    6: "0.8em",
                }
                weights = {
                    1: "bold",
                    2: "bold",
                    3: "bold",
                    4: "600",
                    5: "600",
                    6: "normal",
                }
                html_lines.append(
                    f'<p style="font-size: {sizes[level]}; font-weight: {weights[level]}; '
                    f'margin: 8px 0;">{header_text}</p>'
                )
                continue

            # Blockquote
            if line.strip().startswith(">"):
                quote_text = self._inline_markdown(line.strip()[1:].strip())
                html_lines.append(
                    f'<blockquote style="border-left: 3px solid #ccc; padding-left: 10px; '
                    f'margin: 5px 0; color: #666;">{quote_text}</blockquote>'
                )
                continue

            # Regular paragraph
            processed_line = self._inline_markdown(line)
            html_lines.append(f"<p style='margin: 4px 0;'>{processed_line}</p>")

        # Close any remaining open tags
        if in_code_block:
            code_content = html_module.escape("\n".join(code_block_content))
            html_lines.append(
                f'<pre style="background-color: #f4f4f4; padding: 10px; '
                f'border-radius: 4px;"><code>{code_content}</code></pre>'
            )
        if in_list:
            html_lines.append(f"</{list_type}>")

        return "".join(html_lines)

    def _inline_markdown(self, text):
        """Process inline Markdown elements

        Args:
            text: Text with inline Markdown

        Returns:
            str: HTML formatted text
        """
        import re
        import html as html_module

        # Escape HTML first (but preserve our own tags later)
        text = html_module.escape(text)

        # Inline code (must be processed before bold/italic to avoid conflicts)
        text = re.sub(
            r"`([^`]+)`",
            r'<code style="background-color: #f0f0f0; padding: 2px 4px; '
            r'border-radius: 3px; font-family: monospace;">\1</code>',
            text,
        )

        # Bold: **text** or __text__
        text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
        text = re.sub(r"__(.+?)__", r"<strong>\1</strong>", text)

        # Italic: *text* or _text_ (but not inside words for underscore)
        text = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<em>\1</em>", text)
        text = re.sub(r"(?<![a-zA-Z0-9])_([^_]+)_(?![a-zA-Z0-9])", r"<em>\1</em>", text)

        # Strikethrough: ~~text~~
        text = re.sub(r"~~(.+?)~~", r"<del>\1</del>", text)

        # Links: [text](url)
        text = re.sub(
            r"\[([^\]]+)\]\(([^)]+)\)",
            r'<a href="\2" target="_blank" style="color: #017e84;">\1</a>',
            text,
        )

        return text

    def _process_image(self, image_data):
        """Process image data and create attachment

        Args:
            image_data: Image data (base64 or URL)

        Returns:
            ir.attachment: Created attachment or None
        """
        try:
            if image_data.startswith("base64://"):
                # Base64 encoded image
                b64_data = image_data[9:]  # Remove 'base64://' prefix
                image_bytes = base64.b64decode(b64_data)

                attachment = (
                    request.env["ir.attachment"]
                    .sudo()
                    .create(
                        {
                            "name": "astrbot_image.png",
                            "type": "binary",
                            "datas": base64.b64encode(image_bytes).decode(),
                            "res_model": "discuss.channel",
                            "mimetype": "image/png",
                        }
                    )
                )
                return attachment

            elif image_data.startswith("http://") or image_data.startswith("https://"):
                # URL - download the image
                import requests

                response = requests.get(image_data, timeout=30)
                if response.status_code == 200:
                    # Determine mime type
                    content_type = response.headers.get("Content-Type", "image/png")
                    ext = "png"
                    if "jpeg" in content_type or "jpg" in content_type:
                        ext = "jpg"
                    elif "gif" in content_type:
                        ext = "gif"
                    elif "webp" in content_type:
                        ext = "webp"

                    attachment = (
                        request.env["ir.attachment"]
                        .sudo()
                        .create(
                            {
                                "name": f"astrbot_image.{ext}",
                                "type": "binary",
                                "datas": base64.b64encode(response.content).decode(),
                                "res_model": "discuss.channel",
                                "mimetype": content_type,
                            }
                        )
                    )
                    return attachment

        except Exception as e:
            _logger.error("AstrBot: Failed to process image: %s", e)

        return None

    @http.route(
        "/astrbot/ping",
        type="http",
        auth="public",
        csrf=False,
        methods=["POST", "GET"],
    )
    def astrbot_ping(self, **kwargs):
        """Health check endpoint

        Returns:
            Response: Pong response with status
        """
        IrConfig = request.env["ir.config_parameter"].sudo()
        enabled = IrConfig.get_param("astrbot_connector.enabled", "False") == "True"

        return self._json_response(
            {
                "success": True,
                "message": "pong",
                "enabled": enabled,
                "platform": "odoo",
                "version": "18.0",
            }
        )
