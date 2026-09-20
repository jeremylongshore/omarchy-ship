# Changelog

## [1.3.0] - 2026-09-20

### Added

- `contracts/upstream-contracts.json` and `scripts/check-contracts.py`: a watch on
  every upstream document, repository and endpoint the skill depends on. Documents
  are pinned by commit and sha256 with the assumptions drawn from them and the
  local files that repeat them. Repositories are checked for the owner/name they
  resolve to. Endpoints are checked for status and shape without following
  redirects. A weekly workflow opens an issue with the report.
- Step 0 in the skill: check that the skill's own knowledge is still true before
  trusting its references.
- CI: offline unit tests, contracts validation, and a check that the version
  agrees across the plugin manifest, the marketplace manifest and the skill.

The pin-and-watch design, and the version agreement check, follow
tcballard/build-omarchy-plugins (MIT).

## [1.2.0] - 2026-09-20

### Added

- `scripts/live-first-run.sh`, the implementation of layer 5. It builds a
  throwaway copy of a plugin, replaces the fixture `curl` with a pass-through
  wrapper, seeds no state, and runs it in the real shell on the rig. It fails
  unless every fetch exits 0 with a body, and prints a START / KILLED / END trace.
  On its first day it found a first-run race in a shipped plugin that 89 offline
  tests, 13 gates, static validation and a clean render had all passed: the
  plugin stopped its own schedule fetch 6 ms after starting it and never
  restarted it.

## [1.1.0] - 2026-09-20

First public release.

### Added

- Layer 5, the live first-run test: empty cache, real network, an assertion from
  inside the shell, and a control that must fail.
- Three defect classes, each from a real incident: a render that cannot see the
  network, a receipt that certifies the wrong tree, and a tool whose behavior
  changed under a pinned assumption.
- The three subagents the skill delegates to now ship with it.

### Changed

- Submissions go to `omacom/omarchy-plugin-marketplace`, the repo's home since
  2026-08-30. The verify-request body is now the issue form's own headings,
  verbatim, because the marketplace bot parses them.
- `approved-and-verified` is documented as the only label that publishes.
  `approved-for-listing` is a legacy audit label.
- Removed references to an `omarchy-gate-author` agent that was never published.

## [1.0.0]

Private use.
