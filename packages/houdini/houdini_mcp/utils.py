"""Utilities for converting RPyC netref proxy objects to native Python types.

All values returned from Houdini via RPyC are proxy (netref) objects.
They must be converted to native Python types before JSON serialization.
"""

from __future__ import annotations

import logging
from typing import Any

import rpyc

logger = logging.getLogger(__name__)


def obtain(value: Any) -> Any:
    """Convert an RPyC netref proxy to a native Python object."""
    if value is None:
        return None
    if isinstance(value, (bool, int, float, str, bytes)):
        return value
    try:
        return rpyc.classic.obtain(value)
    except Exception:
        try:
            return str(value)
        except Exception:
            return repr(value)


def obtain_list(remote_list: Any) -> list:
    """Convert a remote list/tuple to a native list."""
    if remote_list is None:
        return []
    try:
        return [obtain(item) for item in remote_list]
    except Exception:
        return []


def obtain_dict(remote_dict: Any) -> dict:
    """Convert a remote dict to a native dict."""
    if remote_dict is None:
        return {}
    try:
        return {obtain(k): obtain(v) for k, v in remote_dict.items()}
    except Exception:
        return {}


def node_to_dict(node: Any) -> dict:
    """Convert a hou.Node netref to a serializable dict."""
    try:
        result = {
            "path": obtain(node.path()),
            "type": obtain(node.type().name()),
            "type_category": obtain(node.type().category().name()),
            "name": obtain(node.name()),
            "comment": obtain(node.comment()),
            "color": obtain_list(node.color().rgb()),
            "position": obtain_list(node.position()),
        }
        try:
            result["is_bypassed"] = obtain(node.isBypassed())
        except Exception:
            pass
        try:
            result["is_locked"] = obtain(node.isLockedHDA())
        except Exception:
            pass
        return result
    except Exception as e:
        logger.warning("Failed to convert node to dict: %s", e)
        return {"path": obtain(node.path()), "error": str(e)}


def parm_template_to_dict(template: Any) -> dict:
    """Convert a hou.ParmTemplate netref to a serializable dict."""
    try:
        result: dict[str, Any] = {
            "name": obtain(template.name()),
            "label": obtain(template.label()),
            "type": obtain(str(template.type())),
        }
        try:
            result["min"] = obtain(template.minValue())
            result["max"] = obtain(template.maxValue())
        except Exception:
            pass
        try:
            result["default"] = obtain_list(template.defaultValue())
        except Exception:
            pass
        try:
            result["num_components"] = obtain(template.numComponents())
        except Exception:
            pass
        try:
            items = template.menuItems()
            if items:
                result["menu_items"] = obtain_list(items)
                result["menu_labels"] = obtain_list(template.menuLabels())
        except Exception:
            pass
        return result
    except Exception as e:
        return {"name": "unknown", "error": str(e)}
