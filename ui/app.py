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
from queue import Empty, SimpleQueue
from typing import Dict, List, Optional, Set

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
from ui.labels import category_label, conversion_target_phrase, convertible_total
from ui.preview_panel import PreviewPanel
from ui.profile_editor import ProfileEditorDialog
from ui.selective_exchange_panel import SelectiveExchangePanel
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
        self._preview_convert_count = None
        self._closing = False
        self._ui_queue: SimpleQueue = SimpleQueue()

        self._build_ui()
        self.toasts = ToastManager(self)
        self._create_help_menu()
        self._bind_shortcuts()
        self._setup_drag_drop()
        self._center_window()
        self.after(16, self._pump_ui_queue)

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
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Open folder…", command=self.browse_blueprint_dir, accelerator="Ctrl+O")
        file_menu.add_command(
            label="Import Workshop / Mod.io blueprint…",
            command=self.import_workshop_blueprint,
        )
        file_menu.add_command(label="Refresh blueprints", command=self.load_blueprints_async, accelerator="F5")
        file_menu.add_separator()
        file_menu.add_command(label="Create desktop shortcut", command=self.create_desktop_shortcut)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self._on_close, accelerator="Alt+F4")
        menubar.add_cascade(label="File", menu=file_menu)

        tools_menu = tk.Menu(menubar, tearoff=0)
        tools_menu.add_command(label="Selective block exchange…", command=self.open_selective_exchange)
        tools_menu.add_command(label="PB Doctor…", command=self.open_pb_doctor)
        tools_menu.add_command(label="Split into projector subgrids", command=self.split_active_blueprint_subgrids)
        tools_menu.add_separator()
        tools_menu.add_command(
            label="Survival Sanity (Prototech → vanilla)",
            command=self.survival_sanity_blueprint,
        )
        tools_menu.add_command(label="Upgrade to Prototech", command=self.upgrade_prototech_blueprint)
        tools_menu.add_separator()
        tools_menu.add_command(label="Harden armor around cores…", command=self.harden_active_armor)
        tools_menu.add_command(label="Lightweight outer hull…", command=self.lightweight_active_armor)
        tools_menu.add_command(label="Export Space Engineers 2 JSON", command=self.export_se2_blueprint)
        menubar.add_cascade(label="Tools", menu=tools_menu)

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
        self.bind_all("<F5>", lambda event: self.load_blueprints_async())
        self.bind_all("<Alt-F4>", lambda event: self._on_close())

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
            self._invalidate_preview_counts()
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
        self._invalidate_preview_counts()
        if self.selected_blueprint:
            self.preview_panel.update_intel(self.selected_blueprint, mode)
            self._inspect_blueprint_async()
        else:
            self._update_convert_state()
        self.footer.set_status("Heavy → Light" if mode == "heavy_to_light" else "Light → Heavy")

    def _invalidate_preview_counts(self):
        """Drop in-flight inspect results and freeze Convert on stale scanner totals."""
        self._inspect_generation += 1
        self._preview_convert_count = None
        self.control_panel.mark_counts_stale()

    def _update_convert_state(self, count: Optional[int] = None):
        if not self.selected_blueprint:
            self._preview_convert_count = None
            self.control_panel.set_convert_ready(
                enabled=False,
                count=0,
                reverse=(self.conversion_mode == "heavy_to_light"),
                has_blueprint=False,
            )
            return
        if count is None:
            count = convertible_total(self.selected_blueprint)
        self._preview_convert_count = count
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
                # Profiles are already registered on self.registry. Reloading them
                # with include_profiles=True would disagree with _build_converter().
                replacer = ArmorBlockReplacer(
                    verbose=False,
                    reverse=reverse,
                    enabled_categories=categories,
                    registry=self.registry,
                    include_profiles=False,
                )
                tree = safe_xml.parse(bp_file)
                root = tree.getroot()
                replacer.blocks_scanned = 0
                replacer.replacements_made = 0
                replacer.change_log = []
                replacer.replace_blocks(tree, dry_run=True)
                before_counts: Dict[str, int] = {}
                after_counts: Dict[str, int] = {}
                for source, target in replacer.change_log:
                    before_counts[source] = before_counts.get(source, 0) + 1
                    after_counts[target] = after_counts.get(target, 0) + 1
                report = replacer.get_dry_run_report()
                analytics = self.analytics_engine.analyze_root(root, blueprint_name=bp.name)
                comparison = self.analytics_engine.compare_conversion_cost_from_result(
                    analytics,
                    replacer.mapping,
                    mode,
                )
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
        preview_count = sum(before_counts.values()) if before_counts else 0
        self._update_convert_state(preview_count)
        self.control_panel.set_pending_change_count(preview_count)

    def _on_inspect_error(self, generation: int, message: str):
        if self._closing or generation != self._inspect_generation:
            return
        self._show_error(f"Preview failed: {message}")
        self._update_convert_state()

    # ------------------------------------------------------------------
    # Conversion operations
    # ------------------------------------------------------------------

    def convert_blueprint(self):
        if not self.selected_blueprint:
            return
        if self.control_panel.counts_are_stale:
            return
        bp = self.selected_blueprint
        count = self._preview_convert_count
        if count is None:
            count = convertible_total(bp)
        target = conversion_target_phrase(
            self.conversion_mode == "heavy_to_light",
            self.enabled_categories,
        )
        category_text = ", ".join(category_label(name) for name in self.enabled_categories)

        confirm = messagebox.askyesno(
            "Create a converted copy?",
            f"Create a new copy of '{bp.display_name}' with {count} block(s) converted to {target}?\n\n"
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

        preview_file = dest_path / "bp.sbc"
        if not preview_file.exists():
            preview_file = dest_path / "blueprint.json"
        if preview_file.exists():
            self.preview_panel.load_xml(preview_file, f"Converted: {dest_path.name}")
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

    def import_workshop_blueprint(self):
        dialog = ctk.CTkInputDialog(
            text="Enter a Steam Workshop URL/ID or a Mod.io URL:",
            title="Import Workshop / Mod.io blueprint",
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
                        self._ui(
                            lambda: self.toasts.toast(
                                f"Workshop ID {wid} parsed. Download the item in Steam first, then retry.",
                                level="info",
                                duration=5000,
                            )
                        )
                        return
                    imported_path = SteamWorkshopFetcher.import_to_local_blueprints(matched[0])
                    self._ui(
                        lambda path=imported_path: (
                            self.toasts.toast(f"Imported Workshop blueprint: {path.name}", level="success"),
                            self.load_blueprints_async(),
                        )
                    )
                except Exception as exc:
                    self._ui(lambda msg=str(exc): self.toasts.toast(f"Import failed: {msg}", level="error"))

            threading.Thread(target=task, daemon=True).start()
            return

        mod_slug = ModioFetcher.parse_modio_url(url_or_id)
        if mod_slug:
            self.toasts.toast(f"Mod.io item '{mod_slug}' detected. Choose the downloaded zip.", level="info")
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

        self.toasts.toast("Could not parse a Workshop ID or Mod.io URL.", level="warning")

    def create_desktop_shortcut(self):
        try:
            import subprocess

            ps_script = Path(get_resource_path("create_desktop_shortcut.ps1"))
            if not ps_script.exists():
                ps_script = Path(__file__).resolve().parent.parent / "create_desktop_shortcut.ps1"
            if ps_script.exists():
                subprocess.run(
                    ["powershell", "-ExecutionPolicy", "Bypass", "-File", str(ps_script)],
                    check=True,
                    capture_output=True,
                    text=True,
                )
                self.toasts.toast("Desktop shortcut created.", level="success")
            else:
                self.toasts.toast("Shortcut script not found.", level="error")
        except Exception as exc:
            self.toasts.toast(f"Could not create desktop shortcut: {exc}", level="error")

    def open_selective_exchange(self):
        if not self.selected_blueprint:
            self.toasts.toast("Select a blueprint first.", level="warning")
            return
        win = ctk.CTkToplevel(self)
        win.title(f"Selective exchange — {self.selected_blueprint.display_name}")
        win.geometry("1120x740")
        win.configure(fg_color=TacticalTheme.BG_DARK)
        panel = SelectiveExchangePanel(
            win,
            on_selective_convert=lambda mapping, selected: self._run_selective_convert(mapping, selected),
        )
        panel.pack(fill="both", expand=True)
        panel.load_blueprint(self.selected_blueprint)

    def _run_selective_convert(self, mapping: Dict[str, str], selected: Set[str]):
        if not self.selected_blueprint:
            return
        bp = self.selected_blueprint
        self.control_panel.set_convert_enabled(False)
        self.control_panel.progress.start_indeterminate("Selective conversion...")
        self.footer.set_status("Selective convert…")

        def task():
            try:
                dest, scanned, converted = self.converter.create_selective_converted_blueprint(
                    bp.path,
                    custom_mapping=mapping,
                    selected_subtypes=selected,
                )
                self._ui(lambda: self._on_conversion_complete(dest, scanned, converted))
            except Exception as exc:
                error_message = str(exc)
                self._ui(lambda msg=error_message: self._on_conversion_error(msg))

        threading.Thread(target=task, daemon=True).start()

    def open_pb_doctor(self):
        if not self.selected_blueprint:
            self.toasts.toast("Select a blueprint first.", level="warning")
            return
        from pb_doctor import PBScriptExtractor, PBScriptValidator

        bp_file = self.selected_blueprint.path / "bp.sbc"
        scripts = PBScriptExtractor.extract_from_file(bp_file)
        reports = [PBScriptValidator.validate_script(s.custom_name, s.program_code) for s in scripts]

        win = ctk.CTkToplevel(self)
        win.title(f"PB Doctor — {self.selected_blueprint.display_name}")
        win.geometry("920x640")
        win.configure(fg_color=TacticalTheme.BG_DARK)
        textbox = ctk.CTkTextbox(
            win,
            font=TacticalTheme.FONT_MONO_SMALL,
            text_color=TacticalTheme.TEXT_CYAN,
            fg_color="#0c1220",
            border_color=TacticalTheme.BG_MEDIUM,
            border_width=1,
            corner_radius=6,
        )
        textbox.pack(fill="both", expand=True, padx=10, pady=10)
        if not scripts:
            content = "No programmable-block scripts found in this blueprint."
        else:
            lines = [f"Found {len(scripts)} programmable block(s).\n"]
            for script, report in zip(scripts, reports):
                lines.append(f"=== {script.custom_name} ({script.subtype_name}) ===")
                lines.append(f"Characters: {script.character_count}  Lines: {script.line_count}")
                lines.append(
                    f"Valid: {report.is_valid}  Score: {report.compliance_score}  Errors: {report.error_count}"
                )
                for diag in report.diagnostics:
                    loc = f"L{diag.line_number} " if diag.line_number else ""
                    lines.append(f"  [{diag.severity}] {loc}{diag.message}")
                lines.append("")
            content = "\n".join(lines)
        textbox.insert("end", content)
        textbox.configure(state="disabled")

    def split_active_blueprint_subgrids(self):
        if not self.selected_blueprint:
            self.toasts.toast("Select a multi-grid blueprint first.", level="warning")
            return

        from subgrid_engine import ProjectorSplitter

        result = ProjectorSplitter.split_blueprint(self.selected_blueprint.path)
        if not result.success:
            self.toasts.toast(f"Split failed: {result.error_message}", level="error")
            return
        if result.total_subgrids <= 1:
            self.toasts.toast("Single grid detected. Nothing to split.", level="info")
            return
        self._undo_stack.append(result.output_directory)
        self.toasts.toast(
            f"Created {result.total_subgrids} printable sub-blueprints in {result.output_directory.name}.",
            level="success",
            duration=5000,
        )
        self.load_blueprints_async()

    def survival_sanity_blueprint(self):
        if not self.selected_blueprint:
            self.toasts.toast("Select a blueprint first.", level="warning")
            return
        bp = self.selected_blueprint
        confirm = messagebox.askyesno(
            "Survival Sanity",
            f"Create a survival-craftable copy of '{bp.display_name}' by replacing Prototech blocks with vanilla equivalents?\n\n"
            "The original blueprint is not changed.",
        )
        if not confirm:
            return
        self._start_named_conversion(
            "Replacing Prototech blocks…",
            lambda: self.converter.survival_sanity_prototech(bp.path),
        )

    def upgrade_prototech_blueprint(self):
        if not self.selected_blueprint:
            self.toasts.toast("Select a blueprint first.", level="warning")
            return
        bp = self.selected_blueprint
        confirm = messagebox.askyesno(
            "Upgrade to Prototech",
            f"Create a Prototech copy of '{bp.display_name}'?\n\nThe original blueprint is not changed.",
        )
        if not confirm:
            return
        self._start_named_conversion(
            "Upgrading to Prototech…",
            lambda: self.converter.upgrade_to_prototech(bp.path),
        )

    def harden_active_armor(self):
        if not self.selected_blueprint:
            self.toasts.toast("Select a blueprint first.", level="warning")
            return
        dialog = ctk.CTkInputDialog(
            text="Radius around reactors, tanks, and cockpits (blocks):",
            title="Harden vital cores",
        )
        raw = dialog.get_input()
        if raw is None:
            return
        try:
            radius = int(raw.strip() or "2")
        except ValueError:
            self.toasts.toast("Radius must be a whole number.", level="warning")
            return
        bp = self.selected_blueprint

        def worker():
            from mappings.armor_hardening import ArmorHardeningEngine

            res = ArmorHardeningEngine.harden_vital_cores(bp.path, reinforce_radius=radius)
            return res.output_path, res.total_blocks_scanned, res.armor_blocks_hardened

        self._start_named_conversion("Hardening armor…", worker)

    def lightweight_active_armor(self):
        if not self.selected_blueprint:
            self.toasts.toast("Select a blueprint first.", level="warning")
            return
        dialog = ctk.CTkInputDialog(
            text="Keep heavy armor within this radius of vital cores (blocks):",
            title="Lightweight outer hull",
        )
        raw = dialog.get_input()
        if raw is None:
            return
        try:
            radius = int(raw.strip() or "1")
        except ValueError:
            self.toasts.toast("Radius must be a whole number.", level="warning")
            return
        bp = self.selected_blueprint

        def worker():
            from mappings.armor_hardening import ArmorHardeningEngine

            res = ArmorHardeningEngine.lightweight_outer_hull(bp.path, preserve_radius=radius)
            return res.output_path, res.total_blocks_scanned, res.armor_blocks_lightened

        self._start_named_conversion("Lightening outer hull…", worker)

    def export_se2_blueprint(self):
        if not self.selected_blueprint:
            self.toasts.toast("Select a blueprint first.", level="warning")
            return
        bp = self.selected_blueprint

        def worker():
            from engine_compat import SE2MigrationBridge

            return SE2MigrationBridge.migrate_se1_to_se2(bp.path)

        self._start_named_conversion("Exporting SE2 JSON…", worker)

    def _start_named_conversion(self, status: str, worker):
        self.control_panel.set_convert_enabled(False)
        self.control_panel.progress.start_indeterminate(status)
        self.footer.set_status(status)

        def task():
            try:
                dest, scanned, converted = worker()
                self._ui(lambda: self._on_conversion_complete(dest, scanned, converted))
            except Exception as exc:
                error_message = str(exc)
                self._ui(lambda msg=error_message: self._on_conversion_error(msg))

        threading.Thread(target=task, daemon=True).start()

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
        """Queue a callback for the Tk main thread. Safe to call from workers."""
        if self._closing:
            return
        self._ui_queue.put(callback)

    def _pump_ui_queue(self) -> None:
        if self._closing:
            return
        try:
            while True:
                callback = self._ui_queue.get_nowait()
                try:
                    if not self._closing:
                        callback()
                except Exception:
                    pass  # callback raced with shutdown or a destroyed widget
        except Empty:
            pass  # queue drained
        try:
            self.after(16, self._pump_ui_queue)
        except Exception:
            pass  # Tk is already torn down

    def _on_close(self):
        import tkinter as tk

        if self._closing:
            os._exit(0)
        self._closing = True
        self._inspect_generation += 1
        for attr in ("_rescan_after_id", "_preview_after_id"):
            job = getattr(self, attr, None)
            if job is not None:
                try:
                    self.after_cancel(job)
                except Exception:
                    pass  # after id already fired or Tk is gone
                setattr(self, attr, None)
        try:
            self.control_panel.progress.stop()
        except Exception:
            pass  # progress widget may already be destroyed
        try:
            self.toasts.dismiss_all()
        except Exception:
            pass  # toast overlay may already be destroyed
        try:
            if self._profile_editor is not None and self._profile_editor.winfo_exists():
                self._profile_editor.grab_release()
                self._profile_editor.destroy()
        except Exception:
            pass  # profile editor may already be closed
        try:
            for widget in list(self.winfo_children()):
                if isinstance(widget, (ctk.CTkToplevel, tk.Toplevel)):
                    try:
                        widget.destroy()
                    except Exception:
                        pass  # child toplevel already destroyed
        except Exception:
            pass  # winfo_children can fail after partial teardown
        try:
            self._drop_target.disable()
        except Exception:
            pass  # drag-drop subclass may already be restored
        try:
            self.destroy()
        except Exception:
            pass  # destroy is best-effort before os._exit
        os._exit(0)


def main():
    app = None
    try:
        app = TacticalCommandCenter()
        app.mainloop()
    except Exception as exc:
        try:
            messagebox.showerror("Fatal Error", f"Application failed to start:\n{exc}")
        except Exception:
            pass  # Tk may not be initialized enough to show a dialog
        os._exit(1)
    finally:
        if app is not None:
            try:
                if not getattr(app, "_closing", False):
                    app.destroy()
            except Exception:
                pass  # mainloop already destroyed the window
        os._exit(0)

if __name__ == "__main__":
    main()
