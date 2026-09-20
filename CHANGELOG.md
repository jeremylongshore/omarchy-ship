# Changelog

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
