"""codexcrew-client — async Python client for the CodexCrew Gateway.

Usage::

    from codexcrew_client import CodexCrewClient

    async with CodexCrewClient(app_name="my-app") as mc:
        ok = await mc.ping()
        status = await mc.get_status()
        await mc.send_message("slot-1", "hello")
"""
from codexcrew_client.client import CodexCrewClient
from codexcrew_client.errors import CodexCrewError, ErrorCode

__all__ = ["CodexCrewClient", "CodexCrewError", "ErrorCode"]
