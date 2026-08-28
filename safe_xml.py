"""
Safe XML parsing helper.

Wraps defusedxml.ElementTree.parse when available to harden against XXE,
billion-laughs, and external-DTD attacks. Falls back to xml.etree.ElementTree
when defusedxml is not installed (e.g. minimal CLI installs without
requirements.txt). Only the parse path is hardened — Element construction and
serialization continue to use the standard library.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import cast

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


__all__ = ["parse", "HARDENED"]
