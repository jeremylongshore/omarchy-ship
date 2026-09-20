# Defect classes this lane exists to catch

Every entry is an incident, not a hypothetical. Each shipped, or reached a
marketplace reviewer, or was found only by loading the plugin into a running
shell.

## Contents

- [The unifying shape](#the-unifying-shape)
- [1. A check that reports success without checking](#1-a-check-that-reports-success-without-checking)
- [2. Runtime absent from the graphical session](#2-runtime-absent-from-the-graphical-session)
- [3. Credentials in argv](#3-credentials-in-argv)
- [4. Untrusted text rendered as markup](#4-untrusted-text-rendered-as-markup)
- [5. Unbounded reads in a process that never restarts](#5-unbounded-reads-in-a-process-that-never-restarts)
- [6. SSRF filters that enumerate bad forms](#6-ssrf-filters-that-enumerate-bad-forms)
- [7. QML contract errors that only a load catches](#7-qml-contract-errors-that-only-a-load-catches)
- [8. Silent truncation](#8-silent-truncation)
- [9. A render that cannot see the network](#9-a-render-that-cannot-see-the-network)
- [10. A receipt that certifies the wrong tree](#10-a-receipt-that-certifies-the-wrong-tree)
- [11. A tool whose behavior changed under a pinned assumption](#11-a-tool-whose-behavior-changed-under-a-pinned-assumption)

## The unifying shape

**A component reports a conclusion whose scope it never established.**

Five instances, four layers, one week:

1. `c32`/`c33` call `gate_skip` when rig binaries are unresolvable. The runner
   counted SKIP as PASS, so the lane printed `verdict PASS, 0 BLOCK` for plugins
   that had never run on Omarchy.
2. A review workflow gated on a repo variable. Unset means the jobs skip, and a
   skipped job renders as a grey tick. Four grey ticks looked like four
   completed reviews.
3. `gate_tree_files` enumerated with `git ls-files`, which lists tracked files
   only. With an untracked file present, `c38` answered
   `PASS - no narrow-dotted-quad host filter found` about a file it never opened.
4. `c36` answered PASS over an empty corpus, asserting that no QML text could
   overflow in a tree containing no QML.
5. A cron script missing `export PATH` failed silently for eight nights. A job
   that never ran was indistinguishable from a job that succeeded.

The remedy is always the same: carry the denominator. `PASS` alone is not an
output.

## 1. A check that reports success without checking

**Rule.** `PASS` means checked-and-clean. `SKIP` means there was nothing to
check. Collapsing them is the defect.

Split `SKIP` further, because it means two incompatible things:

- **NOT APPLICABLE** - the predicate is false. This tree has no QML, so a QML
  gate has nothing to say. Safe to aggregate as a pass.
- **UNPROVEN** - the predicate is true but the checker could not run. The tree
  has QML and `qmllint` is unresolvable. **Never aggregates to a pass.**

Any UNPROVEN makes the run `INCONCLUSIVE`.

**Verification traps that have each produced a wrong verdict here:**

- `cmd | head; echo $?` reports *head's* exit code. Capture the status directly.
- `git grep` searches tracked files only. Use `git grep --untracked`, or walk the
  filesystem, before concluding a pattern is absent. Never stage a probe; that
  mutates the caller's index.
- `grep -c "string" file` matches a string inside a file that does not parse.
  This is how a committed merge conflict was reported as a present, correct
  workflow. Parse, do not grep, when the claim is about validity.

## 2. Runtime absent from the graphical session

Omarchy's graphical session has **no node, python or ruby on PATH**; mise shims
are not exported to it. A plugin that shells out to any of them works on the
author's box and fails for every user.

Pure QML plus shell only. A shipped `.py` in a plugin repo is a runtime
dependency waiting to be mistaken for one.

## 3. Credentials in argv

A secret passed as a command-line argument is world-readable through
`/proc/<pid>/cmdline` for the life of the process.

Wrong: `curl -H "Authorization: Bearer $TOKEN"`, `jq --arg t "$TOKEN"`, any
interpolation into a `Process` command array.

Right: stdin. `curl` reads headers with `--header @-`; `jq` reads with `-R` and
`input`. An env var is better than argv because `/proc/<pid>/environ` is
owner-only, but stdin is the standard here. `printf` and `echo` are builtins and
fork nothing, so a secret inside them is fine.

## 4. Untrusted text rendered as markup

Any string from a network response, a file another program writes, or a
third-party catalog is untrusted. Every `Text` rendering it must set
`textFormat: Text.PlainText`, or Qt's AutoText sniffs it and may render markup.

Journal and log content counts. `logger -t x '<script>alert(1)</script>'`
round-trips verbatim through `journalctl -o json`.

## 5. Unbounded reads in a process that never restarts

The plugin lives in a Quickshell process that never restarts. Any read whose
size is controlled by something other than this code needs a **file-count bound
and a byte bound**, enforced at the reader and again at the parser.

## 6. SSRF filters that enumerate bad forms

A host allowlist that rejects only the canonical dotted quad is broken. `curl`
resolves through `inet_aton`, which accepts one to four parts and reads a
leading `0` as octal and `0x` as hex, so `127.1`, `0177.0.0.1` and `0x7f.1` all
reach loopback past a `/^\d{1,3}(\.\d{1,3}){3}$/` test. Userinfo is another
bypass: `https://user@127.0.0.1/` hides the host before the `@`.

Enumerating bad forms failed twice. Invert the rule: strip userinfo, split on the
dot, and reject the host if **every** label is numeric in any base.

## 7. QML contract errors that only a load catches

`omarchy-plugin-validate` and `qmllint` are both static. Neither catches:

- A `KeyboardPanel` used where a `PanelWindow` belongs.
- `module.exports` in a `.js` a QML file imports. QML sees top-level `function`
  declarations and vars, not CommonJS exports. A helper exported only via
  `module.exports` is invisible at runtime and `qmllint` says nothing.
- A stale duplicate install shadowing the tree under test.

Only `rig-render` catches these. Any QML warning from the load is a finding.

## 8. Silent truncation

A bound applied without saying so is its own defect. A capped read that reports a
confident total is indistinguishable from a complete one.

This shipped twice: an agent spool bounded at 64 files that would have reported a
complete fleet while short hundreds of sessions, and an installed-plugin scan
capped at 256 that would have shown a wrong count on a larger machine. Emit a
census line, and surface truncation in the UI when the cap is hit.

## 9. A render that cannot see the network

The rig render seeds the plugin's state directory from a fixture before the shell
starts. That makes previews deterministic, and it also means the fetch path is
never exercised. A marketplace browser plugin shipped pointing at a host that had
begun answering 301, while refusing redirects by design. The panel sat on its
loading message for every new user for weeks. The lane stayed green throughout:
the fixture had eight entries and the live catalog had 3,638.

A user found it, diagnosed it and supplied the fix. Applying that fix left the
lane green again and the plugin still broken, because two more defects sat behind
the first. Only running it as a first-run user, empty cache and real network,
showed that.

Catch it with layer 5, and with a control that must fail.

## 10. A receipt that certifies the wrong tree

A receipt binds evidence to a tree by content fingerprint. Built from `find .`
with only `./node_modules` excluded, the fingerprint also hashed nested
dependency trees and an ignored state store whose JSON carried the exec bit. One
commit hashed 11 files in a clean export and 2,059 in a working clone, so the
gate reported a stale render receipt that was not stale. CI was green, because a
clean checkout has none of that.

The fix is to list what git treats as part of the project: tracked files plus
untracked files that are not ignored. Tracked-only is wrong in the other
direction, because a brand-new plugin has real uncommitted files that must count.
The script that writes a receipt and the gate that checks it must list files the
same way, or they disagree by construction.

## 11. A tool whose behavior changed under a pinned assumption

A response bound was passed to curl as `--max-filesize`, with a comment stating
that curl only honours it when the server sends Content-Length, so a later check
was "the real bound". That later check did not exist, and the statement stopped
being true: newer curl enforces the limit during the transfer against the decoded
body. When the payload outgrew the bound, every fetch aborted with exit 63 on a
real install and passed on a developer box with the older curl.

A comment that explains why something is safe is an assumption with no test. Pin
the behavior with a test that runs where the user runs.

