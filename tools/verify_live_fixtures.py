"""Re-hash isolated fixture sources and copies without opening or modifying them."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from package_release import sha256
import safe_xml


def verify(manifest_path: Path) -> dict:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    results = []
    for item in manifest.get("source_blueprints", []):
        source = Path(item["source"]) / "bp.sbc"
        copy = Path(item["copy"]) / "bp.sbc"
        expected = item["sha256"]
        source_hash = sha256(source)
        copy_hash = sha256(copy)
        results.append({"name": item["name"], "source": str(source), "copy": str(copy),
                        "expected": expected, "source_sha256": source_hash,
                        "copy_sha256": copy_hash, "unchanged": source_hash == copy_hash == expected,
                        "bytes": source.stat().st_size})
    result = {"manifest": str(manifest_path), "passed": bool(results) and all(r["unchanged"] for r in results),
              "fixtures": results}
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = verify(args.manifest)
    if args.output:
        safe_xml.atomic_write_text(args.output, json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))
    if not result["passed"]:
        raise SystemExit("Live fixture hash verification failed")


if __name__ == "__main__":
    main()
