"""
Blueprint analytics and resource cost engine.
"""

from __future__ import annotations

import csv
import json
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict, deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional, Set, Tuple

import safe_xml
from resource_paths import resource_path


SEVERITY_INFO = "Info"
SEVERITY_WARNING = "Warning"
SEVERITY_ERROR = "Error"

DLC_KEYWORDS = (
    "scifi",
    "industrial",
    "wasteland",
    "warfare",
    "reskin",
    "decorative",
    "desert",
    "cab",
    "buggy",
    "sparks",
    "vending",
    "storeblock",
)
MECHANICAL_KEYWORDS = ("rotor", "stator", "hinge", "piston")


@dataclass
class HealthIssue:
    severity: str
    code: str
    message: str
    suggestion: str
    fix_id: Optional[str] = None


@dataclass
class BlueprintAnalyticsResult:
    blueprint_name: str
    block_count: int
    block_counts: Dict[str, int]
    category_counts: Dict[str, int]
    unknown_subtypes: List[str]
    component_totals: Dict[str, int]
    ingot_totals: Dict[str, float]
    ore_totals: Dict[str, float]
    pcu_total: int
    mass_total: float
    grid_size: str
    health_issues: List[HealthIssue] = field(default_factory=list)
    known_block_count: int = 0
    estimated_block_count: int = 0
    cost_source: str = "Local cost database"

    @property
    def coverage_text(self) -> str:
        missing = max(0, self.block_count - self.known_block_count - self.estimated_block_count)
        return (f"{self.cost_source}: {self.known_block_count:,}/{self.block_count:,} catalog-matched; "
                f"{self.estimated_block_count:,} estimated; {missing:,} unknown. "
                "Ore, ingot and refining totals are estimates.")

    @property
    def is_complete(self) -> bool:
        return self.block_count == self.known_block_count and self.block_count > 0


@dataclass
class SE2Readiness:
    dlc_count: int
    script_count: int
    subgrid_count: int
    score: int
    status: str


@dataclass
class ConversionComparison:
    mode: str
    block_changes: Dict[str, int]
    before_components: Dict[str, int]
    after_components: Dict[str, int]
    component_delta: Dict[str, int]
    before_ingots: Dict[str, float]
    after_ingots: Dict[str, float]
    ingot_delta: Dict[str, float]
    before_ores: Dict[str, float]
    after_ores: Dict[str, float]
    ore_delta: Dict[str, float]
    before_pcu: int
    after_pcu: int
    pcu_delta: int
    before_mass: float
    after_mass: float
    mass_delta: float
    coverage_notes: str = "Coverage not supplied; totals may be partial."


class BlockCostDatabase:
    """Loads block/component/ore conversion data from JSON."""

    def __init__(self, file_path: Path):
        self.file_path = Path(file_path)
        self.metadata: Dict = {}
        self.component_to_ingot: Dict[str, Dict[str, float]] = {}
        self.ore_yields: Dict[str, float] = {}
        self.blocks: Dict[str, Dict] = {}
        self._infer_cache: Dict[str, Optional[Dict]] = {}
        if not self.file_path.exists():
            return
        with open(self.file_path, "r", encoding="utf-8") as handle:
            data = json.load(handle)

        self.metadata = data.get("metadata", {})
        self.component_to_ingot = data.get("component_to_ingot", {})
        self.ore_yields = data.get("ore_yields", {})
        self.blocks = data.get("blocks", {})

    def get_block(self, subtype: str) -> Optional[Dict]:
        if subtype in self.blocks:
            return self.blocks[subtype]
        if subtype in self._infer_cache:
            return self._infer_cache[subtype]
        inferred = self._infer_cost(subtype)
        self._infer_cache[subtype] = inferred
        return inferred

    def known_block_ids(self) -> List[str]:
        return sorted(self.blocks.keys())

    def category_for_subtype(self, subtype: str) -> str:
        block = self.get_block(subtype)
        if block:
            return block.get("category", "utility")

        lowered = subtype.lower()
        if "armor" in lowered:
            return "armor"
        if "thrust" in lowered:
            return "thrusters"
        if "turret" in lowered or "gatling" in lowered or "artillery" in lowered:
            return "weapons"
        return "utility"

    def component_to_ingot_totals(self, components: Dict[str, int]) -> Dict[str, float]:
        ingots: Dict[str, float] = defaultdict(float)
        for component, qty in components.items():
            conversion = self.component_to_ingot.get(component)
            if not conversion:
                continue
            for ingot, per_component in conversion.items():
                ingots[ingot] += qty * float(per_component)
        return dict(ingots)

    def ingot_to_ore_totals(self, ingots: Dict[str, float]) -> Dict[str, float]:
        ores: Dict[str, float] = defaultdict(float)
        for ingot, qty in ingots.items():
            yield_per_ore = self.ore_yields.get(ingot)
            if not yield_per_ore:
                continue
            ores[f"{ingot} Ore"] += qty / float(yield_per_ore)
        return dict(ores)

    def _infer_cost(self, subtype: str) -> Optional[Dict]:
        """
        Cost fallback for unknown armor variants and common blocks.
        """
        lowered = subtype.lower()
        if "armor" in lowered:
            if "heavy" in lowered:
                steel = 150 if subtype.startswith("Large") else 5
                pcu = 1 if subtype.startswith("Large") else 0
                mass = 15100.0 if subtype.startswith("Large") else 30.0
            else:
                steel = 25 if subtype.startswith("Large") else 1
                pcu = 1 if subtype.startswith("Large") else 0
                mass = 2520.0 if subtype.startswith("Large") else 10.0
            return {
                "category": "armor",
                "pcu": pcu,
                "mass": mass,
                "components": {"SteelPlate": steel},
            }
        if "thrust" in lowered:
            return {
                "category": "thrusters",
                "pcu": 10,
                "mass": 1500.0,
                "components": {
                    "SteelPlate": 40,
                    "Construction": 20,
                    "Motor": 20,
                    "Thrust": 10,
                },
            }
        if "reactor" in lowered or "generator" in lowered:
            return {
                "category": "power",
                "pcu": 25,
                "mass": 2000.0,
                "components": {
                    "SteelPlate": 40,
                    "Construction": 20,
                    "Reactor": 10,
                },
            }
        return None


_NEIGHBOR_DELTAS = (
    (1, 0, 0),
    (-1, 0, 0),
    (0, 1, 0),
    (0, -1, 0),
    (0, 0, 1),
    (0, 0, -1),
)


def occupied_mins_in_cube_blocks(cube_blocks: ET.Element) -> Set[Tuple[int, int, int]]:
    """Min cells already used by cubes in this CubeBlocks list."""
    occupied: Set[Tuple[int, int, int]] = set()
    for block in cube_blocks:
        min_elem = block.find("Min")
        if min_elem is None:
            min_elem = block.find("{*}Min")
        if min_elem is None:
            occupied.add((0, 0, 0))
            continue
        occupied.add(
            (
                int(float(min_elem.attrib.get("x", 0))),
                int(float(min_elem.attrib.get("y", 0))),
                int(float(min_elem.attrib.get("z", 0))),
            )
        )
    return occupied


def first_free_min(occupied: Iterable[Tuple[int, int, int]]) -> Tuple[int, int, int]:
    """Prefer origin; otherwise the first empty neighbor of the occupied blob."""
    taken = {(int(x), int(y), int(z)) for x, y, z in occupied}
    origin = (0, 0, 0)
    if origin not in taken:
        return origin
    seen = {origin}
    queue = deque([origin])
    while queue:
        x, y, z = queue.popleft()
        for dx, dy, dz in _NEIGHBOR_DELTAS:
            nxt = (x + dx, y + dy, z + dz)
            if nxt in seen:
                continue
            if nxt not in taken:
                return nxt
            seen.add(nxt)
            queue.append(nxt)
    return (1, 0, 0)


class BlueprintAnalyticsEngine:
    """Performs analytics, health audits, and conversion cost comparisons."""

    def __init__(self, cost_db_path: Optional[Path] = None):
        self.db = BlockCostDatabase(cost_db_path or resource_path("data", "block_costs.json"))
        self.cost_source = "Local cost database"
        if cost_db_path is None:
            self._load_catalog_costs()

    def _load_catalog_costs(self) -> None:
        from se_assets.compatibility import baseline_catalog
        catalog = baseline_catalog()
        payload = json.loads(resource_path("data", "se1_catalog.json").read_text(encoding="utf-8"))
        masses = payload["component_masses"]
        self.cost_source = f"SE1 {payload['version']} catalog"
        for definition in catalog.definitions.values():
            token = definition.subtype_id or definition.key
            previous = self.db.get_block(token) or {}
            category = previous.get("category", "utility")
            if "Armor" in token:
                category = "armor"
            self.db.blocks[token] = {
                "pcu": definition.pcu,
                "mass": sum(masses.get(c, 0.0) * n for c, n in definition.components.items()),
                "components": definition.components,
                "category": category,
                "catalog_verified": all(c in masses for c in definition.components),
            }

    def analyze_blueprint(self, blueprint_file: Path) -> BlueprintAnalyticsResult:
        tree = safe_xml.parse(blueprint_file)
        return self.analyze_root(
            tree.getroot(),
            blueprint_name=Path(blueprint_file).parent.name,
        )

    def analyze_root(self, root: ET.Element, *, blueprint_name: str) -> BlueprintAnalyticsResult:
        grid_size = self._detect_grid_size(root)
        subtype_counts: Dict[str, int] = Counter()
        thruster_forwards: Dict[str, int] = Counter()
        raw_count = 0
        grids = safe_xml.iter_cube_grids(root)
        if grids:
            blocks = []
            for grid in grids:
                blocks.extend(safe_xml.iter_blocks_in_grid(grid))
        else:
            blocks = root.findall(".//CubeBlocks/MyObjectBuilder_CubeBlock") or root.findall(
                ".//MyObjectBuilder_CubeBlock"
            )
        for block in blocks:
            raw_count += 1
            subtype = self._get_block_subtype(block)
            if not subtype:
                continue
            subtype_counts[subtype] += 1
            if "thrust" in subtype.lower():
                orientation = block.find("BlockOrientation")
                if orientation is not None:
                    forward = orientation.attrib.get("Forward")
                    if forward:
                        thruster_forwards[forward] += 1
        return self.analyze_counts(
            subtype_counts,
            blueprint_name=blueprint_name,
            grid_size=grid_size,
            thruster_forwards=thruster_forwards,
            block_count=raw_count,
        )

    def analyze_counts(
        self,
        subtype_counts: Mapping[str, int],
        *,
        blueprint_name: str,
        grid_size: str = "Unknown",
        thruster_forwards: Optional[Mapping[str, int]] = None,
        thruster_count: Optional[int] = None,
        block_count: Optional[int] = None,
    ) -> BlueprintAnalyticsResult:
        component_totals: Dict[str, int] = defaultdict(int)
        category_totals: Dict[str, int] = defaultdict(int)
        unknown_subtypes: Set[str] = set()
        pcu_total = 0
        mass_total = 0.0
        counted: Dict[str, int] = {}
        known = estimated = 0

        for subtype, raw_count in subtype_counts.items():
            count = int(raw_count)
            if count <= 0 or not subtype:
                continue
            counted[subtype] = counted.get(subtype, 0) + count
            block_cost = self.db.get_block(subtype)
            if not block_cost:
                unknown_subtypes.add(subtype)
                category_totals["unknown"] += count
                continue
            category = block_cost.get("category", "utility")
            if block_cost.get("catalog_verified", subtype in self.db.blocks):
                known += count
            else:
                estimated += count
            category_totals[category] += count
            pcu_total += int(block_cost.get("pcu", 0)) * count
            mass_total += float(block_cost.get("mass", 0.0)) * count
            for component, qty in block_cost.get("components", {}).items():
                component_totals[component] += int(qty) * count

        ingot_totals = self.db.component_to_ingot_totals(component_totals)
        ore_totals = self.db.ingot_to_ore_totals(ingot_totals)
        issues = self._run_health_audit(
            None,
            counted,
            sorted(unknown_subtypes),
            thruster_forwards=thruster_forwards,
            thruster_count=thruster_count,
        )

        named_total = sum(counted.values())
        total_blocks = named_total if block_count is None else max(int(block_count), named_total)
        unnamed = max(0, total_blocks - named_total)
        if unnamed:
            category_totals["unknown"] += unnamed
        if known < total_blocks:
            issues.append(HealthIssue(SEVERITY_WARNING, "partial_cost_coverage",
                f"Costs are partial: {known:,}/{total_blocks:,} blocks have catalog costs.",
                "Unknown blocks are excluded; inferred values are estimates. Check coverage before ordering materials."))
        return BlueprintAnalyticsResult(
            blueprint_name=blueprint_name,
            block_count=total_blocks,
            block_counts=dict(sorted(counted.items())),
            category_counts=dict(sorted(category_totals.items())),
            unknown_subtypes=sorted(unknown_subtypes),
            component_totals=dict(sorted(component_totals.items())),
            ingot_totals=dict(sorted(ingot_totals.items())),
            ore_totals=dict(sorted(ore_totals.items())),
            pcu_total=pcu_total,
            mass_total=round(mass_total, 2),
            grid_size=grid_size,
            health_issues=issues,
            known_block_count=known,
            estimated_block_count=estimated,
            cost_source=self.cost_source,
        )

    def compare_conversion_cost(
        self,
        blueprint_file: Path,
        mapping: Dict[str, str],
        mode: str,
    ) -> ConversionComparison:
        return self.compare_conversion_cost_from_result(
            self.analyze_blueprint(blueprint_file),
            mapping,
            mode,
        )

    def compare_conversion_cost_from_result(
        self,
        result: BlueprintAnalyticsResult,
        mapping: Dict[str, str],
        mode: str,
    ) -> ConversionComparison:
        after_components: Dict[str, int] = defaultdict(int)
        after_pcu = 0
        after_mass = 0.0
        block_changes: Dict[str, int] = {}
        after_known = 0

        for subtype, count in result.block_counts.items():
            target_subtype = mapping.get(subtype, subtype)
            if target_subtype != subtype:
                block_changes[f"{subtype} -> {target_subtype}"] = count

            block_cost = self.db.get_block(target_subtype)
            if not block_cost:
                continue
            if block_cost.get("catalog_verified"):
                after_known += count
            after_pcu += int(block_cost.get("pcu", 0)) * count
            after_mass += float(block_cost.get("mass", 0.0)) * count
            for component, qty in block_cost.get("components", {}).items():
                after_components[component] += int(qty) * count

        before_components = result.component_totals
        before_ingots = result.ingot_totals
        before_ores = result.ore_totals

        after_ingots = self.db.component_to_ingot_totals(after_components)
        after_ores = self.db.ingot_to_ore_totals(after_ingots)

        component_delta = self._int_delta(before_components, after_components)
        ingot_delta = self._numeric_delta(before_ingots, after_ingots)
        ore_delta = self._numeric_delta(before_ores, after_ores)

        return ConversionComparison(
            mode=mode,
            block_changes=dict(sorted(block_changes.items())),
            before_components=dict(sorted(before_components.items())),
            after_components=dict(sorted(after_components.items())),
            component_delta=dict(sorted(component_delta.items())),
            before_ingots=dict(sorted(before_ingots.items())),
            after_ingots=dict(sorted(after_ingots.items())),
            ingot_delta=dict(sorted(ingot_delta.items())),
            before_ores=dict(sorted(before_ores.items())),
            after_ores=dict(sorted(after_ores.items())),
            ore_delta=dict(sorted(ore_delta.items())),
            before_pcu=result.pcu_total,
            after_pcu=after_pcu,
            pcu_delta=after_pcu - result.pcu_total,
            before_mass=result.mass_total,
            after_mass=round(after_mass, 2),
            mass_delta=round(after_mass - result.mass_total, 2),
            coverage_notes=(result.coverage_text + f" After conversion: {after_known:,}/{result.block_count:,} catalog-matched. "
                            "Deltas exclude unknown costs; ore and ingot figures are estimates."),
        )

    @staticmethod
    def export_comparison_csv(comparison: ConversionComparison, destination: Path) -> Path:
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with open(destination, "w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["Coverage", comparison.coverage_notes])
            writer.writerow(["Metric", "Before", "After", "Delta"])
            writer.writerow(["PCU", comparison.before_pcu, comparison.after_pcu, comparison.pcu_delta])
            writer.writerow(["Mass", comparison.before_mass, comparison.after_mass, comparison.mass_delta])
            writer.writerow([])
            writer.writerow(["Component", "Before", "After", "Delta"])
            for key in sorted(set(comparison.before_components) | set(comparison.after_components)):
                writer.writerow(
                    [
                        key,
                        comparison.before_components.get(key, 0),
                        comparison.after_components.get(key, 0),
                        comparison.component_delta.get(key, 0),
                    ]
                )
            writer.writerow([])
            writer.writerow(["Ingot", "Before", "After", "Delta"])
            for key in sorted(set(comparison.before_ingots) | set(comparison.after_ingots)):
                writer.writerow(
                    [
                        key,
                        round(comparison.before_ingots.get(key, 0.0), 3),
                        round(comparison.after_ingots.get(key, 0.0), 3),
                        round(comparison.ingot_delta.get(key, 0.0), 3),
                    ]
                )
            writer.writerow([])
            writer.writerow(["Ore", "Before", "After", "Delta"])
            for key in sorted(set(comparison.before_ores) | set(comparison.after_ores)):
                writer.writerow(
                    [
                        key,
                        round(comparison.before_ores.get(key, 0.0), 3),
                        round(comparison.after_ores.get(key, 0.0), 3),
                        round(comparison.ore_delta.get(key, 0.0), 3),
                    ]
                )
        return destination

    @staticmethod
    def export_comparison_text(comparison: ConversionComparison, destination: Path) -> Path:
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        lines: List[str] = []
        lines.append(f"Mode: {comparison.mode}")
        lines.append(comparison.coverage_notes)
        lines.append(f"PCU: {comparison.before_pcu} -> {comparison.after_pcu} (delta {comparison.pcu_delta:+d})")
        lines.append(
            f"Mass: {comparison.before_mass:.2f} -> {comparison.after_mass:.2f} "
            f"(delta {comparison.mass_delta:+.2f})"
        )
        lines.append("")
        lines.append("Block changes:")
        for change, count in comparison.block_changes.items():
            lines.append(f"  {change} (x{count})")
        lines.append("")
        lines.append("Component deltas:")
        for component, component_delta_value in sorted(comparison.component_delta.items()):
            lines.append(f"  {component}: {component_delta_value:+d}")
        lines.append("")
        lines.append("Ingot deltas:")
        for ingot, ingot_delta_value in sorted(comparison.ingot_delta.items()):
            lines.append(f"  {ingot}: {ingot_delta_value:+.3f}")
        lines.append("")
        lines.append("Ore deltas:")
        for ore, ore_delta_value in sorted(comparison.ore_delta.items()):
            lines.append(f"  {ore}: {ore_delta_value:+.3f}")

        with open(destination, "w", encoding="utf-8") as handle:
            handle.write("\n".join(lines))
        return destination

    def apply_fix(self, blueprint_file: Path, fix_id: str) -> bool:
        tree = safe_xml.parse(blueprint_file)
        root = tree.getroot()
        cube_blocks = root.find(".//CubeBlocks")
        if cube_blocks is None:
            return False

        grid_size = self._detect_grid_size(root)

        if fix_id in ("add_control_block", "add_cockpit", "add_control"):
            subtype = "LargeBlockCockpit" if grid_size == "Large" else "SmallBlockCockpit"
            block_type = "MyObjectBuilder_Cockpit"
        elif fix_id in ("add_power_block", "add_power"):
            subtype = "LargeBlockBatteryBlock" if grid_size == "Large" else "SmallBlockBatteryBlock"
            block_type = "MyObjectBuilder_BatteryBlock"
        else:
            return False

        free = first_free_min(occupied_mins_in_cube_blocks(cube_blocks))
        new_block = ET.SubElement(cube_blocks, "MyObjectBuilder_CubeBlock")
        new_block.set("{http://www.w3.org/2001/XMLSchema-instance}type", block_type)
        ET.SubElement(new_block, "SubtypeName").text = subtype
        ET.SubElement(new_block, "Min").attrib.update(
            {"x": str(free[0]), "y": str(free[1]), "z": str(free[2])}
        )
        ET.SubElement(new_block, "BlockOrientation").attrib.update(
            {"Forward": "Forward", "Up": "Up"}
        )
        safe_xml.safe_write(tree, blueprint_file)
        return True

    @staticmethod
    def _get_block_subtype(block: ET.Element) -> Optional[str]:
        from se_assets.block_identity import BlockIdentity
        identity = BlockIdentity.from_block(block)
        return identity.token if identity.subtype_id or identity.type_id != "CubeBlock" else None

    @staticmethod
    def _detect_grid_size(root: ET.Element) -> str:
        element = root.find(".//CubeGrid/GridSizeEnum")
        if element is not None and element.text:
            return element.text.strip()
        return "Unknown"

    @staticmethod
    def _numeric_delta(before: Mapping[str, float], after: Mapping[str, float]) -> Dict[str, float]:
        keys = set(before.keys()) | set(after.keys())
        return {key: after.get(key, 0) - before.get(key, 0) for key in keys}

    @staticmethod
    def _int_delta(before: Mapping[str, int], after: Mapping[str, int]) -> Dict[str, int]:
        keys = set(before.keys()) | set(after.keys())
        return {key: int(after.get(key, 0) - before.get(key, 0)) for key in keys}

    def _run_health_audit(
        self,
        root: Optional[ET.Element],
        subtype_counts: Dict[str, int],
        unknown_subtypes: List[str],
        thruster_forwards: Optional[Mapping[str, int]] = None,
        thruster_count: Optional[int] = None,
    ) -> List[HealthIssue]:
        issues: List[HealthIssue] = []
        subtype_keys = list(subtype_counts.keys())
        lowered = [s.lower() for s in subtype_keys]

        has_control = any(
            key for key in lowered if "cockpit" in key or "controlseat" in key or "remotecontrol" in key
        )
        has_power = any(
            key
            for key in lowered
            if "battery" in key
            or "reactor" in key
            or "hydrogenengine" in key
            or "solar" in key
            or "wind" in key
        )
        if not has_control:
            issues.append(
                HealthIssue(
                    severity=SEVERITY_ERROR,
                    code="missing_control",
                    message="No control block detected (Cockpit/Control Seat/Remote Control).",
                    suggestion="Add a cockpit or remote control to make the grid pilotable.",
                    fix_id="add_control_block",
                )
            )
        if not has_power:
            issues.append(
                HealthIssue(
                    severity=SEVERITY_ERROR,
                    code="missing_power",
                    message="No power source detected (Battery/Reactor/Hydrogen/Solar/Wind).",
                    suggestion="Add a battery or reactor so functional blocks can run.",
                    fix_id="add_power_block",
                )
            )

        inferred_thrusters = sum(
            int(count) for subtype, count in subtype_counts.items() if "thrust" in subtype.lower()
        )
        if thruster_forwards is not None:
            oriented = sum(int(v) for v in thruster_forwards.values())
            n_blocks = max(inferred_thrusters, oriented)
            if thruster_count is not None:
                n_blocks = max(n_blocks, int(thruster_count))
            thruster_balance = self._thruster_balance_from_dirs(
                Counter(thruster_forwards),
                n_blocks,
            )
        elif root is not None:
            thruster_balance = self._thruster_balance(root)
        elif inferred_thrusters >= 6:
            thruster_balance = self._thruster_balance_from_dirs({}, inferred_thrusters)
        else:
            thruster_balance = None
        if thruster_balance:
            issues.append(
                HealthIssue(
                    severity=SEVERITY_WARNING,
                    code="thruster_imbalance",
                    message=thruster_balance,
                    suggestion="Try balancing thrust directions for safer handling.",
                )
            )

        if unknown_subtypes:
            issues.append(
                HealthIssue(
                    severity=SEVERITY_INFO,
                    code="unknown_blocks",
                    message=f"{len(unknown_subtypes)} block subtype(s) are unknown to the local cost database.",
                    suggestion="These may be modded/DLC blocks or missing cost data entries.",
                )
            )

        return issues

    def _thruster_balance(self, root: ET.Element) -> Optional[str]:
        directions: Counter[str] = Counter()
        thruster_blocks = 0
        for block in root.findall(".//CubeGrid/CubeBlocks/MyObjectBuilder_CubeBlock"):
            subtype = self._get_block_subtype(block)
            if not subtype:
                continue
            if "thrust" not in subtype.lower():
                continue
            thruster_blocks += 1
            orientation = block.find("BlockOrientation")
            if orientation is None:
                continue
            forward = orientation.attrib.get("Forward")
            if forward:
                directions[forward] += 1
        return self._thruster_balance_from_dirs(directions, thruster_blocks)

    @staticmethod
    def _thruster_balance_from_dirs(directions: Mapping[str, int], thruster_blocks: int) -> Optional[str]:
        if thruster_blocks < 6:
            return None
        missing = [
            direction
            for direction in ("Forward", "Backward", "Up", "Down", "Left", "Right")
            if int(directions.get(direction, 0)) == 0
        ]
        if missing:
            return f"Thrusters are missing in direction(s): {', '.join(missing)}."
        counts = [int(directions.get(d, 0)) for d in ("Forward", "Backward", "Up", "Down", "Left", "Right")]
        if min(counts) == 0:
            return None
        if max(counts) / min(counts) >= 2.5:
            return "Thruster distribution appears heavily unbalanced across directions."
        return None


    @staticmethod
    def calculate_refining_time(ore_totals: Dict[str, float], refinery_speed_mult: float = 1.0) -> Dict[str, float]:
        """
        Calculates required refining time in seconds for each ore type based on vanilla Space Engineers
        standard refinery throughput rates (kg/s).
        """
        # Vanilla base processing rates (kg/s)
        ORE_RATES = {
            "iron": 20.0,
            "nickel": 2.0,
            "silicon": 5.0,
            "cobalt": 0.3,
            "magnesium": 0.14,
            "silver": 0.1,
            "gold": 0.08,
            "platinum": 0.005,
            "uranium": 0.004,
            "stone": 20.0,
        }
        mult = max(0.1, refinery_speed_mult)
        times: Dict[str, float] = {}
        for ore, amount in ore_totals.items():
            rate = ORE_RATES.get(ore.lower(), 1.0) * mult
            times[ore] = round(amount / rate, 1) if rate > 0 else 0.0
        return times

    @staticmethod
    def generate_tim_config(component_totals: Dict[str, int]) -> str:
        """Generates configuration string for TIM (Taleden's Inventory Master) LCD displays."""
        lines = ["// TIM Inventory Master Autocrafting Target List"]
        lines.append("!TIM-CLEAR")
        for comp, count in sorted(component_totals.items()):
            lines.append(f"Component:{comp.replace(' ', '')}:{count}")
        return "\n".join(lines)

    @staticmethod
    def generate_isy_config(component_totals: Dict[str, int]) -> str:
        """Generates configuration string for Isy's Inventory Manager autocrafting."""
        lines = ["// Isy's Inventory Manager (IIM) Autocrafting Targets", "// Paste into Custom Data of your Autocrafting LCD"]
        lines.append("[Autocrafting]")
        for comp, count in sorted(component_totals.items()):
            lines.append(f"{comp}={count}")
        return "\n".join(lines)

    @classmethod
    def generate_survival_bom_report(cls, result: BlueprintAnalyticsResult) -> str:
        """Generates a rich, structured Bill of Materials markdown document for survival shipyards."""
        refining_times = cls.calculate_refining_time(result.ore_totals)
        total_refine_sec = sum(refining_times.values())
        hours = int(total_refine_sec // 3600)
        minutes = int((total_refine_sec % 3600) // 60)

        lines = [
            f"# 🏗️ SURVIVAL BILL OF MATERIALS: {result.blueprint_name.upper()}",
            f"**Total Blocks**: {result.block_count:,} | **PCU**: {result.pcu_total:,} | **Dry Mass**: {result.mass_total:,.1f} kg",
            f"**Est. Total Single-Refinery Refining Time**: {hours}h {minutes}m ({total_refine_sec:,.0f}s)",
            "",
            "## ⛏️ RAW ORE EXTRACTION REQUIREMENTS",
            "| Ore Type | Required Ingot (kg) | Estimated Raw Ore Needed (kg) | Refine Time (1x) |",
            "| :--- | :--- | :--- | :--- |",
        ]

        for ore, amount in sorted(result.ore_totals.items()):
            ingot_val = result.ingot_totals.get(ore, 0.0)
            sec = refining_times.get(ore, 0.0)
            m = int(sec // 60)
            s = int(sec % 60)
            t_str = f"{m}m {s}s" if m < 60 else f"{m//60}h {m%60}m"
            lines.append(f"| **{ore.capitalize()}** | {ingot_val:,.1f} kg | **{amount:,.1f} kg** | {t_str} |")

        lines.extend([
            "",
            "## 📦 FABRICATED COMPONENT CHECKLIST",
            "| Component | Quantity Needed |",
            "| :--- | :--- |",
        ])

        for comp, qty in sorted(result.component_totals.items(), key=lambda x: x[1], reverse=True):
            lines.append(f"| {comp} | **{qty:,}** |")

        return "\n".join(lines)

def compute_se2_readiness(block_counts: Dict[str, int]) -> SE2Readiness:
    """Legacy summary API. Counts cannot certify native engine compatibility."""
    return SE2Readiness(
        dlc_count=sum(n for s, n in block_counts.items() if any(k in s.lower() for k in DLC_KEYWORDS)),
        script_count=sum(n for s, n in block_counts.items() if "programmable" in s.lower()),
        subgrid_count=sum(n for s, n in block_counts.items() if any(k in s.lower() for k in MECHANICAL_KEYWORDS)),
        score=0,
        status="NOT_VALIDATED",
    )
