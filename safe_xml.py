"""
Safe XML parsing helper.

Wraps defusedxml.ElementTree.parse when available to harden against XXE,
billion-laughs, and external-DTD attacks. Falls back to xml.etree.ElementTree
when defusedxml is not installed (e.g. minimal CLI installs without
requirements.txt). Only the parse path is hardened — Element construction and
serialization continue to use the standard library.
"""

from __future__ import annotations

import os
from pathlib import Path
import xml.etree.ElementTree as ET
from typing import Optional, Union, cast

try:
    import defusedxml.ElementTree as _DET  # type: ignore[import-not-found]

    def parse(source) -> ET.ElementTree[ET.Element]:
        """Parse an XML file or file-like object using defusedxml."""
        return cast("ET.ElementTree[ET.Element]", _DET.parse(source))

    HARDENED = True
except ImportError:  # pragma: no cover - exercised only when defusedxml absent
    def parse(source) -> ET.ElementTree[ET.Element]:
        """Parse an XML file or file-like object (stdlib fallback)."""
        return ET.parse(source)

    HARDENED = False


def safe_write(
    tree: ET.ElementTree[ET.Element],
    file_path: Union[Path, str],
    encoding: str = "utf-8",
    xml_declaration: bool = True,
) -> None:
    """Atomically write an ElementTree using a sibling temp file and replace()."""
    target = Path(file_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp_file = target.with_name(f"{target.name}.tmp_{os.getpid()}")
    try:
        tree.write(temp_file, encoding=encoding, xml_declaration=xml_declaration)
        temp_file.replace(target)
    except Exception:
        if temp_file.exists():
            try:
                temp_file.unlink()
            except OSError:
                pass  # temp file already gone or locked
        raise


def get_subtype(block: ET.Element) -> Optional[str]:
    """Extract SubtypeName or SubtypeId text from a CubeBlock element."""
    sub_name = block.find("SubtypeName")
    if sub_name is not None and sub_name.text and sub_name.text.strip():
        return sub_name.text.strip()
    sub_id = block.find("SubtypeId")
    if sub_id is not None and sub_id.text and sub_id.text.strip():
        return sub_id.text.strip()
    return None


def get_text(element: ET.Element, tag: str) -> Optional[str]:
    """Extract stripped text from a direct child tag."""
    child = element.find(tag)
    if child is not None and child.text:
        return child.text.strip()
    return None


__all__ = ["parse", "safe_write", "get_subtype", "get_text", "HARDENED"]
