"""SE1 definition identity, including blocks whose subtype is empty."""

from dataclasses import dataclass
import xml.etree.ElementTree as ET

import safe_xml

XSI_TYPE = "{http://www.w3.org/2001/XMLSchema-instance}type"


def normalize_type(value: str) -> str:
    return value.removeprefix("MyObjectBuilder_")


@dataclass(frozen=True, order=True)
class BlockIdentity:
    type_id: str
    subtype_id: str = ""

    @property
    def key(self) -> str:
        return f"{self.type_id}/{self.subtype_id}"

    @property
    def token(self) -> str:
        """Compatibility token for existing subtype-based lists and profiles."""
        return self.subtype_id or self.key

    @classmethod
    def from_block(cls, block: ET.Element) -> "BlockIdentity":
        builder = block.get(XSI_TYPE) or safe_xml.local_tag(block.tag)
        return cls(normalize_type(builder), safe_xml.get_subtype(block) or "")

    def apply(self, block: ET.Element) -> None:
        block.set(XSI_TYPE, f"MyObjectBuilder_{self.type_id}")
        found = False
        for child in block:
            if safe_xml.local_tag(child.tag) in ("SubtypeName", "SubtypeId"):
                child.text = self.subtype_id
                found = True
        if not found:
            ET.SubElement(block, "SubtypeName").text = self.subtype_id
