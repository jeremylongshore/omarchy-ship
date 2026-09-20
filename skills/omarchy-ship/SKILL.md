---
name: omarchy-ship
description: |
  Runs the full pre-submission lane for an Omarchy plugin: the contributing-clanker
  gate lane, the offline test suite, rig validation and a real headless render on the
  buzz rig, then delegates coverage accounting and submission judgment to subagents
  and refuses to emit a submission when any check could not run. Use when preparing a
  marketplace submission or verify request, before pushing a plugin change, or when a
  plugin looks green and you need to know what that green actually covers.
  Trigger with "/omarchy-ship", "ship this omarchy plugin", "is this ready to submit",
  "run the submission lane".
allowed-tools: Read, Glob, Grep, Bash(git:*), Bash(bash:*), Bash(jq:*), Bash(docker:*), Bash(gh:*), Bash(npm:*), Task, AskUserQuestion
version: 1.3.0
author: Jeremy Longshore <jeremy@intentsolutions.io>
license: MIT
compatibility: Requires git, jq and docker on PATH, a contributing-clanker checkout for the canonical gate lane, and the omarchy-rig container for rig checks
tags:
  - omarchy
  - quickshell
  - submission
  - gates
  - verification
argument-hint: "[plugin-dir-or-name]"
model: inherit
---

# Omarchy Ship

## Overview

Takes an Omarchy plugin from "I think it works" to a submission you can defend,
and stops when it cannot.

The lane runs four layers of verification, then hands the results to two
subagents: one that accounts for what was actually checked, and one that renders
submission judgment. The final answer is one of three words, and only one of them
lets you file.

The reason this skill exists is that every layer of this stack has, at some
point, reported success without having checked anything:

| Layer | How it lied |
| --- | --- |
| Gate lane | `c32`/`c33` skipped when rig binaries were missing; the runner counted SKIP as PASS and printed `verdict PASS, 0 BLOCK` for plugins never run on Omarchy |
| Gate enumeration | `git ls-files` lists tracked files only, so `c38` answered `PASS - no narrow-dotted-quad host filter found` about a file it had never opened |
| Empty corpus | `c36` answered PASS over a tree containing no QML at all |
| CI review | Jobs gated on an unset variable skip, and a skipped job renders as a grey tick that reads as four completed reviews |
| Static validation | `omarchy-plugin-validate` and `qmllint` are both static; a `KeyboardPanel` used where a `PanelWindow` belongs passes both and fails on load |
| Rig render | The render hooks seed the plugin's cache from a small fixture, so a dead endpoint or an undersized response bound renders identically to a working one. A release was 76 tests, 13/13 gates and a clean render green while no real user could load any data |
| Working tree | Fingerprints were built from `find .`, so ignored debris (nested `node_modules`, an ignored state store) made a receipt disagree with the commit it certified. Green in CI, blocked on a developer disk, same commit |
| Submission guard | The filing hook matched the marketplace by its old repo name. After the repo moved orgs, filing to the new name skipped the gates and the receipt check with no message |

The through-line is one defect: **a component reporting a conclusion whose scope
it never established.** This lane is built so that cannot happen quietly.

## Prerequisites

- A plugin directory containing `manifest.json`. Without it every gate answers
  `not an Omarchy plugin tree` and abstains, which empties the lane silently.
- A `contributing-clanker` checkout for the canonical gate lane.
- The `omarchy-rig` container for rig validation and render. If it is
  unreachable, rig checks become UNPROVEN, never "not applicable".
- `git`, `jq`, `docker` on PATH.

## Instructions

### Step 0: Check that this skill's own knowledge is still true

Everything this skill says about the marketplace is a copy of somebody else's
document, host or repository, and copies go stale without announcing it. From a
checkout of this plugin's repository, run:

```
python3 scripts/check-contracts.py --check-heads --live
```

If it reports drift, read the named upstream document and re-check the listed
assumptions BEFORE trusting `references/submission-format.md`. A submission built
from a stale form is rejected by a bot, not a person. If the check cannot run,
say so in the report; do not assume the references are current.

### Step 1: Resolve the plugin and prove the tree is real

Accept a path or a bare name. Resolve a bare name against the sibling
`omarchy-{name}-entry` convention.

Confirm `manifest.json` exists and parses, and that it declares `entryPoints`.
`c35` abstains without them. If the tree does not resolve, stop here and report
`NO COVERAGE`. Do not run the lane and present its abstentions as a clean result.

### Step 2: Check the vendored lane against canonical BEFORE running it

The vendored lane is hash-pinned per repo, and the freshness check iterates the
local manifest, so a gate that canonical has added is invisible to it by
construction. Compare the two file lists directly.

Report any gate canonical carries that this tree does not as a coverage hole,
by name. A shrunken lane must never produce a clean report against its own
smaller denominator.

### Step 3: Run the four layers

Run every layer even if an early one fails, because a single BLOCK should not hide
the state of everything else:

1. **Gate lane** - the vendored `run-plugin-gates.sh`.
2. **Offline tests** - the repo's own suite.
3. **Rig validation** - `omarchy-plugin-validate` plus `qmllint` on the rig.
4. **Rig render** - load the plugin into a real shell and capture QML warnings.
5. **Live first run** - for any plugin that touches the network: run it on the
   rig as a first-run user, with an EMPTY cache and the real network, and assert
   from inside the shell that the plugin itself fetched real data. Always run a
   control that must fail (the old URL, the old bound), or the test proves nothing.
   A plugin with no network path marks this NOT APPLICABLE, never PASS.
   Run it with `scripts/live-first-run.sh <plugin-tree> <label> [min-calls] [wait-seconds]`.
   It swaps the plugin's fixture `curl` for a pass-through wrapper, so the plugin's
   own argv hits the real host on the rig, and it fails unless every fetch exits 0
   with a body. Read the trace: a START followed by KILLED and no new START is a
   fetch the plugin stopped and never restarted.

Layer 4 is the one that earns its keep for QML. Both static checks pass a plugin whose
QML contract is wrong; only loading it catches that. Treat any QML warning as a
finding, not noise.

Layer 5 is the one that earns its keep for data. Layer 4 renders whatever the
fixture says, so it cannot see a host that moved, a response that outgrew its
bound, or an error path that hides the failure. Validate a curl argv on the rig,
not on a developer box: curl 8.21 counts the DECODED body against
`--max-filesize` and exits 63, where curl 8.5 counted bytes on the wire, so the
same command passes on one and fails on the other.

If the working clone carries ignored debris, run the lane against a pristine
clone of the target commit. That is the tree the marketplace reviews.

### Step 4: Delegate coverage accounting

Spawn the `omarchy-coverage-reporter` agent with the raw results. It separates
NOT APPLICABLE (the predicate is false; this tree has no QML) from UNPROVEN (the
predicate is true but the checker could not run), and returns a denominator.

Do not compute this inline. The agent is read-only by construction, and a
reporter that can also repair what it measures cannot be trusted about what it
measured.

### Step 5: Delegate submission judgment

Spawn `omarchy-submission-auditor` for the qualitative read: does this install
and run on a stock box, does it hold the QML security invariants, does it match
first-party idiom. That is judgment, and it is deliberately a different agent
from the one counting checks.

Run steps 4 and 5 concurrently. They do not depend on each other.

### Step 6: Decide, and be willing to refuse

Combine into exactly one verdict:

- **CLEAN** - every applicable check ran, none found anything, zero UNPROVEN.
- **FINDINGS** - checks ran and found something. Fix, then re-run.
- **INCONCLUSIVE** - at least one applicable check could not run.

`INCONCLUSIVE` is not a failure and it is not a pass. It means nobody knows yet.
**Only CLEAN proceeds to Step 7.** On INCONCLUSIVE, print each UNPROVEN item with
the command that resolves it and stop.

This refusal is the entire point of the skill. A lane that always produces a
submission is a lane whose verdict carries no information.

### Step 7: Emit the submission

Only on CLEAN. Produce the marketplace issue body per
[the submission format](references/submission-format.md), including the coverage
fraction as evidence rather than a bare assertion that it passed.

Do not file it. Print it for review. Filing is the operator's action, and the
`gh issue create` guard enforces a passing lane and a fresh rig receipt
independently at that moment.

## Output

```
OMARCHY SHIP: {plugin}
================================================================
Tree      {path}   manifest: ok   entryPoints: {n}
Lane      {m} applicable of {n} canonical    [DRIFT: {gate} missing]

Gates     {p} ran clean · {f} found · {na} n/a · {u} UNPROVEN
Tests     {p}/{t}
Rig       validate {r} · qmllint {q} · render {w}

COVERAGE  {ran}/{applicable}
VERDICT   CLEAN | FINDINGS | INCONCLUSIVE

on FINDINGS  each finding, its gate and reason
on INCONCLUSIVE  each UNPROVEN item + the command that resolves it
on CLEAN  the submission body, printed and not filed
```

## Error Handling

| Error | Cause | Solution |
| --- | --- | --- |
| `NO COVERAGE` | No `manifest.json`; every gate abstained | Confirm the tree is a plugin root, not its parent |
| Lane reports PASS with 0 gates run | Tree unresolved or lane empty | This is the original defect; treat as INCONCLUSIVE and check drift |
| Rig unreachable | Container down | Rig checks are UNPROVEN, never n/a. Start the rig and re-run |
| Render shows QML warnings | A real contract error | Fix it. Static checks pass these; the load is the only signal |
| A gate crashes | Bug in the gate | Fail closed as UNPROVEN. Never a pass. Report it against the canonical gate source; do not patch the vendored copy |
| Vendored lane behind canonical | Sync drift | Re-sync, then re-run. Report against the canonical denominator |
| Asked to skip a failing check | Deadline pressure | Say no. Report INCONCLUSIVE and name what is unproven |

## Examples

**Ready to file**

```
/omarchy-ship bazaar
→ COVERAGE 9/9 · VERDICT CLEAN · submission body printed
```

**Refuses because the rig is down**

```
/omarchy-ship pit-wall
→ UNPROVEN: rig render (container unreachable)
  → resolve with: docker start omarchy-rig
  VERDICT INCONCLUSIVE: no submission emitted
```

**Catches the silent-empty case**

```
/omarchy-ship ~/000-projects   # parent dir, not a plugin
→ NO COVERAGE: no manifest.json; every gate would abstain
```

## Resources

- [Submission format](references/submission-format.md) - marketplace issue body and verify-request shape
- [Defect catalog](references/defect-classes.md) - the classes this lane exists to catch, each with the incident behind it
- Agents, shipped in this plugin's `agents/` directory: `omarchy-coverage-reporter`
  (accounting), `omarchy-submission-auditor` (judgment), and
  `omarchy-plugin-architect` (designing a plugin that passes the lane to begin with)
