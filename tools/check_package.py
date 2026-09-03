"""Exercise portable imports from an extracted archive outside the checkout."""
from pathlib import Path
import json
import os
import subprocess
import sys
import tempfile
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from package_release import create_release_package, sha256


def main():
    with tempfile.TemporaryDirectory(prefix="sebx-clean-package-") as temporary:
        root = Path(temporary)
        archive = create_release_package(root, require_exe=False)
        extracted = root / "extracted"
        with zipfile.ZipFile(archive) as zf:
            zf.extractall(extracted)
        manifest = json.loads((extracted / "BUILD-MANIFEST.json").read_text())
        for name, expected in manifest["files"].items():
            if sha256(extracted / name) != expected:
                raise ValueError(f"Bad packaged checksum: {name}")
        env = os.environ.copy()
        env.pop("PYTHONPATH", None)
        env["APPDATA"] = str(root / "appdata")
        code = "import gui_standalone, ui.app, blueprint_document, blueprint_edit, engine_compat, se_assets.se2_catalog, se_render.viewport; from resource_paths import resource_path; from se_assets.compatibility import baseline_catalog; assert resource_path('se_render/shaders/preview.vert').is_file(); assert len(baseline_catalog().definitions) > 1000; print('Clean portable imports and data: PASS')"
        subprocess.run([sys.executable, "-c", code], cwd=extracted, env=env, check=True)


if __name__ == "__main__":
    main()
