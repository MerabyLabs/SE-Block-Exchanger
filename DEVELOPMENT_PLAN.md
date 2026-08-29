# SE Block Exchanger â€” Development Plan v3.0

**Meraby Labs** | Created: 2026-02-07  
**Current Version:** 3.0 | **Target:** 3.0+

---

## Overview

Five-phase roadmap to evolve SE Block Exchanger from a single-purpose armor swapper into a full-featured blueprint engineering toolkit with a modern UI, expanded conversions, analytics, mod support, and automated distribution.

---

## Phase 1 â€” Modern UI Overhaul

**Goal:** Replace raw tkinter with CustomTkinter; decompose the monolithic `gui_standalone.py` (1,144 lines) into clean, testable modules.

### 1.1 Framework Migration
- [x] Add `customtkinter` dependency
- [x] Create `ui/` package with dedicated modules per panel
- [x] Migrate theme system to CTk appearance modes (Light/Dark/System)
- [x] Preserve Meraby Labs branding (header logo, subtitle, footer)

### 1.2 Component Decomposition
| Module | Responsibility |
|---|---|
| `ui/app.py` | Main application window, layout orchestration |
| `ui/header.py` | Logo, title, subtitle bar |
| `ui/control_panel.py` | Conversion direction, action buttons |
| `ui/blueprint_panel.py` | Blueprint browser, selection, batch queue |
| `ui/preview_panel.py` | Before/after conversion diff view |
| `ui/footer.py` | Status bar, version, Meraby Labs credit |
| `ui/theme.py` | Color palette, font definitions, CTk config |
| `ui/widgets/` | Reusable custom widgets (below) |

### 1.3 New Widgets
- [x] **Blueprint Card** (`ui/widgets/blueprint_card.py`) â€” Thumbnail, name, grid size, block count, status badge
- [x] **Toast Notifications** (`ui/widgets/toast.py`) â€” Auto-dismissing success/error/info popups
- [x] **Progress Ring** (`ui/widgets/progress_ring.py`) â€” Animated circular progress for batch operations
- [x] **Before/After Preview** â€” Side-by-side or tabbed diff showing exactly which blocks change

### 1.4 UX Improvements
- [x] Drag-and-drop blueprint folder/file loading
- [x] Keyboard shortcuts (Ctrl+O open, Ctrl+R run, Ctrl+Z undo)
- [x] Recent blueprints list with quick-access
- [x] Responsive layout that scales with window resize

### Deliverables
- Zero-regression on all 19 existing tests
- New UI screenshot gallery in README
- `requirements.txt` updated with `customtkinter`

---

## Phase 2 â€” Expanded Block Conversions

**Goal:** Move beyond armor-only swaps. Add thruster tiers, weapon upgrades, functional block swaps. Make the mapping system pluggable.

### 2.1 Modular Mapping Registry
- [x] Define `MappingCategory` dataclass: `name`, `description`, `pairs[]`, `grid_sizes[]`
- [x] Create `mappings/` package:
  ```
  mappings/
    __init__.py          # Registry loader
    armor.py             # Existing 70 armor pairs
    thrusters.py         # Thruster tier swaps
    weapons.py           # Weapon upgrades
    functional.py        # Functional block swaps
    registry.py          # Central registry, category enable/disable
  ```
- [x] Migrate existing 70 armor pairs into `mappings/armor.py`

### 2.2 New Mapping Categories

**Thrusters** (Small â†” Large component variants):
| Swap | Example |
|---|---|
| Ion tier | Small â†’ Large Ion Thruster |
| Hydrogen tier | Small â†’ Large Hydrogen Thruster |
| Atmospheric tier | Small â†’ Large Atmospheric Thruster |

**Weapons:**
| Swap | Example |
|---|---|
| Gatling â†’ Autocannon | Interior Turret â†’ Assault Cannon |
| Rocket â†’ Artillery | Rocket Launcher â†’ Artillery |

**Functional Blocks:**
| Swap | Example |
|---|---|
| Basic â†’ Upgraded | Basic Refinery â†’ Refinery |
| Basic â†’ Upgraded | Basic Assembler â†’ Assembler |
| Battery variants | Small Battery â†’ Battery |

### 2.3 Engine Refactor
- [x] Refactor `blueprint_scanner.py` / `blueprint_converter.py` to accept any `MappingCategory`
- [x] Support multi-category conversion in a single pass
- [x] Add per-category enable/disable toggles in GUI
- [x] Validate mappings at load time (no circular swaps, no duplicate targets)

### Deliverables
- Mapping registry with at least 4 built-in categories
- GUI category selector panel
- Unit tests per mapping category
- `verify_mappings.py` updated to validate all categories

---

## Phase 3 â€” Blueprint Analytics Dashboard

**Goal:** Give users deep insight into their blueprints â€” resource costs, PCU, mass, block distribution, and conversion cost comparisons.

### 3.1 Resource Cost Calculator
- [x] Build component-cost database (`data/block_costs.json`):
  - Steel Plates, Interior Plates, Construction Components, Motors, etc.
  - Per-block component requirements (from SE wiki/game data)
- [x] Calculate total components needed for entire blueprint
- [x] Calculate ingot requirements (smelt-back from components)
- [x] Calculate raw ore requirements (refine-back from ingots)
- [x] Display in collapsible tree: Ores â†’ Ingots â†’ Components â†’ Blocks

### 3.2 PCU & Mass Analysis
- [x] PCU counter per block type, total PCU, PCU budget warnings
- [x] Mass calculation (empty mass, with cargo estimates)
- [x] Block-count-by-category pie/bar chart (armor, weapons, thrusters, utility, etc.)

### 3.3 Conversion Cost Comparison
- [x] "What does upgrading cost?" panel:
  - Before: 1,200 Light Armor Blocks = 25 Steel Plates each = 30,000 total
  - After: 1,200 Heavy Armor Blocks = 150 Steel Plates each = 180,000 total
  - **Delta: +150,000 Steel Plates**
- [x] Display deltas for all resource types
- [x] Export cost report as CSV or text

### 3.4 Blueprint Health Audit
- [x] Detect common issues:
  - Missing essential blocks (no Cockpit, no Reactor/Battery)
  - Unbalanced thruster layout warnings
  - Blocks from uninstalled DLC/mods
- [x] Severity levels: Info / Warning / Error
- [x] One-click "fix" suggestions where possible

### Deliverables
- Analytics tab in GUI with charts and tables
- Cost comparison panel integrated into conversion workflow
- Exportable reports (CSV/TXT)
- Block cost database covering vanilla SE blocks

---

## Phase 4 â€” Custom Mapping Profiles & Mod Support

**Goal:** Let users create, edit, import/export, and share custom mapping profiles. Ship built-in profiles for popular mods.

### 4.1 Profile System
- [x] JSON-based profile format:
  ```json
  {
    "name": "WeaponCore Upgrades",
    "author": "Meraby Labs",
    "version": "1.0",
    "description": "Swap vanilla weapons for WeaponCore equivalents",
    "game_version": "1.205+",
    "categories": [
      {
        "name": "WC Turrets",
        "pairs": [
          ["LargeGatlingTurret", "WC_LargeGatlingTurret"],
          ...
        ]
      }
    ]
  }
  ```
- [x] Profile storage: `profiles/` directory, auto-discovered at startup
- [x] Profile validation on load (schema check, circular reference detection)

### 4.2 Profile Editor (GUI)
- [x] Create new profile wizard
- [x] Add/remove/edit mapping pairs with autocomplete from known block IDs
- [x] Test profile against a sample blueprint before saving
- [x] Duplicate and modify existing profiles

### 4.3 Import/Export & Sharing
- [x] Export profile as `.sebx-profile` (JSON with metadata)
- [x] Import from file or URL
- [x] "Share on Discord" button â€” copies profile JSON to clipboard with formatted message
- [x] Built-in profile browser for community-submitted profiles (future)

### 4.4 Built-in Mod Profiles
- [x] **WeaponCore** â€” Vanilla â†’ WC weapon equivalents
- [x] **Build Vision** â€” Enhanced block variants
- [x] **Assertive Armaments** â€” Military weapon swaps
- [x] Community contribution guide for creating profiles

### Deliverables
- Profile JSON schema and validator
- Profile editor GUI tab
- At least 2 built-in mod profiles
- Import/export functionality
- Profile documentation for community contributors

---

## Phase 5 â€” Distribution & Community

**Goal:** Automate releases, add in-app updates, changelog viewer, and centralized version management.

### 5.1 GitHub Actions CI/CD
- [x] Workflow: `.github/workflows/release.yml`
  - Trigger on version tag push (`v3.0.0`)
  - Run full test suite
  - Build EXE with PyInstaller
  - Create GitHub Release with EXE artifact and changelog
- [x] Workflow: `.github/workflows/ci.yml`
  - Run on every PR/push to main
  - Lint (flake8/ruff), type check (mypy), test (pytest)
- [x] Badge in README: build status, latest release, download count

### 5.2 Version Management
- [x] Single source of truth: `version.py`
  ```python
  __version__ = "3.0.0"
  __build_date__ = "2026-XX-XX"
  __channel__ = "stable"  # stable | beta | dev
  ```
- [x] All references (GUI footer, CLI banner, PyInstaller spec) read from `version.py`
- [x] Semantic versioning enforced

### 5.3 In-App Update Checker
- [x] Check GitHub Releases API on startup (with 24h cache)
- [x] Non-intrusive notification: "Version 3.1.0 available â€” [View Changelog] [Download]"
- [x] User preference to disable auto-check
- [x] Changelog viewer: render markdown release notes in-app

### 5.4 Community Infrastructure
- [x] Issue templates (bug report, feature request, mapping request)
- [x] Contributing guide (`CONTRIBUTING.md`)
- [x] Code of conduct
- [x] Discord integration links in GUI Help menu

### Deliverables
- Fully automated release pipeline
- In-app update notifications
- Version centralization
- Community contribution infrastructure

---

## Priority & Sequencing

```
Phase 1 â”€â”€â–º Phase 2 â”€â”€â–º Phase 3
                â”‚              â”‚
                â””â”€â”€â–º Phase 4 â”€â”€â”˜
                         â”‚
                         â–¼
                      Phase 5
```

| Phase | Est. Effort | Dependencies |
|---|---|---|
| 1 â€” Modern UI | Medium | None (can start immediately) |
| 2 â€” Expanded Conversions | Medium | Core engine refactor |
| 3 â€” Analytics Dashboard | High | Phase 2 mapping registry |
| 4 â€” Custom Profiles | Medium | Phase 2 mapping registry |
| 5 â€” Distribution | Low-Medium | All phases (final polish) |

**Phases 3 and 4** can be developed in parallel after Phase 2 completes.  
**Phase 5** is independent but best done last to package everything.

---

## Technical Constraints

- **Python 3.8+** minimum (match SE modding community's typical setup)
- **CustomTkinter** is the only new required dependency for Phase 1
- **Pillow** remains optional (logo rendering)
- **No internet required** for core functionality (update checker is opt-in)
- **Backward compatibility**: existing CLI usage (`python se_armor_replacer.py <path>`) must continue working unchanged

---

## Success Metrics

| Metric | Target |
|---|---|
| Test coverage | â‰¥ 85% across all modules |
| Startup time | < 2 seconds (GUI cold start) |
| Conversion speed | < 1 second per blueprint (single pass) |
| Profile load time | < 100ms per profile |
| EXE size | < 50 MB (PyInstaller bundle) |
| Zero regressions | All existing tests pass at every phase |

---

*Meraby Labs â€” Building better blueprints, one block at a time.*

