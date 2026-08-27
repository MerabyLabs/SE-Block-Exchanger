"""
Safe XML parsing and atomic writing helpers.

Wraps defusedxml.ElementTree.parse when available to harden against XXE,
billion-laughs, and external-DTD attacks. Falls back to xml.etree.ElementTree
when defusedxml is not installed.
"""

from __future__ import annotations

import os
from pathlib import Path
import xml.etree.ElementTree as ET
from typing import Optional, cast, Any


class BlueprintParseError(ValueError):
    """Raised when an SBC XML blueprint is malformed or cannot be parsed."""


try:
    import defusedxml.ElementTree as _DET  # type: ignore

    def parse(source) -> Any:
        """Parse an XML file or file-like object using defusedxml."""
        try:
            return _DET.parse(source)
        except Exception as exc:
            raise BlueprintParseError(f"Failed to parse XML blueprint: {exc}") from exc

    HARDENED = True
except ImportError:  # pragma: no cover
    def parse(source) -> Any:
        """Parse an XML file or file-like object (stdlib fallback)."""
        try:
            return ET.parse(source)
        except Exception as exc:
            raise BlueprintParseError(f"Failed to parse XML blueprint: {exc}") from exc

    HARDENED = False


def safe_write(tree: Any, file_path: Path | str, encoding: str = "utf-8", xml_declaration: bool = True) -> None:
    """
    Atomically writes an ElementTree to disk using a temporary file and replace().
    Prevents file corruption on interrupted writes or disk errors.
    """
    target = Path(file_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp_file = target.with_suffix(f"{target.suffix}.tmp_{os.getpid()}")
    try:
        tree.write(temp_file, encoding=encoding, xml_declaration=xml_declaration)
        temp_file.replace(target)
    except Exception as exc:
        if temp_file.exists():
            try:
                temp_file.unlink()
            except OSError:
                pass
        raise exc


def get_subtype(block: ET.Element) -> Optional[str]:
    """Extracts SubtypeName or SubtypeId text from a CubeBlock element."""
    sub_name = block.find("SubtypeName")
    if sub_name is not None and sub_name.text and sub_name.text.strip():
        return sub_name.text.strip()
    sub_id = block.find("SubtypeId")
    if sub_id is not None and sub_id.text and sub_id.text.strip():
        return sub_id.text.strip()
    return None


def get_text(element: ET.Element, tag: str) -> Optional[str]:
    """Helper to extract stripped text from a direct child tag."""
    child = element.find(tag)
    if child is not None and child.text:
        return child.text.strip()
    return None


__all__ = [
    "parse",
    "safe_write",
    "get_subtype",
    "get_text",
    "BlueprintParseError",
    "HARDENED",
]

