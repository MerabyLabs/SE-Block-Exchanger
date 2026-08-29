#!/usr/bin/env python3
"""
Space Engineers block conversion engine and CLI.
"""

from __future__ import annotations

import argparse
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set, Tuple

import safe_xml
from mapping_profiles import ProfileManager
from mappings import MappingRegistry, build_registry
from mappings.armor import ARMOR_PAIRS
from version import __version__


class ArmorBlockReplacer:
    """
    Replaces blocks in Space Engineers blueprints.

    Backward compatibility:
    - LIGHT_TO_HEAVY / HEAVY_TO_LIGHT / ARMOR_REPLACEMENTS remain armor-only maps.
    - Default behavior still converts armor only.
    """

    LIGHT_TO_HEAVY = dict(ARMOR_PAIRS)
    HEAVY_TO_LIGHT = {target: source for source, target in LIGHT_TO_HEAVY.items()}
    ARMOR_REPLACEMENTS = LIGHT_TO_HEAVY

    def __init__(
        self,
        verbose: bool = False,
        reverse: bool = False,
        enabled_categories: Optional[Sequence[str]] = None,
        registry: Optional[MappingRegistry] = None,
        include_profiles: bool = True,
        profile_dir: Path = Path("profiles"),
    ):
        self.verbose = verbose
        self.reverse = reverse
        self.replacements_made = 0
        self.blocks_scanned = 0
        self.change_log: List[Tuple[str, str]] = []

        self.registry = registry if registry else build_registry(include_builtin=True)
        self.profile_manager = ProfileManager(profile_dir)
        if include_profiles:
            self._load_profiles()

        if enabled_categories is None:
            enabled_categories = ("armor",)

        self.enabled_categories = self._resolve_categories(enabled_categories)
        self.mapping = self.registry.build_mapping(
            reverse=self.reverse,
            enabled_categories=self.enabled_categories,
        )

    def _load_profiles(self) -> None:
        try:
            self.profile_manager.load_all()
            self.profile_manager.register_profile_categories(self.registry)
        except Exception as exc:
            self.log(f"[WARN] Failed to load profiles: {exc}")

    def _resolve_categories(self, categories: Sequence[str]) -> List[str]:
        normalized = [name.strip().lower() for name in categories if name and name.strip()]
        if not normalized:
            return ["armor"]

        if len(normalized) == 1 and normalized[0] == "all":
            return [category.name for category in self.registry.list_categories()]

        resolved: List[str] = []
        for name in normalized:
            if self.registry.exists(name):
                resolved.append(name)
                continue

            matches = [
                category.name
                for category in self.registry.list_categories()
                if category.name.endswith(f":{name}")
            ]
            if len(matches) == 1:
                resolved.append(matches[0])
                continue

            if not matches:
                raise ValueError(f"Unknown mapping category: {name}")
            raise ValueError(
                f"Category '{name}' is ambiguous; matches: {', '.join(matches)}"
            )
        return resolved

    def list_categories(self) -> List[Tuple[str, str, int]]:
        return [
            (category.name, category.description, len(category.pairs))
            for category in self.registry.list_categories()
        ]

    def log(self, message: str) -> None:
        if self.verbose:
            print(message)

    def find_blueprint_file(self, path: Path) -> Path:
        """Find bp.sbc in file/folder input."""
        if path.is_file() and path.name == "bp.sbc":
            return path
        if path.is_dir():
            bp_file = path / "bp.sbc"
            if bp_file.exists():
                return bp_file
            for item in path.rglob("bp.sbc"):
                return item
        raise FileNotFoundError(f"Could not find bp.sbc in {path}")

    def backup_file(self, file_path: Path) -> Path:
        backup_path = file_path.with_suffix(".sbc.backup")
        counter = 1
        while backup_path.exists():
            backup_path = file_path.with_suffix(f".sbc.backup{counter}")
            counter += 1
        import shutil

        shutil.copy2(file_path, backup_path)
        self.log(f"[INFO] Backup created: {backup_path}")
        return backup_path

    def replace_armor_blocks(self, tree: ET.ElementTree[ET.Element], dry_run: bool = False) -> int:
        """
        Backward-compatible wrapper for replacement.
        """
        return self.replace_blocks(tree, dry_run=dry_run)

    def replace_blocks(
        self,
        tree: ET.ElementTree[ET.Element],
        dry_run: bool = False,
        custom_mapping: Optional[Dict[str, str]] = None,
        selected_subtypes: Optional[Sequence[str] | Set[str]] = None,
    ) -> int:
        """
        Replace block subtype IDs according to the active mapping or custom overrides.
        Supports selective block-by-block conversion via selected_subtypes.
        """
        root = tree.getroot()
        if root is None:
            return 0
        replacements = 0
        self.change_log = []

        effective_mapping = dict(self.mapping)
        if custom_mapping:
            effective_mapping.update(custom_mapping)

        selected_set = set(selected_subtypes) if selected_subtypes is not None else None

        for cube_blocks in root.findall(".//CubeBlocks"):
            for block in cube_blocks.findall("*"):
                self.blocks_scanned += 1
                subtype_name = block.find("SubtypeName")
                subtype_id = block.find("SubtypeId")

                current_subtype = None
                if subtype_name is not None and subtype_name.text:
                    candidate = subtype_name.text.strip()
                    if candidate in effective_mapping:
                        current_subtype = candidate
                if current_subtype is None and subtype_id is not None and subtype_id.text:
                    candidate = subtype_id.text.strip()
                    if candidate in effective_mapping:
                        current_subtype = candidate

                if current_subtype is None:
                    continue

                if selected_set is not None and current_subtype not in selected_set:
                    continue

                new_subtype = effective_mapping[current_subtype]
                self.change_log.append((current_subtype, new_subtype))
                self.log(f"[MAP] {current_subtype} -> {new_subtype}")

                if not dry_run:
                    if subtype_name is not None and subtype_name.text:
                        subtype_name.text = new_subtype
                    if subtype_id is not None and subtype_id.text:
                        subtype_id.text = new_subtype
                replacements += 1

        return replacements

    def process_blueprint(
        self,
        input_path: str,
        output_path: Optional[str] = None,
        create_backup: bool = True,
        dry_run: bool = False,
        custom_mapping: Optional[Dict[str, str]] = None,
        selected_subtypes: Optional[Sequence[str] | Set[str]] = None,
    ) -> Tuple[int, int]:
        """
        Process blueprint file and apply active mappings or selective replacements.
        """
        input_file = self.find_blueprint_file(Path(input_path))
        self.log(f"[INFO] Processing blueprint: {input_file}")

        self.blocks_scanned = 0
        self.replacements_made = 0
        self.change_log = []

        try:
            tree = safe_xml.parse(input_file)
        except Exception as exc:
            raise ValueError(f"Failed to parse XML file: {exc}") from exc

        self.replacements_made = self.replace_blocks(
            tree,
            dry_run=dry_run,
            custom_mapping=custom_mapping,
            selected_subtypes=selected_subtypes,
        )
        if dry_run:
            self.log(f"[INFO] Dry run complete: {self.replacements_made} blocks would change.")
            return self.blocks_scanned, self.replacements_made

        if create_backup and output_path is None:
            self.backup_file(input_file)

        if output_path:
            output_file = Path(output_path)
            output_file.parent.mkdir(parents=True, exist_ok=True)
        else:
            output_file = input_file

        tree.write(output_file, encoding="utf-8", xml_declaration=True)
        self.log(f"[INFO] Output written: {output_file}")

        binary_file = output_file.with_name(output_file.stem + "B5")
        if binary_file.exists():
            try:
                binary_file.unlink()
                self.log(f"[INFO] Removed binary cache file: {binary_file}")
            except Exception as exc:
                self.log(f"[WARN] Could not remove binary cache file {binary_file}: {exc}")

        return self.blocks_scanned, self.replacements_made

    def get_replacement_summary(self) -> str:
        normalized = [name.lower() for name in self.enabled_categories]
        if normalized == ["armor"]:
            direction = "heavy armor with light armor" if self.reverse else "light armor with heavy armor"
            return (
                f"Scanned {self.blocks_scanned} blocks, "
                f"replaced {self.replacements_made} {direction} blocks."
            )

        direction = "reverse" if self.reverse else "forward"
        return (
            f"Scanned {self.blocks_scanned} blocks, replaced {self.replacements_made} "
            f"blocks using {direction} mapping in categories: {', '.join(self.enabled_categories)}."
        )

    def get_dry_run_report(self) -> str:
        if not self.change_log:
            return "No changes would be made."

        lines = [f"Dry-run report: {len(self.change_log)} block(s) would be changed:", ""]
        counts: Dict[str, int] = {}
        for old, new in self.change_log:
            key = f"{old} -> {new}"
            counts[key] = counts.get(key, 0) + 1
        for change, count in sorted(counts.items()):
            lines.append(f"  {change}  (x{count})")
        return "\n".join(lines)


def _split_categories(raw: Optional[str], use_all: bool) -> Optional[List[str]]:
    if use_all:
        return ["all"]
    if not raw:
        return None
    return [item.strip() for item in raw.split(",") if item.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Replace mapped blocks in Space Engineers blueprints "
            "(default: armor light<->heavy)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("input", nargs="?", help="Path to bp.sbc or folder containing it")
    parser.add_argument("-o", "--output", help="Output file path (default: modify in place)")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose output")
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="Do not create backup file when modifying in place",
    )
    parser.add_argument(
        "--reverse",
        action="store_true",
        help="Reverse direction for selected mapping categories",
    )
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without writing")
    parser.add_argument("--list-mappings", action="store_true", help="List active mappings and exit")
    parser.add_argument("--list-categories", action="store_true", help="List available categories")
    parser.add_argument(
        "--categories",
        help="Comma-separated category names (default: armor). Use --all-categories for all.",
    )
    parser.add_argument(
        "--all-categories",
        action="store_true",
        help="Enable all loaded categories for this run",
    )
    parser.add_argument(
        "--profile-dir",
        default="profiles",
        help="Profile directory to auto-load (.sebx-profile / .json)",
    )
    parser.add_argument(
        "--no-profiles",
        action="store_true",
        help="Disable profile auto-loading",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"SE Block Exchanger {__version__}",
    )

    args = parser.parse_args()

    categories = _split_categories(args.categories, args.all_categories)

    try:
        replacer = ArmorBlockReplacer(
            verbose=args.verbose,
            reverse=args.reverse,
            enabled_categories=categories,
            include_profiles=not args.no_profiles,
            profile_dir=Path(args.profile_dir),
        )
    except Exception as exc:
        print(f"Error initializing replacer: {exc}", file=sys.stderr)
        return 1

    if args.list_categories:
        print("Available categories:")
        for name, description, pair_count in replacer.list_categories():
            enabled = " (active)" if name in replacer.enabled_categories else ""
            print(f"  - {name}: {description} [{pair_count} pairs]{enabled}")
        return 0

    if args.list_mappings:
        print("Active mappings:")
        print("=" * 80)
        for source, target in sorted(replacer.mapping.items()):
            print(f"  {source:50} -> {target}")
        print(f"\nTotal active pairs: {len(replacer.mapping)}")
        print(f"Categories: {', '.join(replacer.enabled_categories)}")
        return 0

    if not args.input:
        parser.print_help()
        return 1

    try:
        blocks_scanned, replacements = replacer.process_blueprint(
            args.input,
            output_path=args.output,
            create_backup=not args.no_backup,
            dry_run=args.dry_run,
        )

        mode = "reverse" if args.reverse else "forward"
        if args.dry_run:
            print("\n" + "=" * 60)
            print(f"DRY RUN [{mode}]")
            print("=" * 60)
            print(f"Blocks scanned: {blocks_scanned}")
            print(f"Blocks that would change: {replacements}")
            if replacements > 0:
                print("")
                print(replacer.get_dry_run_report())
            print("\nNo files were modified.")
        else:
            print(f"\nSuccess! [{mode}]")
            print(f"Blocks scanned: {blocks_scanned}")
            print(f"Replacements made: {replacements}")
            print(f"Categories: {', '.join(replacer.enabled_categories)}")

        if replacements == 0:
            print("\nNo matching mapped blocks were found for the selected categories.")
        return 0
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Unexpected error: {exc}", file=sys.stderr)
        if args.verbose:
            import traceback

            traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
