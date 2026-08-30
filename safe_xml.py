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
from dataclasses import dataclass
from pathlib import Path
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional, Union, cast

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


@dataclass(frozen=True)
class FileStamp:
    """Identity of a file on disk so caches can skip an unchanged bp.sbc."""

    path: str
    mtime_ns: int
    size: int

    @classmethod
    def from_path(cls, path: Path) -> "FileStamp":
        stat = Path(path).stat()
        mtime_ns = int(getattr(stat, "st_mtime_ns", int(stat.st_mtime * 1_000_000_000)))
        return cls(str(Path(path)), mtime_ns, int(stat.st_size))


def local_tag(tag: object) -> str:
    """Strip an XML namespace so CubeGrid and {ns}CubeGrid compare equal."""
    if not isinstance(tag, str):
        return ""
    if tag.startswith("{"):
        return tag.rsplit("}", 1)[-1]
    return tag


def index_children(element: ET.Element) -> Dict[str, ET.Element]:
    """Index direct children by local tag. First child wins on duplicates."""
    out: Dict[str, ET.Element] = {}
    for child in element:
        name = local_tag(child.tag)
        if name and name not in out:
            out[name] = child
    return out


def iter_cube_grids(root: ET.Element) -> List[ET.Element]:
    """Unique CubeGrid elements. One XPath, {*} only when the file is namespaced."""
    found = root.findall(".//CubeGrid")
    if not found:
        found = root.findall(".//{*}CubeGrid")
    unique: List[ET.Element] = []
    seen = set()
    for grid in found:
        key = id(grid)
        if key in seen:
            continue
        seen.add(key)
        unique.append(grid)
    return unique


def iter_blocks_in_grid(grid: ET.Element) -> List[ET.Element]:
    """Direct CubeBlocks children — `.//` would double-count nested grids."""
    cube_blocks = None
    for child in grid:
        if local_tag(child.tag) == "CubeBlocks":
            cube_blocks = child
            break
    if cube_blocks is not None:
        children = [child for child in cube_blocks if isinstance(child.tag, str)]
        if children:
            return children
    return (
        grid.findall("./CubeBlocks/MyObjectBuilder_CubeBlock")
        or grid.findall("./{*}CubeBlocks/{*}MyObjectBuilder_CubeBlock")
        or grid.findall("./MyObjectBuilder_CubeBlock")
    )


__all__ = [
    "parse",
    "safe_write",
    "get_subtype",
    "get_text",
    "HARDENED",
    "FileStamp",
    "local_tag",
    "index_children",
    "iter_cube_grids",
    "iter_blocks_in_grid",
]
