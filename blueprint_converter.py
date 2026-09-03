"""
Blueprint Converter Module
Handles safe copying and block conversion of Space Engineers blueprints.
"""

from __future__ import annotations

import shutil
import hashlib
import tempfile
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import safe_xml
from mappings import MappingRegistry
from se_armor_replacer import ArmorBlockReplacer


def _iter_cube_blocks(root):
    blocks = []
    for cube_blocks in root.findall(".//CubeBlocks"):
        blocks.extend(list(cube_blocks))
    if blocks:
        return blocks
    return root.findall(".//MyObjectBuilder_CubeBlock")


def _apply_subtype_text(block, target: str) -> None:
    subtype_name = block.find("SubtypeName")
    subtype_id = block.find("SubtypeId")
    if subtype_name is not None:
        subtype_name.text = target
    if subtype_id is not None:
        subtype_id.text = target


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
        profile_dir: Optional[Path] = None,
        registry: Optional[MappingRegistry] = None,
    ):
        self.verbose = verbose
        self.reverse = reverse
        self.enabled_categories = list(enabled_categories) if enabled_categories else ["armor"]
        self.replacer = ArmorBlockReplacer(
            verbose=verbose,
            reverse=reverse,
            enabled_categories=self.enabled_categories,
            registry=registry,
            include_profiles=include_profiles,
            profile_dir=profile_dir,
        )
        self.prefix = self._select_prefix()
        self._history: List[Path] = []
        self._owned_outputs: Dict[Path, str] = {}

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

    def _require_blueprint_dir(self, source_path: Path) -> Path:
        source_path = Path(source_path)
        if not source_path.exists():
            raise FileNotFoundError(f"Source blueprint not found: {source_path}")
        if source_path.is_file() and source_path.name.lower() == "bp.sbc":
            source_path = source_path.parent
        if not source_path.is_dir():
            raise ValueError(f"Source must be a directory: {source_path}")
        bp_file = source_path / "bp.sbc"
        if not bp_file.exists():
            raise ValueError(f"No bp.sbc found in: {source_path}")
        return source_path.resolve()

    @staticmethod
    def _output_fingerprint(path: Path) -> str:
        digest = hashlib.sha256()
        if path.resolve() != path or path.is_symlink():
            raise ValueError("Refusing an output path that has been redirected")
        for item in sorted(path.rglob("*")):
            if item.is_symlink() or getattr(item.stat(), "st_file_attributes", 0) & 0x400:
                raise ValueError("Refusing an output containing links or junctions")
            digest.update(item.relative_to(path).as_posix().encode())
            if item.is_file():
                with item.open("rb") as stream:
                    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                        digest.update(chunk)
        return digest.hexdigest()

    def _publish_copy(self, source: Path, destination: Path, transform):
        """Transform an isolated copy before exposing it to the game or history."""
        if destination.parent != source.parent or destination == source:
            raise ValueError("Converted output must be a new sibling blueprint folder")
        if destination.exists():
            raise FileExistsError(f"Converted copy already exists: {destination}")
        with tempfile.TemporaryDirectory(prefix="sebx-stage-", dir=source.parent.parent,
                                         ignore_cleanup_errors=True) as temporary:
            stage = Path(temporary) / "blueprint"
            bp_file = self._copy_blueprint_folder(source, stage)
            result = transform(bp_file)
            fingerprint = self._output_fingerprint(stage.resolve())
            if destination.exists():
                raise FileExistsError(f"Converted copy already exists: {destination}")
            stage.rename(destination)
        self._owned_outputs[destination] = fingerprint
        self._history.append(destination)
        return result

    def _copy_blueprint_folder(self, source_path: Path, dest_path: Path) -> Path:
        if dest_path.exists():
            raise FileExistsError(f"Converted copy already exists: {dest_path}")
        self.log(f"Copying blueprint folder: {source_path.name} -> {dest_path.name}")
        shutil.copytree(source_path, dest_path)
        binary_bp_file = dest_path / "bp.sbcB5"
        if binary_bp_file.exists():
            self.log(f"Removing binary blueprint cache: {binary_bp_file}")
            binary_bp_file.unlink()
        return dest_path / "bp.sbc"

    def _rewrite_with_mapping(self, bp_file: Path, mapping: Dict[str, str]) -> Tuple[int, int]:
        replacer = ArmorBlockReplacer(include_profiles=False)
        replacer.mapping = dict(mapping)
        return replacer.process_blueprint(str(bp_file), create_backup=False)

    def vanillafy_blueprint(self, source_path: Path) -> Tuple[Path, int, int]:
        from mappings.dlc_substitution import DLC_TO_BASE_PAIRS
        return self._create_mapped_copy(source_path, "VANILLA_", DLC_TO_BASE_PAIRS)

    def _create_mapped_copy(self, source_path: Path, prefix: str, mapping: Dict[str, str]) -> Tuple[Path, int, int]:
        source_path = self._require_blueprint_dir(source_path)
        # Validate before creating any output directory.
        validator = ArmorBlockReplacer(include_profiles=False)
        validator.mapping = dict(mapping)
        validator.process_blueprint(str(source_path / "bp.sbc"), dry_run=True)
        destination = source_path.parent / f"{prefix}{source_path.name}"
        scanned, converted = self._publish_copy(source_path, destination,
            lambda path: self._rewrite_with_mapping(path, mapping))
        return destination, scanned, converted

    def create_converted_blueprint(
        self,
        source_path: Path,
        custom_mapping: Optional[Dict[str, str]] = None,
        selected_subtypes: Optional[Iterable[str]] = None,
        custom_suffix: Optional[str] = None,
    ) -> Tuple[Path, int, int]:
        """
        Create a new blueprint folder with converted blocks.
        """
        source_path = self._require_blueprint_dir(source_path)
        self.replacer.process_blueprint(str(source_path / "bp.sbc"), dry_run=True,
                                       custom_mapping=custom_mapping, selected_subtypes=selected_subtypes)
        if custom_suffix:
            if any(c in custom_suffix for c in '/\\:') or custom_suffix in (".", ".."):
                raise ValueError("Conversion suffix must be a plain name, not a path")
            dest_path = source_path.parent / f"{custom_suffix}_{source_path.name}"
        else:
            dest_path = self.get_destination_path(source_path)

        blocks_scanned, replacements = self._publish_copy(source_path, dest_path,
            lambda path: self.replacer.process_blueprint(
            str(path),
            create_backup=False,
            custom_mapping=custom_mapping,
            selected_subtypes=selected_subtypes,
        ))
        self.log(f"Conversion complete ({replacements} replacement(s))")
        return dest_path, blocks_scanned, replacements

    def create_selective_converted_blueprint(
        self,
        source_path: Path,
        custom_mapping: Dict[str, str],
        selected_subtypes: Optional[Iterable[str]] = None,
    ) -> Tuple[Path, int, int]:
        """Create a custom converted copy using per-block source/target pairs."""
        return self.create_converted_blueprint(
            source_path=source_path,
            custom_mapping=custom_mapping,
            selected_subtypes=selected_subtypes,
            custom_suffix="Custom",
        )

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
        dest_path = self.get_destination_path(Path(source_path).resolve())
        if dest_path.exists():
            self._remove_owned_output(dest_path)
            return True
        return False

    def _remove_owned_output(self, path: Path) -> None:
        expected = self._owned_outputs.get(path)
        if expected is None or expected != self._output_fingerprint(path):
            raise ValueError("Output was not created in this session, or has changed; keep it and remove it manually if intended.")
        shutil.rmtree(path)
        self._owned_outputs.pop(path, None)

    def undo_last_conversion(self) -> Optional[Path]:
        """
        Delete the most recently created converted blueprint, if present.
        """
        while self._history:
            path = self._history[-1]
            if path.exists():
                self._remove_owned_output(path)
                self._history.pop()
                self.log(f"Undo conversion: removed {path}")
                return path
            self._history.pop()
        return None

    def scale_grid_size(self, source_path: Path, target_size: str) -> Tuple[Path, int, int]:
        """Scale a single armor grid geometrically, retaining cell coordinates.

        Changing metres per cell must not also scale Min: doing both separates
        adjacent blocks (or rounds several blocks onto the same cell). Functional
        blocks and mechanical grids require dedicated inventory/link migration.
        """
        from se_assets.block_identity import BlockIdentity
        from se_assets.compatibility import conversion_catalog

        source_path = self._require_blueprint_dir(source_path)
        target_size = target_size.strip().capitalize()
        if target_size not in ("Large", "Small"):
            raise ValueError(f"Invalid target grid size: {target_size}")
        tree = safe_xml.parse(source_path / "bp.sbc")
        grids = safe_xml.iter_cube_grids(tree.getroot())
        if len(grids) != 1:
            raise ValueError("Scaling supports a single armor grid; mechanical subgrids are unsupported.")
        grid = grids[0]
        size_element = grid.find("{*}GridSizeEnum")
        if size_element is None or size_element.text not in ("Large", "Small"):
            raise ValueError("Blueprint has no valid grid size.")
        old_size = size_element.text
        if old_size == target_size:
            raise ValueError(f"Blueprint is already {target_size}.")
        catalog = conversion_catalog()
        planned = []
        issues = []
        known_armor = set(ArmorBlockReplacer.LIGHT_TO_HEAVY) | set(ArmorBlockReplacer.HEAVY_TO_LIGHT)
        for block in safe_xml.iter_blocks_in_grid(grid):
            identity = BlockIdentity.from_block(block)
            source = catalog.get_exact(identity.type_id, identity.subtype_id)
            target_name = identity.subtype_id.replace(old_size, target_size, 1)
            target = catalog.get_exact(identity.type_id, target_name)
            if (identity.type_id != "CubeBlock" or identity.subtype_id not in known_armor
                    or source is None or target is None or not target.public
                    or source.cube_size != old_size or target.cube_size != target_size
                    or source.size != target.size):
                issues.append(f"{identity.key}: no safe same-shape armor counterpart")
                continue
            planned.append((block, BlockIdentity(target.type_id, target.subtype_id)))
        if not planned or issues:
            raise ValueError("Scaling blocked: " + "; ".join(issues[:20] or ["no armor blocks"]))
        for block, identity in planned:
            identity.apply(block)
        size_element.text = target_size
        prefix = "SCALED_SMALL_" if target_size == "Small" else "SCALED_LARGE_"
        destination = source_path.parent / f"{prefix}{source_path.name}"
        self._publish_copy(source_path, destination, lambda path: safe_xml.safe_write(tree, path))
        return destination, len(planned), len(planned)

    def survival_sanity_prototech(self, source_path: Path) -> Tuple[Path, int, int]:
        """Replace uncraftable Prototech blocks with survival-craftable vanilla counterparts."""
        from mappings.prototech import get_survival_sanity_mapping

        return self._create_mapped_copy(source_path, "SURVIVAL_READY_", get_survival_sanity_mapping())

    def upgrade_to_prototech(self, source_path: Path) -> Tuple[Path, int, int]:
        """Upgrade standard vanilla blocks to Factorum Prototech equivalents."""
        from mappings.prototech import VANILLA_TO_PROTOTECH_PAIRS

        return self._create_mapped_copy(source_path, "PROTOTECH_", VANILLA_TO_PROTOTECH_PAIRS)
