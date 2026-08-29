"""
Main Application Window
Integrates all panel components into the Tactical Command Center.
"""

from __future__ import annotations

import os
import sys
import threading
import webbrowser
from pathlib import Path
from typing import Dict, List, Optional, Set

import customtkinter as ctk
from tkinter import filedialog, messagebox

from app_settings import AppSettings, SettingsStore
from blueprint_analytics import BlueprintAnalyticsEngine
from blueprint_converter import BlueprintConverter
from blueprint_scanner import BlueprintInfo, BlueprintScanner
from mapping_profiles import ProfileManager
from mappings import build_registry
from se_armor_replacer import ArmorBlockReplacer
from ui.blueprint_panel import BlueprintPanel
from ui.control_panel import ControlPanel
from ui.dragdrop_windows import WindowsFileDropTarget
from ui.footer import Footer
from ui.header import Header
from ui.preview_panel import PreviewPanel
from ui.profile_editor import ProfileEditorDialog
from ui.theme import TacticalTheme
from ui.widgets.toast import ToastManager
from update_checker import UpdateChecker, UpdateInfo
from version import __version__


def get_resource_path(relative_path: str) -> str:
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(base, relative_path)


class TacticalCommandCenter(ctk.CTk):
    """Main application window with tactical hologram interface."""

    def __init__(self):
        self.settings_store = SettingsStore()
        self.settings: AppSettings = self.settings_store.load()
        TacticalTheme.apply(self.settings.appearance_mode)
        super().__init__()

        self.title("SE BLOCK EXCHANGER // TACTICAL COMMAND CENTER")
        self.geometry("1360x900")
        self.configure(fg_color=TacticalTheme.BG_DARK)
        self.minsize(1080, 700)
        self._set_icon()

        self.profile_manager = ProfileManager(Path("profiles"))
        self.profile_manager.load_all()
        self.registry = build_registry(include_builtin=True)
        self.profile_manager.register_profile_categories(self.registry)

        self.enabled_categories = self._resolve_enabled_categories(self.settings.enabled_categories)
        self.conversion_mode = "light_to_heavy"

        self.scanner = BlueprintScanner(registry=self.registry, enabled_categories=self.enabled_categories)
        self.converter = self._build_converter()
        self.analytics_engine = BlueprintAnalyticsEngine()
        self.update_checker = UpdateChecker(cache_hours=self.settings.cache_hours)

        self.selected_blueprint: Optional[BlueprintInfo] = None
        self.blueprints: List[BlueprintInfo] = []
        self.custom_blueprint_dir: Optional[str] = None
        self._converted_count = 0
        self._pending_select_name: Optional[str] = None
        self._undo_stack: List[Path] = []
        self._latest_analytics = None
        self._latest_comparison = None
        self._latest_update: Optional[UpdateInfo] = None
        self._profile_editor: Optional[ProfileEditorDialog] = None

        self._build_ui()
        self.toasts = ToastManager(self)
        self._create_help_menu()
        self._bind_shortcuts()
        self._setup_drag_drop()
        self._center_window()

        self.header.set_blueprint_count(0)
        self.header.set_recent_dirs(self.settings.recent_blueprint_dirs)
        self.blueprint_panel.set_recent_blueprints(self.settings.recent_blueprints)
        self.header.set_appearance_mode(self.settings.appearance_mode)
        self.control_panel.set_category_options(
            self.registry.list_categories(),
            self.enabled_categories,
        )

        self.after(200, self.load_blueprints_async)
        if self.settings.auto_check_updates:
            self.after(900, self._check_updates_async)

    def _safe_after(self, ms: int, func, *args):
        try:
            if not self.winfo_exists():
                return
            self.after(ms, func, *args)
        except Exception:
            pass  # Tk is already torn down

    # ------------------------------------------------------------------
    # Bootstrapping
    # ------------------------------------------------------------------

    def _build_converter(self) -> BlueprintConverter:
        return BlueprintConverter(
            verbose=False,
            reverse=(self.conversion_mode == "heavy_to_light"),
            enabled_categories=self.enabled_categories,
            include_profiles=True,
            profile_dir=Path("profiles"),
        )

    def _resolve_enabled_categories(self, requested: List[str]) -> List[str]:
        known = {category.name.lower(): category.name for category in self.registry.list_categories()}
        resolved = [known[name.lower()] for name in requested if name and name.lower() in known]
        if not resolved:
            resolved = ["armor"]
        return resolved

    def _set_icon(self):
        try:
            icon_path = get_resource_path("app_icon.ico")
            if os.path.exists(icon_path):
                self.iconbitmap(icon_path)
        except Exception:
            pass  # icon is optional; missing .ico must not block startup

    def _center_window(self):
        self.update_idletasks()
        w = self.winfo_width()
        h = self.winfo_height()
        x = (self.winfo_screenwidth() // 2) - (w // 2)
        y = (self.winfo_screenheight() // 2) - (h // 2)
        self.geometry(f"{w}x{h}+{x}+{y}")

    def _build_ui(self):
        self.header = Header(
            self,
            on_rescan=self.load_blueprints_async,
            on_browse=self.browse_blueprint_dir,
            on_appearance_change=self.set_appearance_mode,
            on_recent_dir_select=self._select_recent_dir,
            on_open_profiles=self.open_profile_editor,
            on_show_changelog=self.show_changelog_window,
        )
        self.header.pack(fill="x", padx=10, pady=(10, 6))

        content = ctk.CTkFrame(self, fg_color="transparent")
        content.pack(fill="both", expand=True, padx=10, pady=0)
        content.columnconfigure(0, weight=0, minsize=330)
        content.columnconfigure(1, weight=1, minsize=420)
        content.columnconfigure(2, weight=0, minsize=340)
        content.rowconfigure(0, weight=1)

        self.blueprint_panel = BlueprintPanel(
            content,
            on_select=self.on_blueprint_select,
            on_recent_select=self._on_recent_blueprint_pick,
        )
        self.blueprint_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 3))

        self.preview_panel = PreviewPanel(
            content,
            on_run_preview=self.run_dry_run_preview,
            on_export_csv=self.export_comparison_csv,
            on_export_txt=self.export_comparison_txt,
            on_apply_fix=self.apply_health_fix,
            on_vanillafy=self.vanillafy_blueprint,
            on_scale_grid=self.scale_grid_choice,
            on_survival_sanity=self.survival_sanity_blueprint,
            on_upgrade_prototech=self.upgrade_prototech_blueprint,
            on_workshop_sync=self.import_workshop_blueprint,
            on_selective_convert=self.selective_convert_blueprint,
            on_migrate_se2=self.migrate_se2_blueprint,
            on_split_subgrids=self.split_active_blueprint_subgrids,
            on_apply_skin_palette=self.apply_active_skin_palette,
            on_harden_armor=self.harden_active_armor,
            on_lightweight_armor=self.lightweight_active_armor,
        )
        self.preview_panel.grid(row=0, column=1, sticky="nsew", padx=3)

        self.control_panel = ControlPanel(
            content,
            on_convert=self.convert_blueprint,
            on_batch_convert=self.batch_convert,
            on_mode_change=self.set_conversion_mode,
            on_categories_change=self.set_enabled_categories,
            on_undo=self.undo_last_conversion,
        )
        self.control_panel.grid(row=0, column=2, sticky="nsew", padx=(3, 0))

        self.footer = Footer(self, on_update_click=self.open_latest_release)
        self.footer.pack(fill="x", padx=10, pady=(6, 10))

    def _create_help_menu(self):
        import tkinter as tk

        menubar = tk.Menu(self)

        # File menu
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Open Blueprint Directory (Ctrl+O)", command=self.browse_blueprint_dir)
        file_menu.add_command(label="Import Workshop / Mod.io Blueprint...", command=self.import_workshop_blueprint)
        file_menu.add_command(label="Refresh Blueprints (F5)", command=self.load_blueprints_async)
        file_menu.add_separator()
        file_menu.add_command(label="Create Desktop Shortcut", command=self.create_desktop_shortcut)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.destroy)
        menubar.add_cascade(label="File", menu=file_menu)

        # Help menu
        help_menu = tk.Menu(menubar, tearoff=0)
        self._auto_update_var = tk.BooleanVar(value=self.settings.auto_check_updates)
        help_menu.add_checkbutton(
            label="Auto-check updates on startup",
            variable=self._auto_update_var,
            command=self._toggle_auto_update_checks,
        )
        help_menu.add_separator()
        help_menu.add_command(label="View Changelog", command=self.show_changelog_window)
        help_menu.add_command(label="Discord Community", command=lambda: webbrowser.open("https://discord.com/"))
        help_menu.add_command(
            label="Report an Issue",
            command=lambda: webbrowser.open("https://github.com/MerabyLabs/SE-Block-Exchanger/issues"),
        )
        menubar.add_cascade(label="Help", menu=help_menu)
        self.configure(menu=menubar)

    def _toggle_auto_update_checks(self):
        self.settings.auto_check_updates = bool(self._auto_update_var.get())
        self.settings_store.save(self.settings)
        state = "enabled" if self.settings.auto_check_updates else "disabled"
        self.footer.set_status(f"AUTO UPDATE CHECKS {state.upper()}")

    def _bind_shortcuts(self):
        self.bind_all("<Control-o>", lambda event: self.browse_blueprint_dir())
        self.bind_all("<Control-r>", lambda event: self.convert_blueprint())
        self.bind_all("<Control-z>", lambda event: self.undo_last_conversion())
        self.bind_all("<F5>", lambda event: self.load_blueprints_async())

    def _setup_drag_drop(self):
        self._drop_target = WindowsFileDropTarget(self, self._handle_dropped_paths)
        try:
            enabled = self._drop_target.enable()
            if enabled:
                self.footer.set_status("DRAG & DROP ENABLED")
        except Exception:
            self.footer.set_status("DRAG & DROP UNAVAILABLE")

    # ------------------------------------------------------------------
    # Settings and appearance
    # ------------------------------------------------------------------

    def set_appearance_mode(self, mode: str):
        normalized = TacticalTheme.normalize_appearance_mode(mode)
        ctk.set_appearance_mode(normalized)
        self.settings.appearance_mode = normalized
        self.settings_store.save(self.settings)
        self.footer.set_status(f"APPEARANCE: {normalized.upper()}")

    def _select_recent_dir(self, directory: str):
        self.custom_blueprint_dir = directory
        self.footer.set_status(f"DIR: {directory}")
        self.load_blueprints_async()

    def _on_recent_blueprint_pick(self, name: str):
        self.footer.set_status(f"RECENT BLUEPRINT: {name}")

    # ------------------------------------------------------------------
    # Registry / profiles
    # ------------------------------------------------------------------

    def _rebuild_registry(self):
        self.profile_manager.load_all()
        self.registry = build_registry(include_builtin=True)
        self.profile_manager.register_profile_categories(self.registry)
        self.enabled_categories = self._resolve_enabled_categories(self.enabled_categories)
        self.scanner = BlueprintScanner(registry=self.registry, enabled_categories=self.enabled_categories)
        self.converter = self._build_converter()
        self.control_panel.set_category_options(self.registry.list_categories(), self.enabled_categories)
        self.settings.enabled_categories = list(self.enabled_categories)
        self.settings_store.save(self.settings)

    def open_profile_editor(self):
        if self._profile_editor and self._profile_editor.winfo_exists():
            self._profile_editor.focus()
            return
        self._profile_editor = ProfileEditorDialog(
            self,
            profile_manager=self.profile_manager,
            on_profiles_changed=self._on_profiles_changed,
            get_sample_blueprint=self._get_selected_blueprint_file,
        )
        self._profile_editor.grab_set()

    def _on_profiles_changed(self):
        self._rebuild_registry()
        self.toasts.toast("Profiles reloaded and registry refreshed.", level="success")
        self.load_blueprints_async()

    # ------------------------------------------------------------------
    # Update checker
    # ------------------------------------------------------------------

    def _check_updates_async(self):
        def task():
            try:
                info = self.update_checker.check_for_updates(force=False)
                self.after(0, lambda: self._on_update_checked(info))
            except Exception:
                pass  # offline / GitHub rate-limit: skip the update badge silently

        threading.Thread(target=task, daemon=True).start()

    def _on_update_checked(self, info: UpdateInfo):
        self._latest_update = info
        if info.available:
            self.footer.show_update(info.latest_version)
            self.toasts.toast(
                f"Version {info.latest_version} available (current {info.current_version}).",
                level="info",
                duration=4500,
            )

    def open_latest_release(self):
        if self._latest_update and self._latest_update.release_url:
            webbrowser.open(self._latest_update.release_url)

    # ------------------------------------------------------------------
    # Drag and drop
    # ------------------------------------------------------------------

    def _handle_dropped_paths(self, paths: List[str]):
        if not paths:
            return
        raw_path = Path(paths[0])
        if raw_path.is_file() and raw_path.name.lower() == "bp.sbc":
            blueprint_dir = raw_path.parent
            self._pending_select_name = blueprint_dir.name
            self.custom_blueprint_dir = str(blueprint_dir.parent)
        elif raw_path.is_dir() and (raw_path / "bp.sbc").exists():
            self._pending_select_name = raw_path.name
            self.custom_blueprint_dir = str(raw_path.parent)
        elif raw_path.is_dir():
            self._pending_select_name = None
            self.custom_blueprint_dir = str(raw_path)
        else:
            self.toasts.toast(f"Unsupported drop target: {raw_path}", level="warning")
            return

        self.settings_store.add_recent_dir(self.settings, self.custom_blueprint_dir)
        self.header.set_recent_dirs(self.settings.recent_blueprint_dirs)
        self.footer.set_status(f"DROPPED: {raw_path}")
        self.load_blueprints_async()

    # ------------------------------------------------------------------
    # Category selection
    # ------------------------------------------------------------------

    def set_enabled_categories(self, categories: List[str]):
        if not categories:
            categories = ["armor"]
        previous = list(self.enabled_categories)
        try:
            self.scanner.set_enabled_categories(categories)
            self.enabled_categories = categories
            self.settings.enabled_categories = list(categories)
            self.settings_store.save(self.settings)
            self.converter = self._build_converter()
            self.footer.set_status(f"CATEGORIES: {', '.join(categories)}")
            if self.selected_blueprint:
                self.refresh_analytics_async()
        except Exception as exc:
            self.scanner.set_enabled_categories(previous)
            self.enabled_categories = previous
            self.control_panel.set_category_options(self.registry.list_categories(), self.enabled_categories)
            self.toasts.toast(f"Invalid category combination: {exc}", level="error", duration=6000)

    # ------------------------------------------------------------------
    # Blueprint loading
    # ------------------------------------------------------------------

    def load_blueprints_async(self):
        self.footer.set_status("SCANNING BLUEPRINTS...")

        def load_task():
            try:
                scan_dir = self.custom_blueprint_dir or None
                results = self.scanner.scan_blueprints(scan_dir)
                self.after(0, lambda res=results: self._on_blueprints_loaded(res))
            except FileNotFoundError:
                self.after(0, self._on_scan_not_found)
            except Exception as exc:
                error_message = str(exc)
                self.after(0, lambda msg=error_message: self._show_error(f"Scan failed: {msg}"))

        threading.Thread(target=load_task, daemon=True).start()

    def _on_blueprints_loaded(self, results):
        self.blueprints = list(results)
        count = len(self.blueprints)
        self.header.set_blueprint_count(count)
        self.footer.set_status("BLUEPRINTS LOADED")
        self.footer.set_scanned(count)
        self.blueprint_panel.set_blueprints(self.blueprints)
        self.blueprint_panel.set_recent_blueprints(self.settings.recent_blueprints)

        if self._pending_select_name:
            found = self.blueprint_panel.select_blueprint_by_name(self._pending_select_name)
            self._pending_select_name = None
            if not found:
                self.toasts.toast("Dropped blueprint was not found in scanned directory.", level="warning")

    def _on_scan_not_found(self):
        self.blueprints = []
        self.header.set_blueprint_count(0)
        self.footer.set_status("NO SE INSTALL DETECTED")
        self.blueprint_panel.set_blueprints([])
        messagebox.showwarning(
            "Blueprint Directory Not Found",
            "Space Engineers blueprint directory was not found.\n\n"
            "Use BROWSE or drag/drop a blueprint folder.",
        )

    def browse_blueprint_dir(self):
        chosen = filedialog.askdirectory(title="Select Blueprint Directory", mustexist=True)
        if chosen:
            self.custom_blueprint_dir = chosen
            self.settings_store.add_recent_dir(self.settings, chosen)
            self.header.set_recent_dirs(self.settings.recent_blueprint_dirs)
            self.footer.set_status(f"DIR: {chosen}")
            self.load_blueprints_async()

    # ------------------------------------------------------------------
    # Selection handling
    # ------------------------------------------------------------------

    def on_blueprint_select(self, bp: BlueprintInfo):
        self.selected_blueprint = bp
        self.settings_store.add_recent_blueprint(self.settings, bp.display_name)
        self.blueprint_panel.set_recent_blueprints(self.settings.recent_blueprints)

        self.control_panel.update_details(bp)
        self.preview_panel.update_intel(bp, self.conversion_mode)
        self.preview_panel.load_xml(bp.path / "bp.sbc", f"SOURCE: {bp.name}")
        self._update_convert_state()
        self.footer.set_status(f"SELECTED: {bp.display_name}")
        self.refresh_analytics_async()

    def _get_selected_blueprint_file(self) -> Optional[str]:
        if not self.selected_blueprint:
            return None
        return str(self.selected_blueprint.path / "bp.sbc")

    # ------------------------------------------------------------------
    # Conversion mode
    # ------------------------------------------------------------------

    def set_conversion_mode(self, mode: str):
        self.conversion_mode = mode
        self.converter = self._build_converter()
        self._update_convert_state()
        if self.selected_blueprint:
            self.preview_panel.update_intel(self.selected_blueprint, mode)
            self.refresh_analytics_async()
        self.footer.set_status(f"MODE: {mode.replace('_', ' ').upper()}")

    def _update_convert_state(self):
        if not self.selected_blueprint:
            self.control_panel.set_convert_enabled(False)
            return

        bp = self.selected_blueprint
        if self.conversion_mode == "light_to_heavy":
            has_source = bp.light_armor_count > 0
        else:
            has_source = bp.heavy_armor_count > 0

        if any(category.lower() != "armor" for category in self.enabled_categories):
            has_source = has_source or any(bp.category_counts.get(name, 0) > 0 for name in self.enabled_categories)
        self.control_panel.set_convert_enabled(has_source)

    # ------------------------------------------------------------------
    # Conversion operations
    # ------------------------------------------------------------------

    def convert_blueprint(self):
        if not self.selected_blueprint:
            return
        bp = self.selected_blueprint
        mode_name = "reverse" if self.conversion_mode == "heavy_to_light" else "forward"
        category_text = ", ".join(self.enabled_categories)

        confirm = messagebox.askyesno(
            "Confirm Conversion",
            f"Convert blueprint '{bp.display_name}'?\n\n"
            f"Mode: {mode_name}\n"
            f"Categories: {category_text}\n\n"
            f"This creates a new prefixed blueprint folder.",
            icon="warning",
        )
        if not confirm:
            return

        self.control_panel.set_convert_enabled(False)
        self.control_panel.progress.start_indeterminate("Converting blueprint...")
        self.footer.set_status("CONVERTING...")

        def task():
            try:
                dest, scanned, converted = self.converter.create_converted_blueprint(bp.path)
                self.after(0, lambda: self._on_conversion_complete(dest, scanned, converted))
            except Exception as exc:
                error_message = str(exc)
                self.after(0, lambda msg=error_message: self._on_conversion_error(msg))

        threading.Thread(target=task, daemon=True).start()

    def _on_conversion_complete(self, dest_path: Path, scanned: int, converted: int):
        self.control_panel.progress.stop()
        self._converted_count += converted
        self._undo_stack.append(dest_path)
        self.footer.set_scanned(scanned)
        self.footer.set_converted(self._converted_count)
        self.footer.set_status("CONVERSION COMPLETE")
        self._update_convert_state()

        self.preview_panel.load_xml(dest_path / "bp.sbc", f"CONVERTED: {dest_path.name}")
        self.preview_panel.switch_to_xml()
        self.toasts.toast(
            f"Converted {converted} block(s) using {', '.join(self.enabled_categories)}.",
            level="success",
        )
        self.load_blueprints_async()

    def _on_conversion_error(self, error_msg: str):
        self.control_panel.progress.stop()
        self._update_convert_state()
        self.footer.set_status("ERROR", TacticalTheme.RED_PRIMARY)
        self.toasts.toast(f"Conversion failed: {error_msg}", level="error", duration=5000)

    def vanillafy_blueprint(self):
        if not self.selected_blueprint:
            return
        bp = self.selected_blueprint

        confirm = messagebox.askyesno(
            "Vanilla-fy Blueprint",
            f"Replace all premium DLC blocks in '{bp.display_name}' with their base game (Vanilla) counterparts?\n\n"
            f"This will create a new prefixed blueprint folder (e.g. CONVERTED_{bp.name}).",
            icon="question",
        )
        if not confirm:
            return

        self.control_panel.set_convert_enabled(False)
        self.control_panel.progress.start_indeterminate("Converting DLC blocks to base...")
        self.footer.set_status("VANILLA-FYING...")

        # Build a temporary converter specifically for DLC substitution
        dlc_converter = BlueprintConverter(
            verbose=False,
            reverse=False,
            enabled_categories=["dlc_substitution"],
            include_profiles=True,
            profile_dir=Path("profiles"),
        )

        def task():
            try:
                dest, scanned, converted = dlc_converter.create_converted_blueprint(bp.path)
                self.after(0, lambda: self._on_vanillafy_complete(dest, scanned, converted))
            except Exception as exc:
                error_message = str(exc)
                self.after(0, lambda msg=error_message: self._on_conversion_error(msg))

        threading.Thread(target=task, daemon=True).start()

    def _on_vanillafy_complete(self, dest_path: Path, scanned: int, converted: int):
        self.control_panel.progress.stop()
        self._converted_count += converted
        self._undo_stack.append(dest_path)
        self.footer.set_scanned(scanned)
        self.footer.set_converted(self._converted_count)
        self.footer.set_status("DLC CONVERT COMPLETE")
        self._update_convert_state()

        self.preview_panel.load_xml(dest_path / "bp.sbc", f"VANILLA-FIED: {dest_path.name}")
        self.preview_panel.switch_to_xml()
        self.toasts.toast(
            f"Vanilla-fied {converted} DLC block(s) successfully.",
            level="success",
        )
        self.load_blueprints_async()

    def scale_grid_choice(self):
        if not self.selected_blueprint:
            return
        bp = self.selected_blueprint
        
        current_grid = bp.grid_size if bp.grid_size in ("Large", "Small") else "Large"
        suggested_grid = "Small" if current_grid == "Large" else "Large"
        
        confirm = messagebox.askyesno(
            "Rescale Grid Size",
            f"Would you like to auto-scale grid size for '{bp.display_name}' from {current_grid} Grid to {suggested_grid} Grid?\n\n"
            f"This transfers all block subtypes and dimensions to {suggested_grid} equivalents and sets the grid property.",
            icon="question",
        )
        if not confirm:
            return

        self.control_panel.set_convert_enabled(False)
        self.control_panel.progress.start_indeterminate(f"Rescaling grid to {suggested_grid}...")
        self.footer.set_status("RESCALING...")

        def task():
            try:
                dest, scanned, converted = self.converter.scale_grid_size(bp.path, suggested_grid)
                self.after(0, lambda: self._on_scale_complete(dest, scanned, converted, suggested_grid))
            except Exception as exc:
                error_message = str(exc)
                self.after(0, lambda msg=error_message: self._on_conversion_error(msg))

        threading.Thread(target=task, daemon=True).start()

    def _on_scale_complete(self, dest_path: Path, scanned: int, converted: int, target_grid: str):
        self.control_panel.progress.stop()
        self._converted_count += converted
        self._undo_stack.append(dest_path)
        self.footer.set_scanned(scanned)
        self.footer.set_converted(self._converted_count)
        self.footer.set_status(f"SCALED TO {target_grid.upper()}")
        self._update_convert_state()

        self.preview_panel.load_xml(dest_path / "bp.sbc", f"SCALED: {dest_path.name}")
        self.preview_panel.switch_to_xml()
        self.toasts.toast(
            f"Successfully scaled entire blueprint grid size to {target_grid} with {converted} blocks updated.",
            level="success",
        )
        self.load_blueprints_async()

    def survival_sanity_blueprint(self):
        if not self.selected_blueprint:
            return
        bp = self.selected_blueprint
        confirm = messagebox.askyesno(
            "Survival Sanity (Strip Prototech)",
            f"Replace all uncraftable Prototech blocks in '{bp.display_name}' with standard survival-craftable counterparts?\n\n"
            f"This ensures the blueprint can be projected and built in standard survival games.",
            icon="question",
        )
        if not confirm:
            return

        self.control_panel.set_convert_enabled(False)
        self.control_panel.progress.start_indeterminate("Stripping Prototech blocks for survival...")
        self.footer.set_status("SURVIVAL SANITY...")

        def task():
            try:
                dest, scanned, converted = self.converter.survival_sanity_prototech(bp.path)
                self.after(0, lambda: self._on_survival_sanity_complete(dest, scanned, converted))
            except Exception as exc:
                error_message = str(exc)
                self.after(0, lambda msg=error_message: self._on_conversion_error(msg))

        threading.Thread(target=task, daemon=True).start()

    def _on_survival_sanity_complete(self, dest_path: Path, scanned: int, converted: int):
        self.control_panel.progress.stop()
        self._converted_count += converted
        self._undo_stack.append(dest_path)
        self.footer.set_scanned(scanned)
        self.footer.set_converted(self._converted_count)
        self.footer.set_status("SURVIVAL READY")
        self._update_convert_state()

        self.preview_panel.load_xml(dest_path / "bp.sbc", f"SURVIVAL-READY: {dest_path.name}")
        self.preview_panel.switch_to_xml()
        self.toasts.toast(
            f"Successfully converted {converted} Prototech block(s) to survival-craftable equivalents.",
            level="success",
        )
        self.load_blueprints_async()

    def upgrade_prototech_blueprint(self):
        if not self.selected_blueprint:
            return
        bp = self.selected_blueprint
        confirm = messagebox.askyesno(
            "Upgrade to Prototech (Factorum)",
            f"Upgrade standard vanilla blocks in '{bp.display_name}' to endgame Factorum Prototech equivalents?\n\n"
            f"This equips maximum-tier reactors, thrusters, jump drives, and weapons.",
            icon="question",
        )
        if not confirm:
            return

        self.control_panel.set_convert_enabled(False)
        self.control_panel.progress.start_indeterminate("Upgrading to Prototech tier...")
        self.footer.set_status("PROTOTECH UPGRADE...")

        def task():
            try:
                dest, scanned, converted = self.converter.upgrade_to_prototech(bp.path)
                self.after(0, lambda: self._on_prototech_complete(dest, scanned, converted))
            except Exception as exc:
                error_message = str(exc)
                self.after(0, lambda msg=error_message: self._on_conversion_error(msg))

        threading.Thread(target=task, daemon=True).start()

    def _on_prototech_complete(self, dest_path: Path, scanned: int, converted: int):
        self.control_panel.progress.stop()
        self._converted_count += converted
        self._undo_stack.append(dest_path)
        self.footer.set_scanned(scanned)
        self.footer.set_converted(self._converted_count)
        self.footer.set_status("PROTOTECH COMPLETE")
        self._update_convert_state()

        self.preview_panel.load_xml(dest_path / "bp.sbc", f"PROTOTECH: {dest_path.name}")
        self.preview_panel.switch_to_xml()
        self.toasts.toast(
            f"Successfully upgraded {converted} block(s) to Prototech tier.",
            level="success",
        )
        self.load_blueprints_async()

    def selective_convert_blueprint(self, custom_mapping: Dict[str, str], selected_subtypes: Set[str]):
        if not self.selected_blueprint:
            self.toasts.toast("Select a blueprint first.", level="warning")
            return

        bp = self.selected_blueprint
        self.control_panel.set_convert_enabled(False)
        self.control_panel.progress.start_indeterminate(f"Converting {len(selected_subtypes)} selective block type(s)...")
        self.footer.set_status("SELECTIVE CONVERTING...")

        def task():
            try:
                dest, scanned, converted = self.converter.create_selective_converted_blueprint(
                    bp.path,
                    custom_mapping=custom_mapping,
                    selected_subtypes=selected_subtypes,
                )
                self.after(0, lambda: self._on_selective_convert_complete(dest, scanned, converted))
            except Exception as exc:
                error_message = str(exc)
                self.after(0, lambda msg=error_message: self._on_conversion_error(msg))

        threading.Thread(target=task, daemon=True).start()

    def _on_selective_convert_complete(self, dest_path: Path, scanned: int, converted: int):
        self.control_panel.progress.stop()
        self._converted_count += converted
        self._undo_stack.append(dest_path)
        self.footer.set_scanned(scanned)
        self.footer.set_converted(self._converted_count)
        self.footer.set_status("SELECTIVE CONVERT COMPLETE")
        self._update_convert_state()

        self.preview_panel.load_xml(dest_path / "bp.sbc", f"CUSTOM: {dest_path.name}")
        self.preview_panel.switch_to_xml()
        self.toasts.toast(
            f"Successfully exchanged {converted} selected block(s) into Custom blueprint.",
            level="success",
        )
        self.load_blueprints_async()

    def migrate_se2_blueprint(self):
        if not self.selected_blueprint:
            self.toasts.toast("Select a blueprint first.", level="warning")
            return

        bp = self.selected_blueprint
        confirm = messagebox.askyesno(
            "Export to Space Engineers 2 (VRage3)",
            f"Export '{bp.display_name}' to the new VRage3 (SE2) JSON blueprint structure?\n\n"
            f"This creates a forward-compatible SE2 blueprint with translated block subtypes and coordinates.",
            icon="question",
        )
        if not confirm:
            return

        self.control_panel.set_convert_enabled(False)
        self.control_panel.progress.start_indeterminate("Exporting to VRage3 (SE2) format...")
        self.footer.set_status("SE2 EXPORT...")

        def task():
            try:
                from engine_compat import SE2MigrationBridge
                dest, scanned, converted = SE2MigrationBridge.migrate_se1_to_se2(bp.path)
                self.after(0, lambda: self._on_se2_migration_complete(dest, scanned, converted))
            except Exception as exc:
                error_message = str(exc)
                self.after(0, lambda msg=error_message: self._on_conversion_error(msg))

        threading.Thread(target=task, daemon=True).start()

    def _on_se2_migration_complete(self, dest_path: Path, scanned: int, converted: int):
        self.control_panel.progress.stop()
        self.footer.set_scanned(scanned)
        self.footer.set_status("SE2 EXPORT COMPLETE")
        self._update_convert_state()

        json_file = dest_path / "blueprint.json"
        if json_file.exists():
            self.preview_panel.load_xml(json_file, f"VRAGE3 (SE2): {dest_path.name}")
            self.preview_panel.switch_to_xml()

        self.toasts.toast(
            f"Exported {scanned} blocks to Space Engineers 2 format: {dest_path.name}",
            level="success",
        )
        self.load_blueprints_async()

    def create_desktop_shortcut(self):
        try:
            import subprocess
            ps_script = Path(get_resource_path("create_desktop_shortcut.ps1"))
            if ps_script.exists():
                subprocess.run(
                    ["powershell", "-ExecutionPolicy", "Bypass", "-File", str(ps_script)],
                    check=True,
                    capture_output=True,
                )
                self.toasts.toast("Desktop shortcut created successfully!", level="success")
            else:
                self.toasts.toast("Shortcut script not found.", level="error")
        except Exception as exc:
            self.toasts.toast(f"Could not create desktop shortcut: {exc}", level="error")

    def import_workshop_blueprint(self):
        dialog = ctk.CTkInputDialog(
            text="Enter Steam Workshop URL/ID or Mod.io URL:",
            title="Import Blueprint from Workshop / Mod.io",
        )
        url_or_id = dialog.get_input()
        if not url_or_id:
            return

        from workshop_sync import SteamWorkshopFetcher, ModioFetcher
        wid = SteamWorkshopFetcher.parse_workshop_id(url_or_id)
        if wid:
            self.footer.set_status("Looking up workshop cache…")

            def task():
                try:
                    cached_items = SteamWorkshopFetcher.list_cached_workshop_items()
                    matched = [item for item in cached_items if item.workshop_id == wid]
                    if not matched:
                        self.after(
                            0,
                            lambda: self.toasts.toast(
                                f"Workshop ID {wid} parsed. (Ensure item is downloaded in Steam workshop cache)",
                                level="info",
                                duration=5000,
                            ),
                        )
                        return
                    imported_path = SteamWorkshopFetcher.import_to_local_blueprints(matched[0])
                    self.after(
                        0,
                        lambda path=imported_path: (
                            self.toasts.toast(f"Imported Workshop blueprint: {path.name}", level="success"),
                            self.load_blueprints_async(),
                        ),
                    )
                except Exception as exc:
                    self.after(0, lambda msg=str(exc): self.toasts.toast(f"Import failed: {msg}", level="error"))

            threading.Thread(target=task, daemon=True).start()
            return

        mod_slug = ModioFetcher.parse_modio_url(url_or_id)
        if mod_slug:
            self.toasts.toast(f"Mod.io item '{mod_slug}' detected.", level="info")
            zip_path = filedialog.askopenfilename(
                title=f"Select the downloaded Mod.io zip for '{mod_slug}'",
                filetypes=[("Zip archives", "*.zip"), ("All files", "*.*")],
            )
            if not zip_path:
                return
            appdata = os.environ.get("APPDATA")
            local_bp = (
                Path(appdata) / "SpaceEngineers" / "Blueprints" / "local"
                if appdata
                else Path.home() / "AppData" / "Roaming" / "SpaceEngineers" / "Blueprints" / "local"
            )
            dest = local_bp / f"Modio_{mod_slug}"
            try:
                ModioFetcher.extract_zip_blueprint(Path(zip_path), dest)
                self.toasts.toast(f"Imported Mod.io blueprint: {dest.name}", level="success")
                self.load_blueprints_async()
            except Exception as exc:
                self.toasts.toast(f"Mod.io import failed: {exc}", level="error")
            return

        self.toasts.toast("Could not parse Workshop ID or Mod.io URL.", level="warning")

    def batch_convert(self):
        selected_bps = self.blueprint_panel.get_selected_blueprints()
        if not selected_bps:
            self.toasts.toast("Select one or more blueprints first.", level="warning")
            return

        confirm = messagebox.askyesno(
            "Batch Conversion",
            f"Convert {len(selected_bps)} blueprint(s) with categories "
            f"{', '.join(self.enabled_categories)}?",
            icon="warning",
        )
        if not confirm:
            return

        self.control_panel.set_convert_enabled(False)
        total = len(selected_bps)
        self.control_panel.progress.start_indeterminate(f"Batch converting {total} blueprints...")
        self.footer.set_status("BATCH CONVERTING...")

        def batch_task():
            total_scanned = 0
            total_converted = 0
            errors = []
            created: List[Path] = []

            for index, bp in enumerate(selected_bps):
                self.after(
                    0,
                    lambda idx=index: self.control_panel.progress.set_progress(
                        (idx + 1) / total,
                        f"Converting {idx + 1}/{total}",
                    ),
                )
                try:
                    converter = BlueprintConverter(
                        verbose=False,
                        reverse=(self.conversion_mode == "heavy_to_light"),
                        enabled_categories=self.enabled_categories,
                        include_profiles=True,
                        profile_dir=Path("profiles"),
                    )
                    dest, scanned, converted = converter.create_converted_blueprint(bp.path)
                    created.append(dest)
                    total_scanned += scanned
                    total_converted += converted
                except Exception as exc:
                    errors.append(f"{bp.display_name}: {exc}")

            self.after(
                0,
                lambda: self._on_batch_complete(total, total_scanned, total_converted, errors, created),
            )

        threading.Thread(target=batch_task, daemon=True).start()

    def _on_batch_complete(self, count, scanned, converted, errors, created_paths: List[Path]):
        self.control_panel.progress.stop()
        self._converted_count += converted
        self._undo_stack.extend(created_paths)
        self.footer.set_scanned(scanned)
        self.footer.set_converted(self._converted_count)
        self.footer.set_status("BATCH COMPLETE")
        self._update_convert_state()

        message = f"Batch converted {count} blueprint(s): {converted} block(s) changed."
        if errors:
            message += f" ({len(errors)} error(s))"
            self.toasts.toast(message, level="warning", duration=6000)
        else:
            self.toasts.toast(message, level="success")
        self.load_blueprints_async()

    def undo_last_conversion(self):
        if not self._undo_stack:
            self.toasts.toast("Nothing to undo.", level="info")
            return
        last = self._undo_stack.pop()
        try:
            if last.exists() and last.is_dir():
                import shutil

                shutil.rmtree(last)
                self.toasts.toast(f"Removed {last.name}", level="success")
                self.footer.set_status("UNDO COMPLETE")
                self.load_blueprints_async()
            else:
                self.toasts.toast("Last converted folder no longer exists.", level="warning")
        except Exception as exc:
            self.toasts.toast(f"Undo failed: {exc}", level="error")

    # ------------------------------------------------------------------
    # Preview and analytics
    # ------------------------------------------------------------------

    def run_dry_run_preview(self):
        if not self.selected_blueprint:
            self.toasts.toast("Select a blueprint first.", level="warning")
            return
        bp_file = self.selected_blueprint.path / "bp.sbc"

        try:
            replacer = ArmorBlockReplacer(
                verbose=False,
                reverse=(self.conversion_mode == "heavy_to_light"),
                enabled_categories=self.enabled_categories,
                include_profiles=True,
                profile_dir=Path("profiles"),
            )
            replacer.process_blueprint(str(bp_file), create_backup=False, dry_run=True)

            before_counts: Dict[str, int] = {}
            after_counts: Dict[str, int] = {}
            for source, target in replacer.change_log:
                before_counts[source] = before_counts.get(source, 0) + 1
                after_counts[target] = after_counts.get(target, 0) + 1

            report = replacer.get_dry_run_report()
            self.preview_panel.show_preview_diff(before_counts, after_counts, report)

            self._latest_analytics = self.analytics_engine.analyze_blueprint(bp_file)
            self._latest_comparison = self.analytics_engine.compare_conversion_cost(
                bp_file,
                replacer.mapping,
                self.conversion_mode,
            )
            self.preview_panel.update_analytics(self._latest_analytics, self._latest_comparison)
        except Exception as exc:
            self.toasts.toast(f"Dry-run failed: {exc}", level="error", duration=5000)

    def refresh_analytics_async(self):
        if not self.selected_blueprint:
            return
        bp_file = self.selected_blueprint.path / "bp.sbc"

        def task():
            try:
                replacer = ArmorBlockReplacer(
                    verbose=False,
                    reverse=(self.conversion_mode == "heavy_to_light"),
                    enabled_categories=self.enabled_categories,
                    include_profiles=True,
                    profile_dir=Path("profiles"),
                )
                analytics = self.analytics_engine.analyze_blueprint(bp_file)
                comparison = self.analytics_engine.compare_conversion_cost(
                    bp_file,
                    replacer.mapping,
                    self.conversion_mode,
                )
                self._safe_after(0, lambda: self._on_analytics_ready(analytics, comparison))
            except Exception as exc:
                error_message = str(exc)
                self._safe_after(0, lambda msg=error_message: self._show_error(f"Analytics failed: {msg}"))

        threading.Thread(target=task, daemon=True).start()

    def _on_analytics_ready(self, analytics, comparison):
        self._latest_analytics = analytics
        self._latest_comparison = comparison
        self.preview_panel.update_analytics(analytics, comparison)

        # Compute SE2 Readiness metrics
        dlc_keywords = ["scifi", "industrial", "wasteland", "warfare", "reskin", "decorative", "desert", "cab", "buggy", "sparks", "vending", "storeblock"]
        dlc_count = 0
        script_count = 0
        subgrid_count = 0
        
        for subtype, qty in analytics.block_counts.items():
            subtype_lower = subtype.lower()
            if any(kw in subtype_lower for kw in dlc_keywords):
                dlc_count += qty
            if "programmable" in subtype_lower:
                script_count += qty
            if any(kw in subtype_lower for kw in ["rotor", "stator", "hinge", "piston"]):
                subgrid_count += qty
                
        self.preview_panel.update_se2_transition(self.selected_blueprint, dlc_count, script_count, subgrid_count)

        # PB Script Doctor & Subgrid Engine updates
        try:
            if self.selected_blueprint:
                bp_file = self.selected_blueprint.path / "bp.sbc"
                from pb_doctor import PBScriptExtractor, PBScriptValidator
                scripts = PBScriptExtractor.extract_from_file(bp_file)
                reports = [PBScriptValidator.validate_script(s.custom_name, s.program_code) for s in scripts]
                self.preview_panel.update_pb_doctor(scripts, reports)

                from subgrid_engine import SubgridHierarchyParser, GridMatrixVisualizer
                structure = SubgridHierarchyParser.parse_file(bp_file)
                matrix = GridMatrixVisualizer.analyze_grid_matrix(bp_file)
                voxels = GridMatrixVisualizer.extract_all_voxels(bp_file)
                self.preview_panel.update_subgrids(structure, matrix, voxels=voxels)
                self.preview_panel.update_survival_bom(analytics, structure)
        except Exception as exc:
            self.toasts.toast(f"PB Doctor / subgrid update failed: {exc}", level="warning", duration=4000)

    def split_active_blueprint_subgrids(self):
        """Splits the active multi-grid blueprint into individual printable sub-blueprints."""
        if not self.selected_blueprint:
            self.toasts.toast("Select a multi-grid blueprint first.", level="warning")
            return

        from subgrid_engine import ProjectorSplitter
        bp_path = self.selected_blueprint.path
        result = ProjectorSplitter.split_blueprint(bp_path)

        if not result.success:
            self.toasts.toast(f"Split Error: {result.error_message}", level="error")
            return

        if result.total_subgrids <= 1:
            self.toasts.toast("Single grid detected. No subgrid splitting required.", level="info")
            return

        self.toasts.toast(
            f"Successfully generated {result.total_subgrids} printable sub-blueprints!",
            level="success",
            duration=5000,
        )

        # Update preview textbox with assembly guide
        if hasattr(self.preview_panel, "survival_splitter_textbox"):
            self.preview_panel._set_textbox_content(
                self.preview_panel.survival_splitter_textbox,
                result.assembly_guide_text,
            )

        # Refresh blueprint library to discover new sub-blueprints
        self.load_blueprints_async()

    def apply_active_skin_palette(self, skin_id: str, primary_hex: str, secondary_hex: str, armor_only: bool):
        """Batch applies armor texture skin and HSV color palette across the vessel."""
        if not self.selected_blueprint:
            self.toasts.toast("Select a blueprint first.", level="warning")
            return

        from mappings.skin_palette_engine import SkinPaletteEngine
        bp_path = self.selected_blueprint.path

        try:
            reskinned, recolored = SkinPaletteEngine.apply_skin_and_palette(
                source_bp_path=bp_path,
                skin_id=skin_id if skin_id != "None" else None,
                primary_hex=primary_hex,
                armor_only=armor_only,
            )
            self.toasts.toast(
                f"Reskinned {reskinned:,} blocks, Recolored {recolored:,} blocks!",
                level="success",
            )
            self.load_blueprints_async()
            self.refresh_analytics_async()
        except Exception as exc:
            self.toasts.toast(f"Reskin error: {exc}", level="error")

    def harden_active_armor(self, radius: int):
        """Reinforces armor surrounding vital reactor/jump/tank cores."""
        if not self.selected_blueprint:
            self.toasts.toast("Select a blueprint first.", level="warning")
            return

        from mappings.armor_hardening import ArmorHardeningEngine
        bp_path = self.selected_blueprint.path

        try:
            res = ArmorHardeningEngine.harden_vital_cores(bp_path, reinforce_radius=radius)
            self.toasts.toast(
                f"Hardened {res.armor_blocks_hardened:,} armor blocks around {res.critical_cores_found} critical cores!",
                level="success",
            )
            self.load_blueprints_async()
            self.refresh_analytics_async()
        except Exception as exc:
            self.toasts.toast(f"Hardening error: {exc}", level="error")

    def lightweight_active_armor(self, preserve_radius: int):
        """Lightweights peripheral non-vital armor to maximize jump range and acceleration."""
        if not self.selected_blueprint:
            self.toasts.toast("Select a blueprint first.", level="warning")
            return

        from mappings.armor_hardening import ArmorHardeningEngine
        bp_path = self.selected_blueprint.path

        try:
            res = ArmorHardeningEngine.lightweight_outer_hull(bp_path, preserve_radius=preserve_radius)
            self.toasts.toast(
                f"Lightened {res.armor_blocks_lightened:,} non-vital armor blocks!",
                level="success",
            )
            self.load_blueprints_async()
            self.refresh_analytics_async()
        except Exception as exc:
            self.toasts.toast(f"Lightweight error: {exc}", level="error")

    def export_comparison_csv(self):
        if not self._latest_comparison:
            self.toasts.toast("Run preview first to generate comparison data.", level="warning")
            return
        path = filedialog.asksaveasfilename(
            title="Export Comparison CSV",
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv")],
        )
        if not path:
            return
        self.analytics_engine.export_comparison_csv(self._latest_comparison, Path(path))
        self.toasts.toast(f"CSV report exported: {Path(path).name}", level="success")

    def export_comparison_txt(self):
        if not self._latest_comparison:
            self.toasts.toast("Run preview first to generate comparison data.", level="warning")
            return
        path = filedialog.asksaveasfilename(
            title="Export Comparison Text",
            defaultextension=".txt",
            filetypes=[("Text", "*.txt")],
        )
        if not path:
            return
        self.analytics_engine.export_comparison_text(self._latest_comparison, Path(path))
        self.toasts.toast(f"Text report exported: {Path(path).name}", level="success")

    def apply_health_fix(self, fix_id: str):
        if not self.selected_blueprint:
            return
        bp_file = self.selected_blueprint.path / "bp.sbc"
        confirm = messagebox.askyesno(
            "Apply Suggested Fix",
            f"Apply fix '{fix_id}' to blueprint '{self.selected_blueprint.display_name}'?",
            icon="question",
        )
        if not confirm:
            return
        success = self.analytics_engine.apply_fix(bp_file, fix_id)
        if success:
            self.toasts.toast(f"Applied fix: {fix_id}", level="success")
            self.refresh_analytics_async()
            self.preview_panel.load_xml(bp_file, f"SOURCE: {self.selected_blueprint.name}")
        else:
            self.toasts.toast(f"Fix '{fix_id}' could not be applied.", level="warning")

    # ------------------------------------------------------------------
    # Changelog / utilities
    # ------------------------------------------------------------------

    def show_changelog_window(self):
        win = ctk.CTkToplevel(self)
        win.title(f"Changelog - SE Block Exchanger v{__version__}")
        win.geometry("980x700")
        win.configure(fg_color=TacticalTheme.BG_DARK)

        textbox = ctk.CTkTextbox(
            win,
            font=("Consolas", 10),
            text_color=TacticalTheme.TEXT_CYAN,
            fg_color="#0c1220",
            border_color=TacticalTheme.BG_MEDIUM,
            border_width=1,
            corner_radius=6,
        )
        textbox.pack(fill="both", expand=True, padx=10, pady=10)

        content = self._load_changelog_markdown()
        textbox.insert("end", content)
        textbox.configure(state="disabled")

    def _load_changelog_markdown(self) -> str:
        if self._latest_update and self._latest_update.changelog:
            heading = (
                f"Latest release: {self._latest_update.latest_version}\n"
                f"Published: {self._latest_update.published_at}\n"
                f"URL: {self._latest_update.release_url}\n\n"
            )
            return heading + self._latest_update.changelog
        try:
            with open("RELEASE_NOTES.md", "r", encoding="utf-8") as handle:
                return handle.read()
        except Exception as exc:
            return f"Could not load release notes: {exc}"

    def _show_error(self, message: str):
        self.footer.set_status("ERROR", TacticalTheme.RED_PRIMARY)
        self.toasts.toast(message, level="error", duration=5000)


def main():
    try:
        app = TacticalCommandCenter()
        app.mainloop()
    except Exception as exc:
        messagebox.showerror("Fatal Error", f"Application failed to start:\n{exc}")
        sys.exit(1)

if __name__ == "__main__":
    main()
