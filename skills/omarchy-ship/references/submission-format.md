# Marketplace submission and verify-request format

Two shapes go to `omacom/omarchy-plugin-marketplace`: a first-time submission,
and a verify request after an update. The repo moved to the official `omacom`
org on 2026-08-30; `HANCORE-linux/omarchy-plugin-marketplace` only redirects, so
use the `omacom` name anywhere identity matters. Both shapes are GitHub issue
forms, not free-form issues, and the bot parses the form headings:

- Submit: `https://github.com/omacom/omarchy-plugin-marketplace/issues/new?template=submit-plugin.yml`
- Verify or update: `https://github.com/omacom/omarchy-plugin-marketplace/issues/new?template=verify-plugin.yml`

Authority is the marketplace's own `SUBMISSION.md` and `VERIFICATION.md`. They
change often (last process change 2026-09-05). Re-read them before trusting this
file.

## Contents

- [Which one to file](#which-one-to-file)
- [Submission body](#submission-body)
- [Verify request body](#verify-request-body)
- [Evidence rules](#evidence-rules)
- [After filing](#after-filing)

## Which one to file

| Situation | File |
| --- | --- |
| Plugin has never been listed | `[Plugin]` submission |
| Listed, and you pushed a change | `[Verify]` request, action **Verify and publish a newer upstream commit** |
| Listed, unchanged, badge missing | `[Verify]` request, action **Verify the currently listed snapshot** |
| Listed, label reads `needs-fixes` | Reply on the existing thread; do not open a new one |

A push to a listed plugin knocks its listing to `update-unverified` until a
verify request is processed, so the verify request is not optional after a
change. That includes changes no user runs: a CI or dependency-only commit moves
HEAD off the verified SHA and drops the badge exactly the same way. Batch
governance commits with a real release where possible, because each one costs a
maintainer review.

## Submission body

```markdown
**Repository:** https://github.com/<owner>/<repo>
**Plugin ID:** <id from manifest.json>
**Kind:** <Bar widget | Panel | Overlay | Service | Suite>
**Category:** <catalog category>

<Two or three sentences: what it does and who it is for. Lead with the question
it answers, not the technology.>

### Verification

| Check | Result |
| --- | --- |
| Gate lane | <n>/<n> applicable gates, 0 blocking |
| Offline tests | <p>/<t> |
| omarchy-plugin-validate | exit 0 |
| qmllint | 0 errors |
| Loaded in a real shell | 0 QML warnings |

### Runtime

No node, python or ruby. Pure QML plus shell.
<If it reaches the network: name the hosts and the timeout.>
<If it reads files: name the paths and the bounds.>
```

## Verify request body

The first six headings are the form's own fields and must stay verbatim and in
this order, or the bot posts no validation comment. The target commit must be
the full 40-character SHA of the repository's current HEAD at filing time. A
short SHA, a tag, or an older commit is rejected, so read HEAD immediately before
filing. Everything under the `---` is free text for the maintainer.

```markdown
### Verification action

Verify and publish a newer upstream commit

### Plugin ID

<id>

### Repository URL

https://github.com/<owner>/<repo>

### Target commit

<full 40-character HEAD sha>

### Verification acknowledgment

- [x] I understand that only the exact target commit can become a verified marketplace snapshot and that verification is not a security audit.

### Standard installation acknowledgment

- [ ] I confirm that this listed root plugin supports the standard Omarchy installation path and does not require manual setup.

---

Re-verified on the target:

| Check | Result |
| --- | --- |
| Gate lane | <n>/<n>, 0 blocking |
| Offline tests | <p>/<t> |
| Rig validate + qmllint | exit 0, 0 errors |
| Loaded in a real shell | 0 QML warnings |

**Changed:** <one line per user-visible change>
```

## Evidence rules

**State the coverage fraction, not a bare pass.** `9/9 applicable gates` is
falsifiable; `all gates passed` is not, and it is exactly what the lane printed
while checking nothing.

**Never claim rig-verified for a static check.** `omarchy-plugin-validate` and
`qmllint` prove the tree parses and lints. They do not prove it loads. If the
plugin was not loaded in a running shell, do not imply that it was.

**Do not claim a check you did not run.** If the rig was unreachable, the lane's
verdict is INCONCLUSIVE and there is nothing to file yet.

**Match the diff.** Claims about what changed are checked against the commits.
A body that describes a file that is not in the diff reads as carelessness on
the one artifact a reviewer reads closely.

## After filing

Watch for these labels:

| Label | Meaning |
| --- | --- |
| `validated` | Automated checks passed |
| `needs-fixes` | A human found something; fix, push, then reply on the thread |
| `security-review-required` | Routine for anything touching the network or a subprocess |
| `plugin-update` | The bot recognised a newer-commit request |
| `approved-and-verified` | The only label that publishes, for new listings and updates alike. A maintainer sets it last, after the bot reports |
| `listed` | Live in the catalog |
| `approved-for-listing` | Legacy audit label on historical issues. Publishes nothing since 2026-08-20 |

`update-unverified` is not a label. It is the catalog field `verificationCoverage`
on the listing, and it means HEAD has moved past `listingValidatedCommit`. Read it
from `https://omarchyplugins.com/catalog.json`.

If the bot fails the request, edit the same issue to rerun it. A successful
request closes itself.

Reply on the existing thread rather than opening a new issue. A second thread
for the same plugin splits the review history.
