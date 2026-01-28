"""
AstrBot Plugin: Odoo Connector
Connects AstrBot with Odoo 18 Discuss module
"""

from astrbot.api.star import Context, Star, register

# Global reference for adapter to access LLM provider
_provider_manager = None


def get_provider_manager():
    """Get the provider manager instance"""
    return _provider_manager


@register(
    "astrbot_plugin_odoo",
    "AstrBot",
    "Odoo 18 平台适配器，连接 AstrBot 与 Odoo Discuss",
    "1.0.0",
)
class OdooConnectorPlugin(Star):
    """Odoo Connector Plugin - registers Odoo platform adapter"""

    def __init__(self, context: Context):
        super().__init__(context)
        # Import adapter to trigger registration via decorator
        from .odoo_adapter import OdooPlatformAdapter  # noqa: F401

        # Store global reference for adapter to access
        global _provider_manager
        _provider_manager = context.provider_manager

    async def initialize(self):
        """Plugin initialization"""
        pass

    async def terminate(self):
        """Plugin termination"""
        pass
