"""
Extracts embedded C# Programmable Block scripts and metadata from Space Engineers SBC blueprints.
"""

from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional
import xml.etree.ElementTree as ET
import safe_xml


@dataclass
class ExtractedPBScript:
    """Represents a Programmable Block script found in a blueprint."""
    custom_name: str
    entity_id: Optional[str]
    grid_name: Optional[str]
    program_code: str
    storage: Optional[str]
    custom_data: Optional[str]
    default_terminal_arg: Optional[str]
    subtype_name: str
    character_count: int
    line_count: int


class PBScriptExtractor:
    """Scans SBC XML blueprints for Programmable Blocks and extracts their C# scripts."""

    @staticmethod
    def extract_from_file(blueprint_path: Path) -> List[ExtractedPBScript]:
        blueprint_path = Path(blueprint_path)
        if not blueprint_path.is_file():
            return []

        try:
            tree = safe_xml.parse(blueprint_path)
            root = tree.getroot()
            return PBScriptExtractor.extract_from_element(root)
        except Exception:
            return []

    @staticmethod
    def extract_from_element(root: ET.Element) -> List[ExtractedPBScript]:
        scripts: List[ExtractedPBScript] = []

        for grid in root.findall(".//CubeGrid"):
            grid_name_elem = grid.find("CustomName")
            grid_name = grid_name_elem.text.strip() if (grid_name_elem is not None and grid_name_elem.text) else "CubeGrid"

            # Find all Programmable Blocks
            for block in grid.findall(".//CubeBlocks/MyObjectBuilder_CubeBlock"):
                xsi_type = block.attrib.get("{http://www.w3.org/2001/XMLSchema-instance}type", "")
                if "ProgrammableBlock" not in xsi_type:
                    continue

                custom_name_elem = block.find("CustomName")
                custom_name = custom_name_elem.text.strip() if (custom_name_elem is not None and custom_name_elem.text) else "Programmable block"

                entity_id_elem = block.find("EntityId")
                entity_id = entity_id_elem.text.strip() if (entity_id_elem is not None and entity_id_elem.text) else None

                subtype_name = safe_xml.get_subtype(block) or "ProgrammableBlock"

                program_elem = block.find("Program")
                program_code = program_elem.text if (program_elem is not None and program_elem.text) else ""

                storage_elem = block.find("Storage")
                storage = storage_elem.text if (storage_elem is not None and storage_elem.text) else None

                custom_data_elem = block.find("CustomData")
                custom_data = custom_data_elem.text if (custom_data_elem is not None and custom_data_elem.text) else None

                terminal_arg_elem = block.find("DefaultTerminal_argument")
                terminal_arg = terminal_arg_elem.text if (terminal_arg_elem is not None and terminal_arg_elem.text) else None

                scripts.append(
                    ExtractedPBScript(
                        custom_name=custom_name,
                        entity_id=entity_id,
                        grid_name=grid_name,
                        program_code=program_code,
                        storage=storage,
                        custom_data=custom_data,
                        default_terminal_arg=terminal_arg,
                        subtype_name=subtype_name,
                        character_count=len(program_code),
                        line_count=len(program_code.splitlines()) if program_code else 0,
                    )
                )

        return scripts
