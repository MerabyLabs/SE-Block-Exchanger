# v4.0.0 compatibility and release status

This is an **unreleased candidate**, not a certified SE2 release. Publication is
blocked by `release_acceptance.json` until the required live checks have evidence.

## Space Engineers 1

The catalog baseline is the installed **1.210.014 / Steam build 24675677**.
`data/se1_catalog.json` contains 1,503 block definitions plus component metadata
derived from that installation. Game models, textures, and binaries are not bundled.
See the official [1.210 Prosperity announcement](https://support.keenswh.com/spaceengineers/pc/announcement/update-1-210-prosperity).

Conversion uses object-builder type **and** subtype. An empty subtype is valid for
some default weapons; it is not an unknown armor block. Mappings are checked against
the installed catalog when available and the versioned baseline otherwise. Stale,
ambiguous, non-public, different-size, different-footprint and cross-type targets
are rejected before creating a converted copy. Mod profiles do not bypass this check.
They need definitions and an implemented migration before they can safely write.

Light/heavy armor has 116 bijective pairs in the baseline. DLC, weapon and Prototech
tools expose only validated same-type, same-footprint pairs. In particular, the
Prototech reactor uses a different builder type and is **not** a safe subtype swap.
Flat Collectors and decorative replacements are not assumed interchangeable merely
because their names look similar. Disabled categories carry validation diagnostics.

Same-type conversion preserves inventories, orientation, mechanical links and
other XML fields. It does not certify every functional behavior in the game.
Grid-size scaling is restricted to a single armor grid. It changes cell size while
retaining cell coordinates; multiplying coordinates again would disconnect blocks.

Analytics labels matched catalog coverage and estimated/unknown blocks. Partial
totals are not a complete PCU, mass or cost estimate. Ore/ingot calculations and PB
instruction estimates are advisory, not an in-game simulation or compiler result.

## Space Engineers 2

The live acceptance target is **2.4.0.95 / Steam build 24993846**. The experimental
bridge reads actual installed `.def` GUIDs and emits `grid.json` EntityBundles with
native `.container-info` metadata under
`%APPDATA%\SpaceEngineers2\AppData\Blueprints`. It does not write the game's shared
`.index`, invent GUIDs, or silently replace unsupported blocks with armor.

Implemented migration scope is **one grid, 16 armor variants**: cube, slope, corner,
inverted corner; light/heavy; 2.5 m and 0.5 m. Position, orthogonal orientation, color,
build/integrity and representable physics are preserved. Source SE1 entity IDs are
recorded in a hash-bound sidecar for an unchanged round trip. A game-resaved blueprint
requires new SE1 entity IDs, with this limitation reported explicitly.

Functional blocks, mods, skins, deformed armor, mechanical subgrids, block groups,
unmapped ownership and incompatible native sizes/orientations are unsupported.
Conversion rejects these inputs with diagnostics and no output. Validation of an
EntityBundle and its GUIDs is **not** proof that SE2 can open, place, save and reopen it.
No numeric readiness percentage is used as compatibility certification.

Single-grid acceptance and subgrid rejection must be reported separately. The
[official August 2026 SE2 notes](https://2.spaceengineersgame.com/space-engineers-2-smoother-stable-faster/)
still describe incomplete subgrid projection/copy-paste support. SEBX does not claim
to remove that game limitation.

## 3D preview and runtime

The Windows release targets Python 3.11/3.12, CustomTkinter 6.x, NumPy, ModernGL and
Pillow. OpenGL 3.3 is needed for the accelerated renderer. Fallback rendering is
identified in the UI; it is not equivalent to a full game asset preview.

The renderer progressively simplifies expensive scenes: 2,500-block progressive
threshold, 8,000-block huge-scene threshold, 20,000 preview-block cap, and 50,000-block
extreme-scene threshold. These affect the **preview**, not the blueprint or conversion.
Isolate/dissection/shell controls may hide all visible blocks; Reset restores them.

## Reproducing checks

```powershell
python tools/check_runtime.py
python -m ruff check .
python -m mypy se_armor_replacer.py blueprint_converter.py blueprint_scanner.py mapping_profiles.py blueprint_analytics.py update_checker.py engine_compat.py se_assets se_render
python -m pytest -q
python tools/check_package.py
python gui_standalone.py --self-test artifacts/runtime-selftest.json
python tools/check_release_gate.py
```

The final command intentionally fails while release acceptance is on hold. Native
fixture generation is available in `tools/native_se2_acceptance.py`; it reports
serialization separately and never marks in-game acceptance as passed.
