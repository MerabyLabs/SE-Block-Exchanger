"""
Profile editor dialog for custom mapping profiles.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog
from typing import Callable, List, Optional

import customtkinter as ctk

from mapping_profiles import MappingProfile, ProfileManager
from mappings import build_registry
from mappings.registry import MappingCategory
from se_armor_replacer import ArmorBlockReplacer
from ui.theme import TacticalTheme


class ProfileEditorDialog(ctk.CTkToplevel):
    """Manage mapping profiles and mapping pairs."""

    def __init__(
        self,
        master,
        profile_manager: ProfileManager,
        on_profiles_changed: Optional[Callable[[], None]] = None,
        get_sample_blueprint: Optional[Callable[[], Optional[str]]] = None,
    ):
        super().__init__(master)
        self.title("Profile Editor")
        self.geometry("980x720")
        self.minsize(860, 620)
        self.configure(fg_color=TacticalTheme.BG_DARK)

        self.profile_manager = profile_manager
        self.on_profiles_changed = on_profiles_changed
        self.get_sample_blueprint = get_sample_blueprint
        self._known_block_ids = []
        self._current_profile: Optional[MappingProfile] = None
        self._current_category_name = ""
        self._pairs: List[List[str]] = []

        self._build_ui()
        self._refresh_known_block_ids()
        self._reload_profiles()

    def _build_ui(self):
        top = ctk.CTkFrame(self, fg_color=TacticalTheme.BG_MEDIUM, corner_radius=8)
        top.pack(fill="x", padx=10, pady=(10, 6))

        self.profile_var = ctk.StringVar(value="(new profile)")
        self.profile_menu = ctk.CTkOptionMenu(
            top,
            variable=self.profile_var,
            values=["(new profile)"],
            width=280,
            fg_color=TacticalTheme.BG_DARK,
            button_color=TacticalTheme.BG_GLASS,
            button_hover_color=TacticalTheme.CYAN_DIM,
            dropdown_fg_color=TacticalTheme.BG_MEDIUM,
            text_color=TacticalTheme.TEXT_CYAN,
            command=self._on_profile_selected,
        )
        self.profile_menu.pack(side="left", padx=8, pady=8)

        ctk.CTkButton(
            top,
            text="NEW",
            width=70,
            fg_color="transparent",
            border_width=1,
            border_color=TacticalTheme.CYAN_PRIMARY,
            text_color=TacticalTheme.CYAN_PRIMARY,
            command=self._new_profile,
        ).pack(side="left", padx=3)
        ctk.CTkButton(
            top,
            text="DUPLICATE",
            width=95,
            fg_color="transparent",
            border_width=1,
            border_color=TacticalTheme.GREEN_PRIMARY,
            text_color=TacticalTheme.GREEN_PRIMARY,
            command=self._duplicate_profile,
        ).pack(side="left", padx=3)
        ctk.CTkButton(
            top,
            text="IMPORT FILE",
            width=110,
            fg_color="transparent",
            border_width=1,
            border_color=TacticalTheme.ORANGE_PRIMARY,
            text_color=TacticalTheme.ORANGE_PRIMARY,
            command=self._import_file,
        ).pack(side="left", padx=3)
        ctk.CTkButton(
            top,
            text="IMPORT URL",
            width=110,
            fg_color="transparent",
            border_width=1,
            border_color=TacticalTheme.ORANGE_PRIMARY,
            text_color=TacticalTheme.ORANGE_PRIMARY,
            command=self._import_url,
        ).pack(side="left", padx=3)
        ctk.CTkButton(
            top,
            text="EXPORT",
            width=90,
            fg_color="transparent",
            border_width=1,
            border_color=TacticalTheme.CYAN_PRIMARY,
            text_color=TacticalTheme.CYAN_PRIMARY,
            command=self._export_profile,
        ).pack(side="left", padx=3)
        ctk.CTkButton(
            top,
            text="SHARE DISCORD",
            width=130,
            fg_color=TacticalTheme.CYAN_PRIMARY,
            text_color=TacticalTheme.BG_DARK,
            command=self._share_discord,
        ).pack(side="left", padx=6)

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=10, pady=6)
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, weight=1)

        # Metadata
        meta = ctk.CTkFrame(body, fg_color=TacticalTheme.BG_MEDIUM, corner_radius=8)
        meta.grid(row=0, column=0, sticky="nsew", padx=(0, 4))
        meta.columnconfigure(1, weight=1)

        fields = [
            ("Name", "name_entry"),
            ("Author", "author_entry"),
            ("Version", "version_entry"),
            ("Game Version", "game_entry"),
            ("Category Name", "category_entry"),
        ]
        for idx, (label, attr) in enumerate(fields):
            ctk.CTkLabel(meta, text=label, font=TacticalTheme.FONT_SMALL).grid(
                row=idx, column=0, sticky="w", padx=8, pady=(8 if idx == 0 else 4, 4)
            )
            entry = ctk.CTkEntry(meta, font=TacticalTheme.FONT_SMALL)
            entry.grid(row=idx, column=1, sticky="ew", padx=8, pady=(8 if idx == 0 else 4, 4))
            setattr(self, attr, entry)

        ctk.CTkLabel(meta, text="Description", font=TacticalTheme.FONT_SMALL).grid(
            row=5, column=0, sticky="nw", padx=8, pady=(4, 4)
        )
        self.description_box = ctk.CTkTextbox(meta, height=90, font=TacticalTheme.FONT_SMALL)
        self.description_box.grid(row=5, column=1, sticky="ew", padx=8, pady=(4, 4))

        # Pair editor
        pair_frame = ctk.CTkFrame(body, fg_color=TacticalTheme.BG_MEDIUM, corner_radius=8)
        pair_frame.grid(row=0, column=1, sticky="nsew", padx=(4, 0))
        pair_frame.columnconfigure(0, weight=1)
        pair_frame.columnconfigure(1, weight=1)

        ctk.CTkLabel(pair_frame, text="Source Block", font=TacticalTheme.FONT_SMALL).grid(
            row=0, column=0, sticky="w", padx=8, pady=(8, 4)
        )
        ctk.CTkLabel(pair_frame, text="Target Block", font=TacticalTheme.FONT_SMALL).grid(
            row=0, column=1, sticky="w", padx=8, pady=(8, 4)
        )
        self.source_combo = ctk.CTkComboBox(pair_frame, values=[""], font=TacticalTheme.FONT_SMALL)
        self.source_combo.grid(row=1, column=0, sticky="ew", padx=8, pady=4)
        self.target_combo = ctk.CTkComboBox(pair_frame, values=[""], font=TacticalTheme.FONT_SMALL)
        self.target_combo.grid(row=1, column=1, sticky="ew", padx=8, pady=4)

        ctk.CTkButton(
            pair_frame,
            text="ADD PAIR",
            width=90,
            command=self._add_pair,
            fg_color=TacticalTheme.CYAN_PRIMARY,
            text_color=TacticalTheme.BG_DARK,
        ).grid(row=2, column=0, padx=8, pady=4, sticky="w")
        ctk.CTkButton(
            pair_frame,
            text="REMOVE SELECTED",
            width=140,
            command=self._remove_selected_pair,
            fg_color="transparent",
            border_width=1,
            border_color=TacticalTheme.RED_PRIMARY,
            text_color=TacticalTheme.RED_PRIMARY,
        ).grid(row=2, column=1, padx=8, pady=4, sticky="e")

        list_frame = ctk.CTkFrame(pair_frame, fg_color=TacticalTheme.BG_DARK)
        list_frame.grid(row=3, column=0, columnspan=2, sticky="nsew", padx=8, pady=6)
        pair_frame.rowconfigure(3, weight=1)

        scroll = tk.Scrollbar(list_frame)
        scroll.pack(side="right", fill="y")
        self.pair_list = tk.Listbox(
            list_frame,
            yscrollcommand=scroll.set,
            bg="#0c1220",
            fg="#67e8f9",
            selectbackground="#f59e0b",
            selectforeground="#0f172a",
            font=("Consolas", 9),
            relief=tk.FLAT,
            activestyle="none",
        )
        self.pair_list.pack(side="left", fill="both", expand=True)
        scroll.config(command=self.pair_list.yview)

        bottom = ctk.CTkFrame(self, fg_color=TacticalTheme.BG_MEDIUM, corner_radius=8)
        bottom.pack(fill="x", padx=10, pady=(0, 10))

        ctk.CTkButton(
            bottom,
            text="TEST AGAINST SELECTED BLUEPRINT",
            command=self._test_profile,
            fg_color="transparent",
            border_width=1,
            border_color=TacticalTheme.GREEN_PRIMARY,
            text_color=TacticalTheme.GREEN_PRIMARY,
            width=260,
        ).pack(side="left", padx=8, pady=8)
        ctk.CTkButton(
            bottom,
            text="SAVE PROFILE",
            command=self._save_profile,
            fg_color=TacticalTheme.ORANGE_PRIMARY,
            text_color=TacticalTheme.BG_DARK,
            width=140,
        ).pack(side="left", padx=8)

        self.status_label = ctk.CTkLabel(
            bottom,
            text="Ready",
            font=TacticalTheme.FONT_SMALL,
            text_color=TacticalTheme.TEXT_GRAY,
        )
        self.status_label.pack(side="left", padx=10)

    def _refresh_known_block_ids(self):
        registry = build_registry(include_builtin=True)
        self._known_block_ids = [""] + sorted(
            {
                subtype
                for category in registry.list_categories()
                for pair in category.pairs.items()
                for subtype in pair
            }
        )
        self.source_combo.configure(values=self._known_block_ids)
        self.target_combo.configure(values=self._known_block_ids)

    def _reload_profiles(self):
        self.profile_manager.load_all()
        profiles = self.profile_manager.list_profiles()
        values = ["(new profile)"] + [profile.name for profile in profiles]
        self.profile_menu.configure(values=values)
        self.profile_var.set(values[0])
        self._new_profile()

    def _on_profile_selected(self, value: str):
        if value == "(new profile)":
            self._new_profile()
            return
        profile = self.profile_manager.get(value)
        self._current_profile = profile
        self._populate_profile(profile)

    def _populate_profile(self, profile: MappingProfile):
        self._set_entry(self.name_entry, profile.name)
        self._set_entry(self.author_entry, profile.author)
        self._set_entry(self.version_entry, profile.version)
        self._set_entry(self.game_entry, profile.game_version)
        self._set_textbox(self.description_box, profile.description)

        first_category = profile.categories[0] if profile.categories else None
        if first_category:
            self._set_entry(self.category_entry, first_category.name.split(":")[-1])
            self._pairs = [[src, tgt] for src, tgt in first_category.pairs.items()]
        else:
            self._set_entry(self.category_entry, "Custom Category")
            self._pairs = []
        self._refresh_pair_list()

    def _new_profile(self):
        self._current_profile = None
        self._set_entry(self.name_entry, "")
        self._set_entry(self.author_entry, "Meraby Labs")
        self._set_entry(self.version_entry, "1.0")
        self._set_entry(self.game_entry, "1.205+")
        self._set_entry(self.category_entry, "Custom Category")
        self._set_textbox(self.description_box, "")
        self._pairs = []
        self._refresh_pair_list()
        self.status_label.configure(text="Creating new profile.")

    def _add_pair(self):
        source = self.source_combo.get().strip()
        target = self.target_combo.get().strip()
        if not source or not target:
            messagebox.showwarning("Missing pair values", "Select source and target block IDs.")
            return
        if source == target:
            messagebox.showwarning("Invalid mapping", "Source and target cannot be the same.")
            return
        for existing_source, _ in self._pairs:
            if existing_source == source:
                messagebox.showwarning("Duplicate source", f"{source} already exists in this category.")
                return
        self._pairs.append([source, target])
        self._refresh_pair_list()
        self.status_label.configure(text=f"Added mapping: {source} -> {target}")

    def _remove_selected_pair(self):
        selection = self.pair_list.curselection()
        if not selection:
            return
        index = selection[0]
        removed = self._pairs.pop(index)
        self._refresh_pair_list()
        self.status_label.configure(text=f"Removed mapping: {removed[0]} -> {removed[1]}")

    def _refresh_pair_list(self):
        self.pair_list.delete(0, tk.END)
        for source, target in self._pairs:
            self.pair_list.insert(tk.END, f"{source:45} -> {target}")

    def _collect_profile(self) -> MappingProfile:
        name = self.name_entry.get().strip()
        author = self.author_entry.get().strip()
        version = self.version_entry.get().strip()
        game_version = self.game_entry.get().strip()
        category_name = self.category_entry.get().strip()
        description = self.description_box.get("1.0", "end").strip()

        if not name or not category_name:
            raise ValueError("Profile name and category name are required.")
        if not self._pairs:
            raise ValueError("Add at least one mapping pair.")

        category = MappingCategory(
            name=f"profile:{name.lower().replace(' ', '_')}:{category_name.lower().replace(' ', '_')}",
            description=description or f"{name} / {category_name}",
            pairs={source: target for source, target in self._pairs},
            source=f"profile:{name}",
            enabled_by_default=False,
            tags=("profile",),
        )

        return MappingProfile(
            name=name,
            author=author or "Unknown",
            version=version or "1.0",
            description=description or "Custom mapping profile",
            game_version=game_version or "unknown",
            categories=[category],
        )

    def _save_profile(self):
        try:
            profile = self._collect_profile()
            self.profile_manager.upsert_profile(profile)
            self.status_label.configure(text=f"Saved profile: {profile.name}")
            self._reload_profiles()
            self.profile_var.set(profile.name)
            self._on_profile_selected(profile.name)
            if self.on_profiles_changed:
                self.on_profiles_changed()
        except Exception as exc:
            messagebox.showerror("Save failed", str(exc))

    def _duplicate_profile(self):
        selected = self.profile_var.get()
        if selected == "(new profile)":
            messagebox.showwarning("No profile selected", "Select an existing profile to duplicate.")
            return
        new_name = simpledialog.askstring("Duplicate profile", "New profile name:")
        if not new_name:
            return
        try:
            profile = self.profile_manager.duplicate_profile(selected, new_name.strip())
            self.status_label.configure(text=f"Duplicated profile: {profile.name}")
            self._reload_profiles()
            if self.on_profiles_changed:
                self.on_profiles_changed()
        except Exception as exc:
            messagebox.showerror("Duplicate failed", str(exc))

    def _import_file(self):
        path = filedialog.askopenfilename(
            title="Import Profile",
            filetypes=[("Profile Files", "*.sebx-profile *.json"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            profile, saved_path = self.profile_manager.import_profile(path)
            self.status_label.configure(text=f"Imported {profile.name} -> {saved_path}")
            self._reload_profiles()
            if self.on_profiles_changed:
                self.on_profiles_changed()
        except Exception as exc:
            messagebox.showerror("Import failed", str(exc))

    def _import_url(self):
        url = simpledialog.askstring("Import from URL", "Profile URL:")
        if not url:
            return
        try:
            profile, saved_path = self.profile_manager.import_profile(url.strip())
            self.status_label.configure(text=f"Imported {profile.name} -> {saved_path}")
            self._reload_profiles()
            if self.on_profiles_changed:
                self.on_profiles_changed()
        except Exception as exc:
            messagebox.showerror("Import failed", str(exc))

    def _export_profile(self):
        selected = self.profile_var.get()
        if selected == "(new profile)":
            messagebox.showwarning("No profile selected", "Select a saved profile to export.")
            return
        path = filedialog.asksaveasfilename(
            title="Export Profile",
            defaultextension=".sebx-profile",
            filetypes=[("SEBX Profile", "*.sebx-profile")],
            initialfile=f"{selected.replace(' ', '_')}.sebx-profile",
        )
        if not path:
            return
        try:
            destination = self.profile_manager.export_profile(selected, path)
            self.status_label.configure(text=f"Exported profile to {destination}")
        except Exception as exc:
            messagebox.showerror("Export failed", str(exc))

    def _share_discord(self):
        selected = self.profile_var.get()
        if selected == "(new profile)":
            messagebox.showwarning("No profile selected", "Select a saved profile to share.")
            return
        try:
            formatted = self.profile_manager.discord_share_text(selected)
            self.clipboard_clear()
            self.clipboard_append(formatted)
            self.status_label.configure(text="Discord share payload copied to clipboard.")
        except Exception as exc:
            messagebox.showerror("Share failed", str(exc))

    def _test_profile(self):
        if not self.get_sample_blueprint:
            messagebox.showwarning("No sample blueprint", "No blueprint callback configured.")
            return
        sample_path = self.get_sample_blueprint()
        if not sample_path:
            messagebox.showwarning(
                "No blueprint selected",
                "Select a blueprint in the main window before testing profile.",
            )
            return
        try:
            profile = self._collect_profile()
            registry = build_registry(include_builtin=True)
            for category in profile.categories:
                registry.register(category, overwrite=True if registry.exists(category.name) else False)
            active_categories = [category.name for category in profile.categories]
            replacer = ArmorBlockReplacer(
                reverse=False,
                enabled_categories=active_categories,
                registry=registry,
                include_profiles=False,
            )
            _, replacements = replacer.process_blueprint(sample_path, create_backup=False, dry_run=True)
            self.status_label.configure(
                text=f"Test complete: {replacements} block(s) would be converted in {sample_path}."
            )
        except Exception as exc:
            messagebox.showerror("Test failed", str(exc))

    @staticmethod
    def _set_entry(entry: ctk.CTkEntry, value: str):
        entry.delete(0, tk.END)
        entry.insert(0, value)

    @staticmethod
    def _set_textbox(box: ctk.CTkTextbox, value: str):
        box.delete("1.0", "end")
        box.insert("end", value)
