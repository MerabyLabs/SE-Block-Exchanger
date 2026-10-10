"""Parse and convert edges that used to disagree with the game file."""

from __future__ import annotations

from pathlib import Path

from blueprint_analytics import BlueprintAnalyticsEngine, write_repair_copy
from blueprint_converter import BlueprintConverter
from blueprint_fixtures import write_blueprint_dir
from blueprint_scanner import BlueprintScanner
from mappings.armor_hardening import ArmorHardeningEngine
from se_armor_replacer import ArmorBlockReplacer

TYPED_SHIP = """<?xml version="1.0" encoding="utf-8"?>
<Definitions xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <ShipBlueprints>
    <ShipBlueprint>
      <Id Type="MyObjectBuilder_ShipBlueprintDefinition" Subtype="Typed">
        <SubtypeId>Typed</SubtypeId>
      </Id>
      <DisplayName>Typed</DisplayName>
      <CubeGrids>
        <CubeGrid>
          <GridSizeEnum>Large</GridSizeEnum>
          <CubeBlocks>
            <MyObjectBuilder_CubeBlock xsi:type="MyObjectBuilder_CubeBlock">
              <SubtypeName>LargeBlockArmorBlock</SubtypeName>
              <SubtypeId>LargeBlockArmorBlock</SubtypeId>
              <Min x="0" y="0" z="0" />
            </MyObjectBuilder_CubeBlock>
            <MyObjectBuilder_Cockpit xsi:type="MyObjectBuilder_Cockpit">
              <SubtypeName>LargeBlockCockpit</SubtypeName>
              <SubtypeId>LargeBlockCockpit</SubtypeId>
              <Min x="1" y="0" z="0" />
            </MyObjectBuilder_Cockpit>
          </CubeBlocks>
        </CubeGrid>
      </CubeGrids>
    </ShipBlueprint>
  </ShipBlueprints>
</Definitions>
"""


def _typed_ship(tmp_path: Path) -> Path:
    folder = tmp_path / "Typed"
    folder.mkdir()
    (folder / "bp.sbc").write_text(TYPED_SHIP, encoding="utf-8")
    (folder / "thumb.png").write_text("thumb", encoding="utf-8")
    return folder


def test_scanner_counts_concrete_builder_tags(tmp_path: Path):
    info = BlueprintScanner(enabled_categories=["armor"]).parse_folder(_typed_ship(tmp_path))
    assert info.block_count == 2
    assert info.light_armor_count == 1
    assert sum(info.convertible_counts.values()) == 1


def test_analytics_sees_cockpit_that_is_not_a_cubeblock_tag(tmp_path: Path):
    result = BlueprintAnalyticsEngine().analyze_blueprint(_typed_ship(tmp_path) / "bp.sbc")
    assert result.block_counts["LargeBlockCockpit"] == 1
    assert not any(issue.code == "missing_control" for issue in result.health_issues)


def test_hardening_sees_typed_cockpit_and_leaves_the_original(tmp_path: Path):
    source = _typed_ship(tmp_path)
    before = (source / "bp.sbc").read_bytes()
    result = ArmorHardeningEngine.harden_vital_cores(source, reinforce_radius=2)
    assert (source / "bp.sbc").read_bytes() == before
    assert result.critical_cores_found == 1
    assert result.armor_blocks_hardened == 1
    assert (result.output_path / "thumb.png").is_file()
    copied = (result.output_path / "bp.sbc").read_text(encoding="utf-8")
    assert "LargeHeavyBlockArmorBlock" in copied
    assert "LargeBlockCockpit" in copied
    assert result.output_path.name in copied


def test_subtype_name_is_not_rewritten_from_a_different_subtype_id(tmp_path: Path):
    folder = tmp_path / "Mismatch"
    folder.mkdir()
    (folder / "bp.sbc").write_text(
        """<?xml version="1.0" encoding="utf-8"?>
<Definitions xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <ShipBlueprints><ShipBlueprint><CubeGrids><CubeGrid><CubeBlocks>
    <MyObjectBuilder_Thrust xsi:type="MyObjectBuilder_Thrust">
      <SubtypeName>STR350_Flat</SubtypeName>
      <SubtypeId>LargeBlockArmorBlock</SubtypeId>
    </MyObjectBuilder_Thrust>
    <MyObjectBuilder_CubeBlock>
      <SubtypeId>LargeBlockArmorBlock</SubtypeId>
    </MyObjectBuilder_CubeBlock>
  </CubeBlocks></CubeGrid></CubeGrids></ShipBlueprint></ShipBlueprints>
</Definitions>
""",
        encoding="utf-8",
    )
    replacer = ArmorBlockReplacer(include_profiles=False, enabled_categories=["armor"])
    _scanned, replaced = replacer.process_blueprint(str(folder / "bp.sbc"), create_backup=False)
    text = (folder / "bp.sbc").read_text(encoding="utf-8")
    assert replaced == 1
    assert "STR350_Flat" in text
    assert text.count("LargeHeavyBlockArmorBlock") == 1
    assert "LargeBlockArmorBlock" in text


def test_scale_does_not_copy_a_prefix_onto_a_different_subtype_id(tmp_path: Path):
    folder = tmp_path / "ScaleMismatch"
    folder.mkdir()
    (folder / "bp.sbc").write_text(
        """<?xml version="1.0" encoding="utf-8"?>
<Definitions>
  <ShipBlueprints><ShipBlueprint><CubeGrids><CubeGrid>
    <GridSizeEnum>Large</GridSizeEnum>
    <CubeBlocks>
      <MyObjectBuilder_CubeBlock>
        <SubtypeName>LargeBlockArmorBlock</SubtypeName>
        <SubtypeId>WidgetSmBlock</SubtypeId>
        <Min x="2" y="0" z="0" />
      </MyObjectBuilder_CubeBlock>
    </CubeBlocks>
  </CubeGrid></CubeGrids></ShipBlueprint></ShipBlueprints>
</Definitions>
""",
        encoding="utf-8",
    )
    dest, _scanned, converted = BlueprintConverter(include_profiles=False).scale_grid_size(folder, "Small")
    text = (dest / "bp.sbc").read_text(encoding="utf-8")
    assert converted == 1
    assert "SmallBlockArmorBlock" in text
    assert "WidgetSmBlock" in text
    assert "SmallWidgetSmBlock" not in text


def test_repair_copy_keeps_the_original_and_drops_the_copied_cache(tmp_path: Path):
    source = write_blueprint_dir(tmp_path, "Bare", ["LargeBlockArmorBlock"])
    (source / "bp.sbcB5").write_bytes(b"stale-cache")
    (source / "thumb.png").write_text("thumb", encoding="utf-8")
    before = (source / "bp.sbc").read_bytes()
    dest = write_repair_copy(source, "add_control_block", BlueprintAnalyticsEngine())
    assert (source / "bp.sbc").read_bytes() == before
    assert (source / "bp.sbcB5").is_file()
    assert not (dest / "bp.sbcB5").exists()
    assert (dest / "thumb.png").is_file()
    copied = (dest / "bp.sbc").read_text(encoding="utf-8")
    assert "LargeBlockCockpit" in copied
    assert dest.name in copied
