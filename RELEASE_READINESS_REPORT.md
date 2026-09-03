# SE Tactical Command 4.0.0 release-readiness report

Status: **HOLD — do not tag or publish.** The candidate is version `4.0.0`; the
major bump is intentional because the v4 document/renderer/UI and compatibility
contracts are a breaking surface change from 3.2.1.

## What is complete

- The v4 branch was reconciled with cumulative PR #29 on top of the latest v4
  master line. PRs #26–#28 are represented as one integrated result; #25 is an
  experimental duplicate; #12 is superseded by the tested CustomTkinter 6.x
  requirement. Remote PR retarget/close/merge actions remain pending until this
  working tree is committed and the final CI result is available.
- SE1 baseline is installed 1.210.014 / Steam build 24675677. The catalog has
  1,503 definitions and 116 validated light/heavy armor pairs. Identity-aware
  mappings include `TypeId` plus subtype and preserve empty/default subtypes;
  stale, ambiguous, cross-type, size, footprint, and non-public targets fail
  closed before writing.
- Conversion output is staged atomically, never overwrites an existing folder,
  and undo deletes only an unchanged output created by the current session.
  Analytics shows catalog coverage and partial status instead of claiming full
  cost, PCU, or mass truth.
- The 3D renderer compiles an OpenGL 3.3 shader on the RTX 4070 Ti SUPER. The
  responsive UI includes orbit, zoom, isolate, dissection, shell and reset
  controls, with documented simplification thresholds. Missing-root startup is
  an in-window empty state rather than a modal deadlock.
- The native SE2 bridge reads installed `.def` files and writes authentic
  `grid.json`, `.container-info`, and `snapshot` files with installed GUIDs.
  V7 serialization round-trips two authored single-grid armor fixtures and
  rejects subgrid-heavy and unsupported inputs with diagnostics. It does not
  write `.index`, use `VR3_*` identifiers, or silently fall back to armor.
- Both unified suites pass 328 tests on Python 3.11 and 3.12. Ruff, core/renderer
  mypy, runtime compilation/catalog validation, clean portable imports, and the
  frozen 4.0.0 executable self-test pass. The portable archive checksum is
  recorded in `artifacts/release-v4.0.0`.
- An isolated copy padded to the documented 28 MiB large-ship gate parsed in
  1.879 seconds and found four grids; the source fixture was not changed.

## Remaining release blockers

1. Open the corrected V7 single-grid fixtures in the installed SE2 2.4.0.95
   build, place them in the disposable creative world, save, reopen, and record
   the result. Then perform the separate subgrid/unsupported-loss report. The
   prior log proves the earlier Current fixture failed snapshot validation; it
   does not prove the corrected V7 fixture succeeds.
2. Complete the Windows live sweep at default and maximized sizes over Drone -
   MSG, MSGhome, Salvage Drone, and the 22.4 MB Space Dock fixture, including
   XML, analytics, PB Doctor, selective exchange, conversion, undo, and every
   3D interaction. The source app reached the missing-root state, but the
   desktop automation service exhausted its usage limit before the folder could
   be confirmed and controls exercised.
3. Rebuild from a clean committed checkout, run the final CI matrix, then push
   the integrated head to PR #29, retarget it to the v4 branch, merge it, and
   close the superseded PRs. Do not create a `v4.0.0` tag until the acceptance
   manifest changes to `APPROVED` with native SE2 evidence.

## Evidence index

See [release_acceptance.json](release_acceptance.json) for the fail-closed gate.
The four fixture source/copy hashes are in
[hash-verification-final.json](artifacts/live-fixture-appdata/hash-verification-final.json).
Native serialization and diagnostics are in `artifacts/native-se2-v7`; the
installed game log is retained outside the repository under the Space Engineers
2 log directory. The generated fixtures contain no user blueprint data.
