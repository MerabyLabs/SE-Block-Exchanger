"""
Blueprint Converter Module
Handles safe copying and block conversion of Space Engineers blueprints.
"""

import shutil
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

from se_armor_replacer import ArmorBlockReplacer


class BlueprintConverter:
    """Converts blueprints by copying and applying selected mapping categories."""

    HEAVYARMOR_PREFIX = "HEAVYARMOR_"
    LIGHTARMOR_PREFIX = "LIGHTARMOR_"
    CONVERTED_PREFIX = "CONVERTED_"
    REVERSED_PREFIX = "REVERSED_"

    def __init__(
        self,
        verbose: bool = False,
        reverse: bool = False,
        enabled_categories: Optional[Sequence[str]] = None,
        include_profiles: bool = True,
        profile_dir: Path = Path("profiles"),
    ):
        self.verbose = verbose
        self.reverse = reverse
        self.enabled_categories = list(enabled_categories) if enabled_categories else ["armor"]
        self.replacer = ArmorBlockReplacer(
            verbose=verbose,
            reverse=reverse,
            enabled_categories=self.enabled_categories,
            include_profiles=include_profiles,
            profile_dir=profile_dir,
        )
        self.prefix = self._select_prefix()
        self._history: List[Path] = []

    def _select_prefix(self) -> str:
        normalized = [name.lower() for name in self.enabled_categories]
        only_armor = normalized == ["armor"]
        if only_armor and not self.reverse:
            return self.HEAVYARMOR_PREFIX
        if only_armor and self.reverse:
            return self.LIGHTARMOR_PREFIX
        return self.REVERSED_PREFIX if self.reverse else self.CONVERTED_PREFIX

    def log(self, message: str) -> None:
        if self.verbose:
            print(f"[CONVERTER] {message}")

    def create_converted_blueprint(self, source_path: Path) -> Tuple[Path, int, int]:
        """
        Create a new blueprint folder with converted blocks.
        """
        source_path = Path(source_path)
        if not source_path.exists():
            raise FileNotFoundError(f"Source blueprint not found: {source_path}")
        if not source_path.is_dir():
            raise ValueError(f"Source must be a directory: {source_path}")

        bp_file = source_path / "bp.sbc"
        if not bp_file.exists():
            raise ValueError(f"No bp.sbc found in: {source_path}")

        dest_path = self.get_destination_path(source_path)
        if dest_path.exists():
            self.log(f"Destination exists, removing: {dest_path}")
            shutil.rmtree(dest_path)

        self.log(f"Copying blueprint folder: {source_path.name} -> {dest_path.name}")
        shutil.copytree(source_path, dest_path)

        binary_bp_file = dest_path / "bp.sbcB5"
        if binary_bp_file.exists():
            self.log(f"Removing binary blueprint cache: {binary_bp_file}")
            binary_bp_file.unlink()

        new_bp_file = dest_path / "bp.sbc"
        blocks_scanned, replacements = self.replacer.process_blueprint(
            str(new_bp_file),
            create_backup=False,
        )
        self.log(f"Conversion complete ({replacements} replacement(s))")
        self._history.append(dest_path)
        return dest_path, blocks_scanned, replacements

    def create_heavy_armor_blueprint(self, source_path: Path) -> Tuple[Path, int, int]:
        """
        Backward-compatible wrapper for existing callers.
        """
        return self.create_converted_blueprint(source_path)

    def get_destination_path(self, source_path: Path) -> Path:
        source_path = Path(source_path)
        return source_path.parent / f"{self.prefix}{source_path.name}"

    def check_destination_exists(self, source_path: Path) -> bool:
        return self.get_destination_path(source_path).exists()

    def delete_heavy_armor_blueprint(self, source_path: Path) -> bool:
        """
        Backward-compatible delete method.
        """
        return self.delete_converted_blueprint(source_path)

    def delete_converted_blueprint(self, source_path: Path) -> bool:
        dest_path = self.get_destination_path(source_path)
        if dest_path.exists():
            self.log(f"Deleting converted blueprint: {dest_path}")
            shutil.rmtree(dest_path)
            return True
        return False

    def undo_last_conversion(self) -> Optional[Path]:
        """
        Delete the most recently created converted blueprint, if present.
        """
        while self._history:
            path = self._history.pop()
            if path.exists():
                shutil.rmtree(path)
                self.log(f"Undo conversion: removed {path}")
                return path
        return None

    def scale_grid_size(self, source_path: Path, target_size: str) -> Tuple[Path, int, int]:
        """
        Create a scaled blueprint copy (Large to Small or Small to Large)
        with block counterparts and grid size modifications.
        """
        source_path = Path(source_path)
        if not source_path.exists():
            raise FileNotFoundError(f"Source blueprint not found: {source_path}")
        if not source_path.is_dir():
            raise ValueError(f"Source must be a directory: {source_path}")

        bp_file = source_path / "bp.sbc"
        if not bp_file.exists():
            raise ValueError(f"No bp.sbc found in: {source_path}")

        target_size = target_size.strip().capitalize()
        if target_size not in ("Large", "Small"):
            raise ValueError(f"Invalid target grid size: {target_size}")

        prefix = "SCALED_SMALL_" if target_size == "Small" else "SCALED_LARGE_"
        dest_path = source_path.parent / f"{prefix}{source_path.name}"
        
        if dest_path.exists():
            shutil.rmtree(dest_path)

        shutil.copytree(source_path, dest_path)

        binary_bp_file = dest_path / "bp.sbcB5"
        if binary_bp_file.exists():
            binary_bp_file.unlink()

        new_bp_file = dest_path / "bp.sbc"
        
        # Parse XML, scale the grid size and swap subtypes!
        import safe_xml
        tree = safe_xml.parse(new_bp_file)
        root = tree.getroot()
        
        # 1. Update GridSizeEnum
        grid_size_elements = root.findall(".//CubeGrid/GridSizeEnum")
        for elem in grid_size_elements:
            if elem.text and elem.text.strip().capitalize() != target_size:
                elem.text = target_size
                
        # 2. Swap Subtypes & Scale Coordinates (5:1 ratio between Large 2.5m and Small 0.5m)
        source_prefix = "Large" if target_size == "Small" else "Small"
        dest_prefix = "Small" if target_size == "Small" else "Large"
        scale_factor = 5 if target_size == "Small" else 1 / 5.0
        
        replacements = 0
        blocks_scanned = 0
        
        for cube_blocks in root.findall(".//CubeBlocks"):
            for block in cube_blocks.findall("MyObjectBuilder_CubeBlock"):
                blocks_scanned += 1
                subtype_name = block.find("SubtypeName")
                subtype_id = block.find("SubtypeId")
                
                elem_to_modify = []
                current_val = None
                
                if subtype_name is not None and subtype_name.text:
                    elem_to_modify.append(subtype_name)
                    current_val = subtype_name.text.strip()
                if subtype_id is not None and subtype_id.text:
                    elem_to_modify.append(subtype_id)
                    if not current_val:
                        current_val = subtype_id.text.strip()
                
                if current_val and elem_to_modify:
                    new_val = None
                    if current_val.startswith(source_prefix):
                        new_val = dest_prefix + current_val[len(source_prefix):]
                    elif current_val.startswith(source_prefix.lower()):
                        new_val = dest_prefix.lower() + current_val[len(source_prefix):]
                    elif "Large" in current_val and target_size == "Small":
                        new_val = current_val.replace("Large", "Small")
                    elif "Small" in current_val and target_size == "Large":
                        new_val = current_val.replace("Small", "Large")
                    elif "Lg" in current_val and target_size == "Small":
                        new_val = current_val.replace("Lg", "Sm")
                    elif "Sm" in current_val and target_size == "Large":
                        new_val = current_val.replace("Sm", "Lg")
                    
                    if new_val and new_val != current_val:
                        for elem in elem_to_modify:
                            elem.text = new_val
                        replacements += 1

                # 3. Rescale coordinates so blocks do not overlap or float
                min_elem = block.find("Min")
                if min_elem is not None:
                    try:
                        x = int(min_elem.attrib.get("x", 0))
                        y = int(min_elem.attrib.get("y", 0))
                        z = int(min_elem.attrib.get("z", 0))
                        if target_size == "Small":
                            min_elem.attrib["x"] = str(x * 5)
                            min_elem.attrib["y"] = str(y * 5)
                            min_elem.attrib["z"] = str(z * 5)
                        else:
                            min_elem.attrib["x"] = str(int(x // 5))
                            min_elem.attrib["y"] = str(int(y // 5))
                            min_elem.attrib["z"] = str(int(z // 5))
                    except (ValueError, TypeError):
                        pass
                        
        safe_xml.safe_write(tree, new_bp_file)
        self._history.append(dest_path)
        return dest_path, blocks_scanned, replacements

    def vanillafy_blueprint(self, source_path: Path) -> Tuple[Path, int, int]:
        """
        Create a vanilla-only blueprint copy, stripping all paid DLC blocks.
        """
        source_path = Path(source_path)
        if not source_path.exists():
            raise FileNotFoundError(f"Source blueprint not found: {source_path}")
        
        dest_path = source_path.parent / f"VANILLA_{source_path.name}"
        if dest_path.exists():
            shutil.rmtree(dest_path)

        shutil.copytree(source_path, dest_path)
        binary_bp_file = dest_path / "bp.sbcB5"
        if binary_bp_file.exists():
            binary_bp_file.unlink()

        from mappings.dlc_substitution import DLC_TO_BASE_PAIRS
        import safe_xml
        new_bp_file = dest_path / "bp.sbc"
        tree = safe_xml.parse(new_bp_file)
        root = tree.getroot()

        scanned = 0
        converted = 0
        for block in root.findall(".//CubeGrid/CubeBlocks/MyObjectBuilder_CubeBlock"):
            scanned += 1
            subtype_name = block.find("SubtypeName")
            subtype_id = block.find("SubtypeId")
            
            val = None
            elem = None
            if subtype_name is not None and subtype_name.text:
                val = subtype_name.text.strip()
                elem = subtype_name
            elif subtype_id is not None and subtype_id.text:
                val = subtype_id.text.strip()
                elem = subtype_id

            if val and val in DLC_TO_BASE_PAIRS:
                target = DLC_TO_BASE_PAIRS[val]
                if elem is not None:
                    elem.text = target
                if subtype_name is not None and subtype_name.text:
                    subtype_name.text = target
                if subtype_id is not None and subtype_id.text:
                    subtype_id.text = target
                converted += 1

        safe_xml.safe_write(tree, new_bp_file)
        self._history.append(dest_path)
        return dest_path, scanned, converted

    def survival_sanity_prototech(self, source_path: Path) -> Tuple[Path, int, int]:
        """
        Replace uncraftable Prototech blocks with standard survival-craftable counterparts.
        """
        source_path = Path(source_path)
        if not source_path.exists():
            raise FileNotFoundError(f"Source blueprint not found: {source_path}")

        dest_path = source_path.parent / f"SURVIVAL_READY_{source_path.name}"
        if dest_path.exists():
            shutil.rmtree(dest_path)

        shutil.copytree(source_path, dest_path)
        binary_bp_file = dest_path / "bp.sbcB5"
        if binary_bp_file.exists():
            binary_bp_file.unlink()

        from mappings.prototech import get_survival_sanity_mapping
        sanity_mapping = get_survival_sanity_mapping()
        import safe_xml
        new_bp_file = dest_path / "bp.sbc"
        tree = safe_xml.parse(new_bp_file)
        root = tree.getroot()

        scanned = 0
        converted = 0
        for block in root.findall(".//CubeGrid/CubeBlocks/MyObjectBuilder_CubeBlock"):
            scanned += 1
            subtype_name = block.find("SubtypeName")
            subtype_id = block.find("SubtypeId")

            val = None
            elem = None
            if subtype_name is not None and subtype_name.text:
                val = subtype_name.text.strip()
                elem = subtype_name
            elif subtype_id is not None and subtype_id.text:
                val = subtype_id.text.strip()
                elem = subtype_id

            if val and val in sanity_mapping:
                target = sanity_mapping[val]
                if elem is not None:
                    elem.text = target
                if subtype_name is not None and subtype_name.text:
                    subtype_name.text = target
                if subtype_id is not None and subtype_id.text:
                    subtype_id.text = target
                converted += 1

        safe_xml.safe_write(tree, new_bp_file)
        self._history.append(dest_path)
        return dest_path, scanned, converted

    def upgrade_to_prototech(self, source_path: Path) -> Tuple[Path, int, int]:
        """
        Upgrade standard vanilla blocks to Factorum Prototech endgame equivalents.
        """
        source_path = Path(source_path)
        if not source_path.exists():
            raise FileNotFoundError(f"Source blueprint not found: {source_path}")

        dest_path = source_path.parent / f"PROTOTECH_{source_path.name}"
        if dest_path.exists():
            shutil.rmtree(dest_path)

        shutil.copytree(source_path, dest_path)
        binary_bp_file = dest_path / "bp.sbcB5"
        if binary_bp_file.exists():
            binary_bp_file.unlink()

        from mappings.prototech import VANILLA_TO_PROTOTECH_PAIRS
        import safe_xml
        new_bp_file = dest_path / "bp.sbc"
        tree = safe_xml.parse(new_bp_file)
        root = tree.getroot()

        scanned = 0
        converted = 0
        for block in root.findall(".//CubeGrid/CubeBlocks/MyObjectBuilder_CubeBlock"):
            scanned += 1
            subtype_name = block.find("SubtypeName")
            subtype_id = block.find("SubtypeId")

            val = None
            elem = None
            if subtype_name is not None and subtype_name.text:
                val = subtype_name.text.strip()
                elem = subtype_name
            elif subtype_id is not None and subtype_id.text:
                val = subtype_id.text.strip()
                elem = subtype_id

            if val and val in VANILLA_TO_PROTOTECH_PAIRS:
                target = VANILLA_TO_PROTOTECH_PAIRS[val]
                if elem is not None:
                    elem.text = target
                if subtype_name is not None and subtype_name.text:
                    subtype_name.text = target
                if subtype_id is not None and subtype_id.text:
                    subtype_id.text = target
                converted += 1

        safe_xml.safe_write(tree, new_bp_file)
        self._history.append(dest_path)
        return dest_path, scanned, converted


