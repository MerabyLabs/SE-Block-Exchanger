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
import secrets
from pathlib import Path
import xml.etree.ElementTree as ET
from typing import Iterator, Optional, Tuple, Union, cast

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
    temp_file = target.with_name(
        f"{target.name}.tmp_{os.getpid()}_{secrets.token_hex(8)}"
    )
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


def iter_cube_blocks(root: ET.Element) -> Iterator[ET.Element]:
    """Yield every direct child of each ``CubeBlocks`` element.

    Space Engineers usually names that child ``MyObjectBuilder_CubeBlock``
    and stores the concrete builder in ``xsi:type``. Some files use the
    concrete builder as the element name (``MyObjectBuilder_Thrust``,
    ``MyObjectBuilder_Cockpit``). Counting only the CubeBlock tag drops
    those blocks from scans, maps, and armor tools while conversion still
    sees them.
    """
    found = False
    for cube_blocks in root.findall(".//CubeBlocks"):
        for block in list(cube_blocks):
            found = True
            yield block
    if found:
        return
    yield from root.findall(".//MyObjectBuilder_CubeBlock")


def min_axis(element: Optional[ET.Element], axis: str, default: int = 0) -> int:
    """Read one ``Min`` axis. Non-numeric text stays at ``default``."""
    if element is None:
        return default
    raw = element.attrib.get(axis)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def min_xyz(block: ET.Element) -> Tuple[int, int, int]:
    """Return ``Min`` x/y/z, or zeros when the element or an axis is unusable."""
    min_elem = block.find("Min")
    return (
        min_axis(min_elem, "x"),
        min_axis(min_elem, "y"),
        min_axis(min_elem, "z"),
    )


__all__ = [
    "parse",
    "safe_write",
    "get_subtype",
    "get_text",
    "iter_cube_blocks",
    "min_axis",
    "min_xyz",
    "HARDENED",
]
