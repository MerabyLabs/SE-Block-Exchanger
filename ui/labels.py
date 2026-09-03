"""Human-readable labels for categories, modes, and conversion CTAs."""

from __future__ import annotations

# Built-in mapping keys → short, player-facing names
_CATEGORY_TITLES: dict[str, str] = {
    "armor": "Armor",
    "thrusters": "Thrusters",
    "gyros": "Gyroscopes",
    "reactors": "Reactors",
    "batteries": "Batteries",
    "cargo": "Cargo",
    "cockpits": "Cockpits",
    "doors": "Doors",
    "windows": "Windows",
    "lights": "Lights",
    "conveyor": "Conveyors",
    "functional": "Production & power",
    "weapons": "Weapons",
    "advanced": "Advanced blocks",
    "dlc_substitution": "DLC → vanilla",
    "prototech": "Prototech",
}

_CATEGORY_HINTS: dict[str, str] = {
    "armor": "Light ↔ heavy plates",
    "thrusters": "Small → large (and reverse)",
    "gyros": "Small → large",
    "reactors": "Small → large",
    "batteries": "Small → large",
    "cargo": "Small → large containers",
    "cockpits": "Fighter / industrial seats",
    "doors": "Sliding / airtight doors",
    "windows": "Window variants",
    "lights": "Interior / spotlight",
    "conveyor": "Tubes and junctions",
    "functional": "Refineries, assemblers, generators",
    "weapons": "Gatlings, missiles, interiors",
    "advanced": "Less common block swaps",
    "dlc_substitution": "Paid DLC blocks → free equivalents",
    "prototech": "Vanilla ↔ Factorum Prototech",
}

# Scan / convert group headers used by ControlPanel
CATEGORY_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Core", ("armor", "thrusters", "gyros", "reactors", "batteries")),
    ("Ship systems", ("cargo", "cockpits", "doors", "windows", "lights", "conveyor")),
    ("Combat & extra", ("functional", "weapons", "advanced", "dlc_substitution", "prototech")),
)


def category_label(category_id: str) -> str:
    """Return a sentence-case label for a mapping or profile category id."""
    if not category_id:
        return ""
    known = _CATEGORY_TITLES.get(category_id)
    if known:
        return known
    if category_id.startswith("profile:"):
        rest = category_id[len("profile:") :]
        parts = [p.strip() for p in rest.split(":") if p.strip()]
        pretty = " · ".join(_title_words(p) for p in parts)
        return pretty or category_id
    return _title_words(category_id.replace("_", " "))


def category_hint(category_id: str) -> str:
    """One-line hint shown next to a category checkbox."""
    return _CATEGORY_HINTS.get(category_id, "")


def _title_words(text: str) -> str:
    return " ".join(word.capitalize() for word in text.replace("_", " ").replace("-", " ").split())


def grouped_category_ids(all_ids: list[str]) -> list[tuple[str, list[str]]]:
    """Partition category ids into named groups; leftover ids go under Profiles."""
    remaining = list(all_ids)
    groups: list[tuple[str, list[str]]] = []
    for title, members in CATEGORY_GROUPS:
        present = [m for m in members if m in remaining]
        if present:
            groups.append((title, present))
            for m in present:
                remaining.remove(m)
    if remaining:
        groups.append(("Installed profiles", remaining))
    return groups


def conversion_target_phrase(reverse: bool, category_ids: list[str] | None = None) -> str:
    """Player-facing description of what conversion will produce."""
    ids = [str(name) for name in (category_ids or []) if name]
    lowered = [name.lower() for name in ids]
    if not lowered or lowered == ["armor"]:
        return "heavy armor" if not reverse else "light armor"
    if len(ids) == 1:
        return category_label(ids[0])
    return "the selected categories"


def convert_button_text(
    *,
    count: int,
    reverse: bool,
    enabled: bool,
    has_blueprint: bool,
    category_ids: list[str] | None = None,
) -> str:
    """Primary CTA copy that states the action in player language."""
    if not has_blueprint:
        return "Select a blueprint to convert"
    if not enabled or count <= 0:
        return "Nothing to convert with current settings"
    block_word = "block" if count == 1 else "blocks"
    ids = [str(name) for name in (category_ids or []) if name]
    lowered = [name.lower() for name in ids]
    armor_only = (not lowered) or lowered == ["armor"]
    if armor_only:
        direction = "heavy armor" if not reverse else "light armor"
        return f"Convert {count} {block_word} to {direction}"
    if len(ids) == 1:
        return f"Convert {count} {block_word} ({category_label(ids[0])})"
    return f"Convert {count} matching {block_word}"


def mode_label(reverse: bool) -> str:
    return "Heavy → Light" if reverse else "Light → Heavy"


def convertible_total(bp_info) -> int:
    """How many blocks the current mapping would rewrite on this blueprint."""
    counts = getattr(bp_info, "convertible_counts", None) or {}
    return int(sum(counts.values()))


def armor_convertible_total(bp_info) -> int:
    """Convertible blocks that are light/heavy armor plates, not thrusters/etc."""
    counts = getattr(bp_info, "convertible_counts", None) or {}
    total = 0
    for pair, count in counts.items():
        source, sep, target = str(pair).partition("->")
        if "Armor" in source or "Armor" in target:
            total += int(count)
    return total


def card_status_label(convertible: int, scanned: bool) -> str:
    if not scanned:
        return "Not scanned yet"
    if convertible <= 0:
        return "Already matches"
    return f"{convertible} ready to convert"
