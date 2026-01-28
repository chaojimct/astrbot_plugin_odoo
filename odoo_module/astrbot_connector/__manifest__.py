# -*- coding: utf-8 -*-
{
    "name": "AstrBot Connector",
    "version": "18.0.1.0.0",
    "category": "Discuss",
    "summary": "Connect Odoo Discuss with AstrBot AI Assistant",
    "description": """
AstrBot Connector for Odoo 18
=============================

This module integrates AstrBot AI assistant with Odoo Discuss module,
allowing users to chat with AI directly within Odoo.

Features:
---------
* Chat with AstrBot AI in Discuss
* Automatic message forwarding to AstrBot
* Support for text and image messages
* Easy configuration through Settings

Configuration:
--------------
1. Go to Settings -> General Settings -> AstrBot
2. Enter AstrBot Webhook URL
3. Set API Key for authentication
4. Enable the connector

For more information, visit: https://github.com/AstrBotDevs/AstrBot
    """,
    "author": "AstrBot",
    "website": "https://github.com/AstrBotDevs/AstrBot",
    "license": "LGPL-3",
    "depends": [
        "base",
        "base_setup",
        "mail",
    ],
    "data": [
        "security/ir.model.access.csv",
        "data/astrbot_connector_data.xml",
        "wizard/astrbot_test_wizard_views.xml",
        "views/res_config_settings_views.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
