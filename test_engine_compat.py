"""Native engine compatibility contracts, replacing the former synthetic JSON tests."""
import copy
import hashlib
import json
import xml.etree.ElementTree as ET

import numpy as np
import pytest

from engine_compat import (BlueprintFormat, EngineVersionDetector, SE2MigrationBridge,
                           UnsupportedBlueprintError, _quaternion, _rotation)
from se_assets.se2_catalog import HIERARCHY_TYPE, component, validate_bundle
from se_render.orientation import BASE6, orientation_matrix
from tests.native_fixtures import armor_blueprint, catalog_fixture


@pytest.mark.parametrize("size", ["Large", "Small"])
def test_native_roundtrip_preserves_shapes_colors_positions_and_source(tmp_path, size):
    source = armor_blueprint(tmp_path / "source", size, all_shapes=True)
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    catalog = catalog_fixture(tmp_path)
    out, total, changed = SE2MigrationBridge.migrate_se1_to_se2(source, tmp_path / "native", catalog=catalog)
    assert total == changed == 8
    payload = json.loads((out / "grid.json").read_text())
    roots = validate_bundle(payload, catalog)
    assert len(component(roots[0], HIERARCHY_TYPE)["Children"]) == 8
    assert not (out / "blueprint.json").exists()
    assert (out / ".container-info").is_file()
    assert EngineVersionDetector.detect_file_format(out) == BlueprintFormat.SE2_JSON
    returned, total, _ = SE2MigrationBridge.migrate_se2_to_se1(out, tmp_path / "returned", catalog=catalog)
    original = ET.parse(source).findall(".//CubeBlocks/MyObjectBuilder_CubeBlock")
    blocks = ET.parse(returned / "bp.sbc").findall(".//CubeBlocks/MyObjectBuilder_CubeBlock")
    assert total == 8
    for a, b in zip(original, blocks):
        assert a.findtext("EntityId") == b.findtext("EntityId")
        assert a.findtext("SubtypeName") == b.findtext("SubtypeName")
        assert a.find("Min").attrib == b.find("Min").attrib
        assert a.find("BlockOrientation").attrib == b.find("BlockOrientation").attrib
        for axis in "xyz":
            assert float(a.find("ColorMaskHSV").get(axis)) == pytest.approx(float(b.find("ColorMaskHSV").get(axis)))
    assert hashlib.sha256(source.read_bytes()).hexdigest() == before


def test_all_24_block_rotations_roundtrip():
    count = 0
    for forward in BASE6:
        for up in BASE6:
            if abs(np.dot(BASE6[forward], BASE6[up])) > 0.1:
                continue
            matrix = np.array(orientation_matrix(forward, up)).T
            assert np.allclose(_rotation(_quaternion(matrix)), matrix)
            count += 1
    assert count == 24


def test_unknown_blocks_and_subgrids_never_write_output(tmp_path):
    source = armor_blueprint(tmp_path / "source")
    tree = ET.parse(source)
    tree.find(".//SubtypeName").text = "SomeModBlock"
    tree.write(source)
    with pytest.raises(UnsupportedBlueprintError, match="unsupported"):
        SE2MigrationBridge.migrate_se1_to_se2(source, tmp_path / "blocked", catalog=catalog_fixture(tmp_path))
    assert not (tmp_path / "blocked").exists()
    tree = ET.parse(armor_blueprint(tmp_path / "second"))
    tree.find(".//CubeGrids").append(copy.deepcopy(tree.find(".//CubeGrid")))
    tree.write(source)
    with pytest.raises(UnsupportedBlueprintError, match="one grid"):
        SE2MigrationBridge.migrate_se1_to_se2(source, tmp_path / "blocked", catalog=catalog_fixture(tmp_path))


def test_fake_json_and_missing_references_are_rejected(tmp_path):
    fake = tmp_path / "blueprint.json"
    fake.write_text(json.dumps({"engine_target": "SE2_VRAGE3", "grids": []}))
    assert EngineVersionDetector.detect_file_format(fake) == BlueprintFormat.UNKNOWN
    catalog = catalog_fixture(tmp_path)
    source = armor_blueprint(tmp_path / "source")
    out, _, _ = SE2MigrationBridge.migrate_se1_to_se2(source, tmp_path / "native", catalog=catalog)
    payload = json.loads((out / "grid.json").read_text())
    payload["$Value"]["Builders"][0]["Definition"] = "missing"
    with pytest.raises(ValueError, match="Unknown"):
        validate_bundle(payload, catalog)


def test_existing_destination_is_preserved(tmp_path):
    source = armor_blueprint(tmp_path / "source")
    target = tmp_path / "existing"
    target.mkdir()
    sentinel = target / "keep"
    sentinel.write_text("user data")
    with pytest.raises(FileExistsError):
        SE2MigrationBridge.migrate_se1_to_se2(source, target, catalog=catalog_fixture(tmp_path))
    assert sentinel.read_text() == "user data"


def test_report_does_not_infer_compatibility_from_dlc_counts(tmp_path):
    source = armor_blueprint(tmp_path / "source")
    report = EngineVersionDetector.inspect_compatibility(source, catalog=catalog_fixture(tmp_path))
    assert report.catalog_validated and report.se2_migratable
    assert not report.is_se2_compatible
