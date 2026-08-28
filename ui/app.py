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
from typing import Dict, List, Optional

import customtkinter as ctk
from tkinter import filedialog, messagebox

from app_settings import AppSettings, SettingsStore
from blueprint_analytics import BlueprintAnalyticsEngine, compute_se2_readiness
from blueprint_converter import BlueprintConverter
from blueprint_scanner import BlueprintInfo, BlueprintScanner
from mapping_profiles import ProfileManager
from mappings import build_registry
import safe_xml
from se_armor_replacer import ArmorBlockReplacer
from subgrid_engine import GridMatrixVisualizer, SubgridHierarchyParser
from ui.blueprint_panel import BlueprintPanel
from ui.control_panel import ControlPanel
from ui.dragdrop_windows import WindowsFileDropTarget
from ui.footer import Footer
from ui.header import Header
from ui.labels import category_label, convertible_total
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
        TacticalTheme.resolve_fonts()

        self.title("SE Block Exchanger")
        self.geometry("1360x900")
        self.configure(fg_color=TacticalTheme.BG_DARK)
        self.minsize(1080, 700)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._set_icon()

        self.profile_manager = ProfileManager(Path("profiles"))
        self.profile_manager.load_all()
        self.registry = build_registry(include_builtin=True)
        self.profile_manager.register_profile_categories(self.registry)

        self.enabled_categories = self._resolve_enabled_categories(self.settings.enabled_categories)
        self.conversion_mode = "light_to_heavy"

        self.scanner = BlueprintScanner(
            registry=self.registry,
            enabled_categories=self.enabled_categories,
            reverse=False,
        )
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
        self._rescan_after_id = None
        self._preview_after_id = None
        self._inspect_generation = 0
        self._closing = False

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

    # ------------------------------------------------------------------
    # Bootstrapping
    # ------------------------------------------------------------------

    def _build_converter(self) -> BlueprintConverter:
        return BlueprintConverter(
            verbose=False,
            reverse=(self.conversion_mode == "heavy_to_light"),
            enabled_categories=self.enabled_categories,
            include_profiles=False,
            registry=self.registry,
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
            pass

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
        content.columnconfigure(0, weight=0, minsize=340)
        content.columnconfigure(1, weight=1, minsize=420)
        content.columnconfigure(2, weight=0, minsize=360)
        content.rowconfigure(0, weight=1)

        self.blueprint_panel = BlueprintPanel(
            content,
            on_select=self.on_blueprint_select,
            on_recent_select=self._on_recent_blueprint_pick,
            on_browse=self.browse_blueprint_dir,
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
        help_menu = tk.Menu(menubar, tearoff=0)
        self._auto_update_var = tk.BooleanVar(value=self.settings.auto_check_updates)
        help_menu.add_checkbutton(
            label="Auto-check updates on startup",
            variable=self._auto_update_var,
            command=self._toggle_auto_update_checks,
        )
        help_menu.add_separator()
        help_menu.add_command(label="View Changelog", command=self.show_changelog_window)
        help_menu.add_command(label="Discord", command=lambda: webbrowser.open("https://discord.com/"))
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
        self.footer.set_status(f"Auto-check updates {state}")

    def _bind_shortcuts(self):
        self.bind_all("<Control-o>", lambda event: self.browse_blueprint_dir())
        self.bind_all("<Control-r>", lambda event: self.convert_blueprint())
        self.bind_all("<Control-z>", lambda event: self.undo_last_conversion())

    def _setup_drag_drop(self):
        self._drop_target = WindowsFileDropTarget(self, self._handle_dropped_paths)
        try:
            enabled = self._drop_target.enable()
            if enabled:
                self.footer.set_status("Drop a blueprint folder to open it")
        except Exception:
            self.footer.set_status("Drag and drop unavailable")

    # ------------------------------------------------------------------
    # Settings and appearance
    # ------------------------------------------------------------------

    def set_appearance_mode(self, mode: str):
        normalized = TacticalTheme.normalize_appearance_mode(mode)
        ctk.set_appearance_mode(normalized)
        self.settings.appearance_mode = normalized
        self.settings_store.save(self.settings)
        self.footer.set_status(f"Appearance: {normalized}")

    def _select_recent_dir(self, directory: str):
        self.custom_blueprint_dir = directory
        self.footer.set_status(f"Folder: {directory}")
        self.load_blueprints_async()

    def _on_recent_blueprint_pick(self, name: str):
        self.footer.set_status(f"Recent: {name}")

    # ------------------------------------------------------------------
    # Registry / profiles
    # ------------------------------------------------------------------

    def _rebuild_registry(self):
        self.profile_manager.load_all()
        self.registry = build_registry(include_builtin=True)
        self.profile_manager.register_profile_categories(self.registry)
        self.enabled_categories = self._resolve_enabled_categories(self.enabled_categories)
        self.scanner = BlueprintScanner(
            registry=self.registry,
            enabled_categories=self.enabled_categories,
            reverse=(self.conversion_mode == "heavy_to_light"),
        )
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
                self._ui(lambda: self._on_update_checked(info))
            except Exception:
                pass

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
        self.footer.set_status(f"Opened: {raw_path.name}")
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
            self.footer.set_status(
                "Categories: " + ", ".join(category_label(name) for name in categories)
            )
            if self.selected_blueprint:
                self._inspect_blueprint_async()
            self._schedule_rescan()
        except Exception as exc:
            self.scanner.set_enabled_categories(previous)
            self.enabled_categories = previous
            self.control_panel.set_category_options(self.registry.list_categories(), self.enabled_categories)
            self.toasts.toast(f"Invalid category combination: {exc}", level="error", duration=6000)

    # ------------------------------------------------------------------
    # Blueprint loading
    # ------------------------------------------------------------------

    def load_blueprints_async(self):
        self.footer.set_status("Scanning blueprints…")

        def load_task():
            try:
                scan_dir = self.custom_blueprint_dir or None
                self.blueprints = self.scanner.scan_blueprints(scan_dir)
                self._ui(self._on_blueprints_loaded)
            except FileNotFoundError:
                self._ui(self._on_scan_not_found)
            except Exception as exc:
                error_message = str(exc)
                self._ui(lambda msg=error_message: self._show_error(f"Scan failed: {msg}"))

        threading.Thread(target=load_task, daemon=True).start()

    def _on_blueprints_loaded(self):
        count = len(self.blueprints)
        self.header.set_blueprint_count(count)
        self.footer.set_status(f"{count} blueprint{'s' if count != 1 else ''} loaded")
        self.footer.set_scanned(count)
        self.blueprint_panel.set_blueprints(self.blueprints)
        self.blueprint_panel.set_recent_blueprints(self.settings.recent_blueprints)

        target = self._pending_select_name
        dropped = self._pending_select_name is not None
        self._pending_select_name = None
        if not target and self.selected_blueprint:
            target = self.selected_blueprint.display_name
        if not target and self.blueprints:
            target = self.blueprints[0].display_name
        if target:
            found = self.blueprint_panel.select_blueprint_by_name(target)
            if not found and dropped:
                self.toasts.toast("That blueprint was not in the scanned folder.", level="warning")
            if not found and self.blueprints:
                self.blueprint_panel.select_blueprint_by_name(self.blueprints[0].display_name)

    def _on_scan_not_found(self):
        self.blueprints = []
        self.header.set_blueprint_count(0)
        self.footer.set_status("Space Engineers folder not found")
        self.blueprint_panel.set_blueprints([])
        messagebox.showwarning(
            "Blueprint folder not found",
            "The Space Engineers Blueprints folder was not found.\n\n"
            "Use Open folder or drop a blueprint folder here.",
        )

    def browse_blueprint_dir(self):
        chosen = filedialog.askdirectory(title="Open Blueprints folder", mustexist=True)
        if chosen:
            self.custom_blueprint_dir = chosen
            self.settings_store.add_recent_dir(self.settings, chosen)
            self.header.set_recent_dirs(self.settings.recent_blueprint_dirs)
            self.footer.set_status(f"Folder: {chosen}")
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
        self._update_convert_state()
        self.footer.set_status(f"Selected: {bp.display_name}")
        self._inspect_blueprint_async()

    def _get_selected_blueprint_file(self) -> Optional[str]:
        if not self.selected_blueprint:
            return None
        return str(self.selected_blueprint.path / "bp.sbc")

    # ------------------------------------------------------------------
    # Conversion mode
    # ------------------------------------------------------------------

    def set_conversion_mode(self, mode: str):
        self.conversion_mode = mode
        self.scanner.set_reverse(mode == "heavy_to_light")
        self.converter = self._build_converter()
        if self.selected_blueprint:
            self.preview_panel.update_intel(self.selected_blueprint, mode)
            self._inspect_blueprint_async()
        self._update_convert_state()
        self.footer.set_status("Heavy → Light" if mode == "heavy_to_light" else "Light → Heavy")

    def _update_convert_state(self):
        if not self.selected_blueprint:
            self.control_panel.set_convert_ready(
                enabled=False,
                count=0,
                reverse=(self.conversion_mode == "heavy_to_light"),
                has_blueprint=False,
            )
            return
        count = convertible_total(self.selected_blueprint)
        self.control_panel.set_convert_ready(
            enabled=count > 0,
            count=count,
            reverse=(self.conversion_mode == "heavy_to_light"),
            has_blueprint=True,
        )

    def _schedule_rescan(self):
        if self._rescan_after_id is not None:
            self.after_cancel(self._rescan_after_id)
        self._rescan_after_id = self.after(800, self._run_scheduled_rescan)

    def _run_scheduled_rescan(self):
        self._rescan_after_id = None
        if self.selected_blueprint:
            self._pending_select_name = self.selected_blueprint.display_name
        self.load_blueprints_async()

    def _schedule_preview(self):
        self._inspect_blueprint_async()

    def _run_scheduled_preview(self):
        self._preview_after_id = None
        self._inspect_blueprint_async()

    def _inspect_blueprint_async(self):
        if not self.selected_blueprint or self._closing:
            return
        if self._preview_after_id is not None:
            self.after_cancel(self._preview_after_id)
        self._preview_after_id = self.after(90, self._run_inspect_now)

    def _run_inspect_now(self):
        self._preview_after_id = None
        if not self.selected_blueprint or self._closing:
            return
        self._inspect_generation += 1
        generation = self._inspect_generation
        bp = self.selected_blueprint
        bp_file = bp.path / "bp.sbc"
        mode = self.conversion_mode
        categories = list(self.enabled_categories)
        reverse = mode == "heavy_to_light"

        def task():
            try:
                replacer = ArmorBlockReplacer(
                    verbose=False,
                    reverse=reverse,
                    enabled_categories=categories,
                    registry=self.registry,
                    include_profiles=False,
                )
                replacer.process_blueprint(str(bp_file), create_backup=False, dry_run=True)
                before_counts: Dict[str, int] = {}
                after_counts: Dict[str, int] = {}
                for source, target in replacer.change_log:
                    before_counts[source] = before_counts.get(source, 0) + 1
                    after_counts[target] = after_counts.get(target, 0) + 1
                report = replacer.get_dry_run_report()
                analytics = self.analytics_engine.analyze_blueprint(bp_file)
                comparison = self.analytics_engine.compare_conversion_cost(
                    bp_file,
                    replacer.mapping,
                    mode,
                )
                tree = safe_xml.parse(bp_file)
                root = tree.getroot()
                structure = SubgridHierarchyParser.parse_element(root)
                voxels = GridMatrixVisualizer.extract_voxels_from_root(root)
                self._ui(
                    lambda: self._on_inspect_ready(
                        generation,
                        bp,
                        before_counts,
                        after_counts,
                        report,
                        analytics,
                        comparison,
                        structure,
                        voxels,
                    )
                )
            except Exception as exc:
                error_message = str(exc)
                self._ui(lambda msg=error_message: self._on_inspect_error(generation, msg))

        threading.Thread(target=task, daemon=True).start()

    def _on_inspect_ready(
        self,
        generation: int,
        bp: BlueprintInfo,
        before_counts,
        after_counts,
        report,
        analytics,
        comparison,
        structure,
        voxels,
    ):
        if self._closing or generation != self._inspect_generation:
            return
        if not self.selected_blueprint or self.selected_blueprint.path != bp.path:
            return
        self._latest_analytics = analytics
        self._latest_comparison = comparison
        self.preview_panel.show_preview_diff(before_counts, after_counts, report, switch_tab=False)
        self.preview_panel.update_analytics(analytics, comparison)
        self.preview_panel.update_se2_transition(bp, compute_se2_readiness(analytics.block_counts))
        try:
            self.preview_panel.update_subgrids(structure, voxels=voxels)
        except Exception as exc:
            self.toasts.toast(f"Map view failed: {exc}", level="warning")
        self.preview_panel.load_xml(bp.path / "bp.sbc", f"Source: {bp.name}")

    def _on_inspect_error(self, generation: int, message: str):
        if self._closing or generation != self._inspect_generation:
            return
        self._show_error(f"Preview failed: {message}")

    # ------------------------------------------------------------------
    # Conversion operations
    # ------------------------------------------------------------------

    def convert_blueprint(self):
        if not self.selected_blueprint:
            return
        bp = self.selected_blueprint
        count = convertible_total(bp)
        direction = "heavy armor" if self.conversion_mode != "heavy_to_light" else "light armor"
        category_text = ", ".join(category_label(name) for name in self.enabled_categories)

        confirm = messagebox.askyesno(
            "Create a converted copy?",
            f"Create a new copy of '{bp.display_name}' with {count} block(s) converted to {direction}?\n\n"
            f"Included: {category_text}\n\n"
            "The original blueprint is not changed. Undo removes the new copy.",
        )
        if not confirm:
            return

        self.control_panel.set_convert_enabled(False)
        self.control_panel.progress.start_indeterminate("Converting blueprint...")
        self.footer.set_status("Converting…")

        def task():
            try:
                dest, scanned, converted = self.converter.create_converted_blueprint(bp.path)
                self._ui(lambda: self._on_conversion_complete(dest, scanned, converted))
            except Exception as exc:
                error_message = str(exc)
                self._ui(lambda msg=error_message: self._on_conversion_error(msg))

        threading.Thread(target=task, daemon=True).start()

    def _on_conversion_complete(self, dest_path: Path, scanned: int, converted: int):
        self.control_panel.progress.stop()
        self._converted_count += converted
        self._undo_stack.append(dest_path)
        self.footer.set_scanned(scanned)
        self.footer.set_converted(self._converted_count)
        self.footer.set_status("Copy created")
        self._update_convert_state()

        self.preview_panel.load_xml(dest_path / "bp.sbc", f"Converted: {dest_path.name}")
        self.toasts.toast(
            f"Created {dest_path.name} with {converted} block(s) converted.",
            level="success",
        )
        self._pending_select_name = dest_path.name
        self.load_blueprints_async()

    def _on_conversion_error(self, error_msg: str):
        self.control_panel.progress.stop()
        self._update_convert_state()
        self.footer.set_status("Error", TacticalTheme.RED_PRIMARY)
        self.toasts.toast(f"Conversion failed: {error_msg}", level="error", duration=5000)

    def vanillafy_blueprint(self):
        if not self.selected_blueprint:
            return
        bp = self.selected_blueprint

        confirm = messagebox.askyesno(
            "Vanilla-fy Blueprint",
            f"Replace paid DLC blocks in '{bp.display_name}' with vanilla equivalents?\n\n"
            "This creates a new copy (original stays untouched).",
            icon="question",
        )
        if not confirm:
            return

        self.control_panel.set_convert_enabled(False)
        self.control_panel.progress.start_indeterminate("Converting DLC blocks to base...")
        self.footer.set_status("Replacing DLC blocks…")

        # Build a temporary converter specifically for DLC substitution
        dlc_converter = BlueprintConverter(
            verbose=False,
            reverse=False,
            enabled_categories=["dlc_substitution"],
            include_profiles=False,
            registry=self.registry,
        )

        def task():
            try:
                dest, scanned, converted = dlc_converter.create_converted_blueprint(bp.path)
                self._ui(lambda: self._on_vanillafy_complete(dest, scanned, converted))
            except Exception as exc:
                error_message = str(exc)
                self._ui(lambda msg=error_message: self._on_conversion_error(msg))

        threading.Thread(target=task, daemon=True).start()

    def _on_vanillafy_complete(self, dest_path: Path, scanned: int, converted: int):
        self.control_panel.progress.stop()
        self._converted_count += converted
        self._undo_stack.append(dest_path)
        self.footer.set_scanned(scanned)
        self.footer.set_converted(self._converted_count)
        self.footer.set_status("DLC replaced")
        self._update_convert_state()

        self.preview_panel.load_xml(dest_path / "bp.sbc", f"Vanilla copy: {dest_path.name}")
        self.toasts.toast(
            f"Created {dest_path.name} with {converted} DLC block(s) replaced.",
            level="success",
        )
        self._pending_select_name = dest_path.name
        self.load_blueprints_async()

    def scale_grid_choice(self):
        if not self.selected_blueprint:
            return
        bp = self.selected_blueprint
        
        current_grid = bp.grid_size if bp.grid_size in ("Large", "Small") else "Large"
        suggested_grid = "Small" if current_grid == "Large" else "Large"
        
        confirm = messagebox.askyesno(
            "Rescale Grid Size",
            f"Create a {suggested_grid.lower()}-grid copy of '{bp.display_name}'?\n\n"
            f"Block subtypes and coordinates are scaled from {current_grid} to {suggested_grid}. "
            "The original blueprint is not changed.",
            icon="question",
        )
        if not confirm:
            return

        self.control_panel.set_convert_enabled(False)
        self.control_panel.progress.start_indeterminate(f"Rescaling grid to {suggested_grid}...")
        self.footer.set_status(f"Scaling to {suggested_grid}…")

        def task():
            try:
                dest, scanned, converted = self.converter.scale_grid_size(bp.path, suggested_grid)
                self._ui(lambda: self._on_scale_complete(dest, scanned, converted, suggested_grid))
            except Exception as exc:
                error_message = str(exc)
                self._ui(lambda msg=error_message: self._on_conversion_error(msg))

        threading.Thread(target=task, daemon=True).start()

    def _on_scale_complete(self, dest_path: Path, scanned: int, converted: int, target_grid: str):
        self.control_panel.progress.stop()
        self._converted_count += converted
        self._undo_stack.append(dest_path)
        self.footer.set_scanned(scanned)
        self.footer.set_converted(self._converted_count)
        self.footer.set_status(f"Scaled to {target_grid}")
        self._update_convert_state()

        self.preview_panel.load_xml(dest_path / "bp.sbc", f"Scaled: {dest_path.name}")
        self.toasts.toast(
            f"Created a {target_grid}-grid copy with {converted} blocks updated.",
            level="success",
        )
        self._pending_select_name = dest_path.name
        self.load_blueprints_async()

    def batch_convert(self):
        selected_bps = self.blueprint_panel.get_selected_blueprints()
        if not selected_bps:
            self.toasts.toast("Select one or more blueprints first (Ctrl+click).", level="warning")
            return

        confirm = messagebox.askyesno(
            "Convert the selected ships?",
            f"Create converted copies of {len(selected_bps)} blueprint(s)?\n\n"
            f"Included: {', '.join(category_label(name) for name in self.enabled_categories)}\n\n"
            "Originals stay untouched.",
        )
        if not confirm:
            return

        self.control_panel.set_convert_enabled(False)
        total = len(selected_bps)
        self.control_panel.progress.start_indeterminate(f"Batch converting {total} blueprints...")
        self.footer.set_status("Converting selected ships…")

        def batch_task():
            total_scanned = 0
            total_converted = 0
            errors = []
            created: List[Path] = []

            for index, bp in enumerate(selected_bps):
                self._ui(
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
                        include_profiles=False,
                        registry=self.registry,
                    )
                    dest, scanned, converted = converter.create_converted_blueprint(bp.path)
                    created.append(dest)
                    total_scanned += scanned
                    total_converted += converted
                except Exception as exc:
                    errors.append(f"{bp.display_name}: {exc}")

            self._ui(
                lambda: self._on_batch_complete(total, total_scanned, total_converted, errors, created),
            )

        threading.Thread(target=batch_task, daemon=True).start()

    def _on_batch_complete(self, count, scanned, converted, errors, created_paths: List[Path]):
        self.control_panel.progress.stop()
        self._converted_count += converted
        self._undo_stack.extend(created_paths)
        self.footer.set_scanned(scanned)
        self.footer.set_converted(self._converted_count)
        self.footer.set_status("Batch complete")
        self._update_convert_state()

        message = f"Created copies for {count} blueprint(s): {converted} block(s) changed."
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
                self.footer.set_status("Copy removed")
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
        self._inspect_blueprint_async()

    def refresh_analytics_async(self):
        self._inspect_blueprint_async()

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
            "Apply suggested fix?",
            f"Apply this repair to '{self.selected_blueprint.display_name}'?\n\n"
            "This edits the selected blueprint (not a copy).",
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
            font=TacticalTheme.code_font(16),
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
        self.footer.set_status("Error", TacticalTheme.RED_PRIMARY)
        self.toasts.toast(message, level="error", duration=5000)

    def _ui(self, callback) -> None:
        if self._closing:
            return
        try:
            self.after(0, lambda: None if self._closing else callback())
        except Exception:
            pass

    def _on_close(self):
        if self._closing:
            return
        self._closing = True
        self._inspect_generation += 1
        for attr in ("_rescan_after_id", "_preview_after_id"):
            job = getattr(self, attr, None)
            if job is not None:
                try:
                    self.after_cancel(job)
                except Exception:
                    pass
                setattr(self, attr, None)
        try:
            self.control_panel.progress.stop()
        except Exception:
            pass
        try:
            self.toasts.dismiss_all()
        except Exception:
            pass
        try:
            self._drop_target.disable()
        except Exception:
            pass
        try:
            if self._profile_editor is not None and self._profile_editor.winfo_exists():
                self._profile_editor.grab_release()
                self._profile_editor.destroy()
        except Exception:
            pass
        try:
            self.quit()
        except Exception:
            pass
        try:
            self.destroy()
        except Exception:
            pass


def main():
    try:
        app = TacticalCommandCenter()
        app.mainloop()
    except Exception as exc:
        messagebox.showerror("Fatal Error", f"Application failed to start:\n{exc}")
        sys.exit(1)

if __name__ == "__main__":
    main()
