"""Parse an isolated XML copy padded to the documented large-ship size."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import tempfile
import time
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import safe_xml


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--target-bytes", type=int, default=28 * 1024 * 1024)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source = args.source / "bp.sbc" if args.source.is_dir() else args.source
    with tempfile.TemporaryDirectory(prefix="sebx-large-xml-") as temporary:
        target = Path(temporary) / "large-test.sbc"
        shutil.copyfile(source, target)
        with target.open("ab") as stream:
            stream.write(b"\n" * max(0, args.target_bytes - target.stat().st_size))
        started = time.perf_counter()
        root = safe_xml.parse(target).getroot()
        elapsed = time.perf_counter() - started
        result = {"source": str(source), "bytes": target.stat().st_size,
                  "target_bytes": args.target_bytes, "cube_grids": len(safe_xml.iter_cube_grids(root)),
                  "parse_seconds": round(elapsed, 3), "passed": target.stat().st_size >= args.target_bytes}
    safe_xml.atomic_write_text(args.output, json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))
    if not result["passed"]:
        raise SystemExit("Large XML fixture did not reach target size")


if __name__ == "__main__":
    main()
