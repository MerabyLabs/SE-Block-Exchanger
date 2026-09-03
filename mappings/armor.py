"""Light/heavy armor pairs resolved against the bundled SE1 definition snapshot."""
from se_assets.compatibility import baseline_catalog, validate_pair
from mappings.registry import MappingCategory


def _armor_pairs():
    catalog = baseline_catalog()
    pairs = {}
    for definition in catalog.definitions.values():
        source = definition.subtype_id
        if not definition.public or definition.type_id != "CubeBlock" or "Heavy" in source:
            continue
        candidates = [source.replace("Light", "Heavy")]
        for size in ("Large", "Small"):
            candidates.extend((
                source.replace(f"{size}BlockArmor", f"{size}HeavyBlockArmor"),
                source.replace(f"{size}BlockArmor", f"{size}BlockHeavyArmor"),
                source.replace(f"{size}RoundArmor_", f"{size}HeavyBlockArmorRound"),
            ))
        candidates.extend((
            source.replace("LargeHalf", "LargeHeavyHalf"),
            "Heavy" + source if source.startswith("Half") else source,
        ))
        for target in candidates:
            if target != source and validate_pair(source, target, catalog) is None:
                pairs[source] = target
                break
    return pairs


ARMOR_PAIRS = _armor_pairs()


def get_category() -> MappingCategory:
    return MappingCategory(name="armor", description="Catalog-validated light/heavy armor variants.",
                           pairs=ARMOR_PAIRS, grid_sizes=("Large", "Small"))

