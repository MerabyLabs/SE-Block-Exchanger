"""Non-interactive source/frozen integrity probe. Does not load user blueprints."""
from __future__ import annotations

import importlib
import json
from pathlib import Path
import sys
import traceback

import safe_xml
from resource_paths import resource_path
from version import __version__, __channel__


def run_selftest(report_path: str) -> int:
    report = {"version": __version__, "channel": __channel__, "frozen": bool(getattr(sys, "frozen", False)),
              "python": sys.version, "passed": False, "checks": {}}
    try:
        for module in ("ui.app", "customtkinter", "numpy", "moderngl", "glcontext", "PIL.ImageTk",
                       "blueprint_document", "blueprint_edit", "engine_compat", "se_assets.se2_catalog",
                       "se_assets.dds_loader", "se_assets.mwm_loader", "se_render.viewport", "pb_doctor",
                       "subgrid_engine", "workshop_sync"):
            importlib.import_module(module)
        import customtkinter
        report["checks"]["customtkinter"] = customtkinter.__version__
        if int(customtkinter.__version__.split(".")[0]) != 6:
            raise ValueError("The release requires the tested CustomTkinter 6.x series")
        for item in ("data/se1_catalog.json", "se_render/shaders/preview.vert", "se_render/shaders/preview.frag",
                     "README.md", "INSTALL.md", "COMPATIBILITY.md", "logo.png"):
            if not resource_path(item).is_file():
                raise FileNotFoundError(f"Missing packaged data: {item}")
        from se_assets.compatibility import baseline_catalog
        report["checks"]["se1_definitions"] = len(baseline_catalog().definitions)
        import moderngl
        context = moderngl.create_standalone_context(require=330)
        try:
            report["checks"]["opengl"] = {"version": context.version_code, "renderer": context.info["GL_RENDERER"]}
            program = context.program(vertex_shader=resource_path("se_render/shaders/preview.vert").read_text(),
                                      fragment_shader=resource_path("se_render/shaders/preview.frag").read_text())
            program.release()
        finally:
            context.release()
        report["passed"] = True
    except Exception:
        report["error"] = traceback.format_exc()
    safe_xml.atomic_write_text(Path(report_path), json.dumps(report, indent=2))
    return 0 if report["passed"] else 1
