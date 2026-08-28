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
}

# Scan / convert group headers used by ControlPanel
CATEGORY_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Core", ("armor", "thrusters", "gyros", "reactors", "batteries")),
    ("Ship systems", ("cargo", "cockpits", "doors", "windows", "lights", "conveyor")),
    ("Combat & extra", ("functional", "weapons", "advanced", "dlc_substitution")),
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


def convert_button_text(*, count: int, reverse: bool, enabled: bool, has_blueprint: bool) -> str:
    """Primary CTA copy that states the action in player language."""
    if not has_blueprint:
        return "Select a blueprint to convert"
    if not enabled or count <= 0:
        return "Nothing to convert with current settings"
    direction = "heavy armor" if not reverse else "light armor"
    block_word = "block" if count == 1 else "blocks"
    return f"Convert {count} {block_word} to {direction}"


def mode_label(reverse: bool) -> str:
    return "Heavy → Light" if reverse else "Light → Heavy"


def convertible_total(bp_info) -> int:
    """How many blocks the current mapping would rewrite on this blueprint."""
    counts = getattr(bp_info, "convertible_counts", None) or {}
    return int(sum(counts.values()))


def card_status_label(convertible: int, scanned: bool) -> str:
    if not scanned:
        return "Not scanned yet"
    if convertible <= 0:
        return "Already matches"
    return f"{convertible} ready to convert"
