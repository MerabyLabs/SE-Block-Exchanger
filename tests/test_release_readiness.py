"""Release regressions for identity, preservation, native metadata and packaging."""
import copy
import hashlib
import json
import xml.etree.ElementTree as ET

import pytest

from blueprint_converter import BlueprintConverter
from engine_compat import SE2MigrationBridge, UnsupportedBlueprintError
from mappings.registry import build_registry
from se_assets.block_identity import BlockIdentity
from se_assets.compatibility import baseline_catalog, validate_mapping, validate_pair
from se_assets.se2_catalog import HIERARCHY_TYPE, PHYSICS_TYPE, component, validate_bundle
from tests.native_fixtures import armor_blueprint, catalog_fixture
from tools.check_release_gate import validate_gate, REQUIRED
from version import __version__


@pytest.fixture(autouse=True)
def baseline(monkeypatch):
    monkeypatch.setenv("SEBX_SE1_CATALOG", "baseline")


def test_every_exposed_mapping_has_valid_identity_and_footprint():
    catalog = baseline_catalog()
    registry = build_registry(catalog=catalog)
    for category in registry.list_categories():
        valid, errors = validate_mapping(category.pairs, catalog)
        assert not errors
        assert valid == category.pairs
        if not valid:
            assert category.validation_issues
    assert catalog.get_exact("LargeGatlingTurret", "") is not None
    assert catalog.get_exact("LargeMissileTurret", "") is not None
    assert "type changes" in validate_pair("LargeBlockSmallGenerator", "LargePrototechReactor", catalog)


def test_copy_failure_does_not_publish_or_mutate_source(tmp_path, monkeypatch):
    source = armor_blueprint(tmp_path / "source")
    original = source.read_bytes()
    converter = BlueprintConverter(include_profiles=False)
    process = converter.replacer.process_blueprint
    def fail_on_write(*args, **kwargs):
        if kwargs.get("dry_run"):
            return process(*args, **kwargs)
        raise OSError("injected output write failure")
    monkeypatch.setattr(converter.replacer, "process_blueprint", fail_on_write)
    with pytest.raises(OSError, match="injected"):
        converter.create_converted_blueprint(source)
    assert not converter.get_destination_path(source.parent).exists()
    assert source.read_bytes() == original
    assert converter.undo_last_conversion() is None


def test_undo_only_removes_unchanged_session_output(tmp_path):
    source = armor_blueprint(tmp_path / "source")
    converter = BlueprintConverter(include_profiles=False)
    output, _, _ = converter.create_converted_blueprint(source)
    sentinel = output / "user-edit.txt"
    sentinel.write_text("keep this")
    with pytest.raises(ValueError, match="has changed"):
        converter.undo_last_conversion()
    assert sentinel.read_text() == "keep this"
    sentinel.unlink()
    assert converter.undo_last_conversion() == output
    assert not output.exists()
    assert source.exists()


def test_cannot_delete_existing_output_owned_by_another_session(tmp_path):
    source = armor_blueprint(tmp_path / "source")
    output, _, _ = BlueprintConverter(include_profiles=False).create_converted_blueprint(source)
    with pytest.raises(ValueError, match="not created"):
        BlueprintConverter(include_profiles=False).delete_converted_blueprint(source.parent)
    assert output.exists()


@pytest.mark.parametrize("suffix", ["../outside", "..\\outside", "C:outside"])
def test_custom_suffix_cannot_escape_blueprint_root(tmp_path, suffix):
    source = armor_blueprint(tmp_path / "source")
    with pytest.raises(ValueError, match="plain name"):
        BlueprintConverter(include_profiles=False).create_converted_blueprint(source, custom_suffix=suffix)


def test_default_weapon_identity_and_mechanical_fields_survive(tmp_path):
    source = armor_blueprint(tmp_path / "source")
    tree = ET.parse(source)
    grids = tree.find(".//CubeGrids")
    grid = grids[0]
    cubes = grid.find("CubeBlocks")
    weapon = ET.SubElement(cubes, "MyObjectBuilder_CubeBlock")
    BlockIdentity("LargeMissileTurret", "").apply(weapon)
    inventory = ET.SubElement(weapon, "Inventory")
    ET.SubElement(inventory, "Items").text = "preserved fixture"
    rotor = ET.SubElement(cubes, "MyObjectBuilder_CubeBlock")
    BlockIdentity("MotorStator", "LargeStator").apply(rotor)
    ET.SubElement(rotor, "RotorEntityId").text = "778899"
    second = copy.deepcopy(grid)
    second.find("EntityId").text = "223344"
    grids.append(second)
    tree.write(source)
    output, _, _ = BlueprintConverter(include_profiles=False, enabled_categories=["weapons"]).create_converted_blueprint(source)
    changed = ET.parse(output / "bp.sbc")
    assert len(changed.findall(".//CubeGrid")) == 2
    assert changed.findtext(".//Inventory/Items") == "preserved fixture"
    assert changed.findtext(".//RotorEntityId") == "778899"
    identities = [BlockIdentity.from_block(b) for b in changed.findall(".//CubeBlocks/MyObjectBuilder_CubeBlock")]
    assert BlockIdentity("LargeMissileTurret", "LargeCalibreTurret") in identities


@pytest.mark.parametrize("size", ["Large", "Small"])
def test_native_uses_current_container_metadata_and_physics(tmp_path, size):
    source = armor_blueprint(tmp_path / "source", size)
    tree = ET.parse(source)
    grid = tree.find(".//CubeGrid")
    ET.SubElement(grid, "IsStatic").text = "true"
    ET.SubElement(grid, "LinearVelocity", x="1", y="2", z="3")
    tree.write(source)
    catalog = catalog_fixture(tmp_path)
    output, _, _ = SE2MigrationBridge.migrate_se1_to_se2(source, tmp_path / "native", catalog=catalog)
    meta = json.loads((output / ".container-info").read_text())["$Value"]["Meta"]
    assert meta["BaseMetadata"]["Title"] == "source"
    assert "Author" not in meta and "UserInfo" not in meta
    root = validate_bundle(json.loads((output / "grid.json").read_text()), catalog)[0]
    snapshots = json.loads((output / "snapshot").read_text())["$Value"]["Snapshots"]
    assert snapshots[root["Definition"]]["Components"] == [e["Key"] for e in root["ObjectBuilders"]]
    assert component(root, PHYSICS_TYPE)["MotionType"] == "Static"
    assert component(root, PHYSICS_TYPE)["LinearVelocity"] == {"X": 1, "Y": 2, "Z": 3}


@pytest.mark.parametrize("field,value", [("SkinSubtypeId", "ModSkin"), ("Owner", "23"), ("MultiBlockId", "8")])
def test_native_rejects_unrepresentable_block_state(tmp_path, field, value):
    source = armor_blueprint(tmp_path / "source")
    tree = ET.parse(source)
    ET.SubElement(tree.find(".//CubeBlocks/MyObjectBuilder_CubeBlock"), field).text = value
    tree.write(source)
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    with pytest.raises(UnsupportedBlueprintError):
        SE2MigrationBridge.migrate_se1_to_se2(source, tmp_path / "native", catalog=catalog_fixture(tmp_path))
    assert not (tmp_path / "native").exists()
    assert hashlib.sha256(source.read_bytes()).hexdigest() == before


def test_native_rejects_duplicate_ids_and_missing_slots(tmp_path):
    source = armor_blueprint(tmp_path / "source")
    catalog = catalog_fixture(tmp_path)
    output, _, _ = SE2MigrationBridge.migrate_se1_to_se2(source, tmp_path / "native", catalog=catalog)
    payload = json.loads((output / "grid.json").read_text())
    children = component(payload["$Value"]["Builders"][0], HIERARCHY_TYPE)["Children"]
    children[1]["Value"]["$ObjectId"] = children[0]["Value"]["$ObjectId"]
    with pytest.raises(ValueError, match="unique"):
        validate_bundle(payload, catalog)
    children[1]["Value"]["$ObjectId"] = 22
    children[1]["Value"]["ObjectBuilders"][0]["Key"] = "missing-slot"
    with pytest.raises(ValueError, match="Unknown component"):
        validate_bundle(payload, catalog)


def test_release_gate_fails_closed_for_missing_evidence():
    data = {"version": __version__, "status": "APPROVED", "blockers": [],
            "checks": {name: {"status": "PASS", "evidence": ["test evidence"]} for name in REQUIRED}}
    assert not validate_gate(data)
    data["checks"]["se2_single_grid_open_save_reopen"]["evidence"] = []
    assert validate_gate(data)
    assert validate_gate({})
