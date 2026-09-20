#!/usr/bin/env python3
"""Watch the upstream contracts this lane depends on, and say when they move.

Everything the omarchy-ship skill tells you about submitting a plugin is a copy of
somebody else's document, host or repository. Copies go stale silently. On
2026-09-20 alone: the marketplace repository had moved organisations three weeks
earlier and a filing guard still matched the old name; the verify request had
become a parsed issue form; one label had stopped publishing anything; and the
catalog host had begun answering 301, which left a shipped plugin unable to load
for every new user. None of that was announced. All of it was discoverable.

contracts/upstream-contracts.json pins three kinds of thing:

  document    a file in a repository, by commit and sha256, with the assumptions
              we draw from it and the local files that repeat them
  repository  the canonical owner/name a repository resolves to
  endpoint    a URL a shipped plugin or script calls, and how it must answer

Modes (combine freely; with none, the file is only validated):
  --online        every pinned document still hashes to its recorded sha256
  --check-heads   every pinned document is unchanged at the tip of its ref
  --live          repositories resolve to the expected name; endpoints answer as
                  pinned, WITHOUT following redirects
  --repin NAME    re-pin one document (or "all") to the tip of its ref, after a
                  human has re-read it and re-checked the listed assumptions

Exit: 0 clean, 2 invalid file or a pin that no longer verifies, 3 drift,
4 a repository or endpoint no longer answers as pinned. Standard library only.

The pin-and-watch design follows tcballard/build-omarchy-plugins (MIT),
contracts/upstream-contracts.json and scripts/check_contracts.py. The repository
identity and live endpoint checks are additions.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import pathlib
import re
import sys
import urllib.error
import urllib.request
from typing import Any, Callable

ROOT = pathlib.Path(__file__).resolve().parents[1]
DEFAULT_FILE = ROOT / "contracts" / "upstream-contracts.json"
UA = "omarchy-ship-contract-watch (+https://github.com/jeremylongshore/omarchy-ship)"
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
REPO_RE = re.compile(r"^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$")
KINDS = {"document", "repository", "endpoint"}


class ContractError(ValueError):
    """The contracts file itself is wrong."""


class Response:
    def __init__(self, status: int, body: bytes, location: str = "", final_url: str = "") -> None:
        self.status, self.body, self.location, self.final_url = status, body, location, final_url


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args: Any, **kwargs: Any) -> None:  # noqa: D401
        return None


def http_get(url: str, follow_redirects: bool = True, limit: int = 20_000_000) -> Response:
    """One bounded GET. GitHub hosts get the token, nothing else does."""
    headers = {"User-Agent": UA, "Accept": "*/*"}
    host = urllib.request.urlparse(url).hostname or ""
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token and host == "api.github.com":
        headers["Authorization"] = f"Bearer {token}"
        headers["X-GitHub-Api-Version"] = "2022-11-28"
    opener = urllib.request.build_opener() if follow_redirects else urllib.request.build_opener(_NoRedirect)
    request = urllib.request.Request(url, headers=headers)
    try:
        with opener.open(request, timeout=60) as reply:
            return Response(reply.status, reply.read(limit + 1)[:limit], "", reply.geturl())
    except urllib.error.HTTPError as error:
        return Response(error.code, b"", error.headers.get("Location", "") or "", url)


def load(path: pathlib.Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise ContractError(f"cannot read {path}: {error}") from error
    if not isinstance(data, dict) or data.get("schemaVersion") != 1:
        raise ContractError("schemaVersion must be 1")
    contracts = data.get("contracts")
    if not isinstance(contracts, list) or not contracts:
        raise ContractError("contracts must be a non-empty array")
    seen: set[str] = set()
    for entry in contracts:
        validate_entry(entry)
        if entry["name"] in seen:
            raise ContractError(f"duplicate contract name: {entry['name']}")
        seen.add(entry["name"])
    return data


def _text(entry: dict[str, Any], key: str) -> str:
    value = entry.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{entry.get('name', '?')}: {key} must be a non-empty string")
    return value


def validate_entry(entry: Any) -> None:
    if not isinstance(entry, dict):
        raise ContractError("each contract must be an object")
    name = _text(entry, "name")
    kind = _text(entry, "kind")
    if kind not in KINDS:
        raise ContractError(f"{name}: kind must be one of {sorted(KINDS)}")
    assumptions = entry.get("assumptions")
    if not isinstance(assumptions, list) or not assumptions or not all(isinstance(a, str) and a.strip() for a in assumptions):
        raise ContractError(f"{name}: assumptions must be a non-empty array of strings; a pin with no stated assumption cannot tell you what to re-check")
    if kind in ("document", "repository") and not REPO_RE.match(_text(entry, "repository")):
        raise ContractError(f"{name}: repository must be owner/name")
    if kind == "document":
        _text(entry, "ref")
        path = _text(entry, "path")
        if path.startswith("/") or ".." in path.split("/"):
            raise ContractError(f"{name}: path must be repository-relative")
        if not SHA_RE.match(_text(entry, "pinnedCommit")):
            raise ContractError(f"{name}: pinnedCommit must be a full 40 character sha")
        if not SHA256_RE.match(_text(entry, "sha256")):
            raise ContractError(f"{name}: sha256 must be 64 hex characters")
    elif kind == "repository":
        if not REPO_RE.match(_text(entry, "expectedFullName")):
            raise ContractError(f"{name}: expectedFullName must be owner/name")
    else:
        url = _text(entry, "url")
        if not url.startswith("https://"):
            raise ContractError(f"{name}: url must be https")
        if not isinstance(entry.get("expectStatus"), int):
            raise ContractError(f"{name}: expectStatus must be an integer")


def raw_url(entry: dict[str, Any], revision: str) -> str:
    return f"https://raw.githubusercontent.com/{entry['repository']}/{revision}/{entry['path']}"


def digest(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def latest_commit(entry: dict[str, Any], get: Callable[..., Response]) -> str:
    url = (f"https://api.github.com/repos/{entry['repository']}/commits"
           f"?path={entry['path']}&sha={entry['ref']}&per_page=1")
    reply = get(url)
    if reply.status != 200:
        return ""
    try:
        return str(json.loads(reply.body)[0]["sha"])
    except (ValueError, LookupError, TypeError):
        return ""


def check(data: dict[str, Any], online: bool, heads: bool, live: bool,
          get: Callable[..., Response] = http_get) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []

    def add(level: str, entry: dict[str, Any], message: str, **extra: Any) -> None:
        findings.append({"level": level, "name": entry["name"], "kind": entry["kind"], "message": message,
                         "assumptions": entry["assumptions"], "consumers": entry.get("consumers", []), **extra})

    for entry in data["contracts"]:
        kind = entry["kind"]
        if kind == "document":
            if online:
                reply = get(raw_url(entry, entry["pinnedCommit"]))
                if reply.status != 200:
                    add("broken-pin", entry, f"pinned document is unreachable (HTTP {reply.status})")
                elif digest(reply.body) != entry["sha256"]:
                    add("broken-pin", entry, "pinned document no longer hashes to the recorded sha256")
            if heads:
                reply = get(raw_url(entry, entry["ref"]))
                if reply.status != 200:
                    add("drift", entry, f"document is gone at the tip of {entry['ref']} (HTTP {reply.status}); it was moved, renamed or deleted")
                elif digest(reply.body) != entry["sha256"]:
                    add("drift", entry, f"document changed upstream since {entry['pinnedCommit'][:12]}",
                        headCommit=latest_commit(entry, get)[:12], headSha256=digest(reply.body))
        elif kind == "repository" and live:
            reply = get(f"https://api.github.com/repos/{entry['repository']}")
            if reply.status != 200:
                add("live", entry, f"repository lookup failed (HTTP {reply.status})")
            else:
                try:
                    actual = str(json.loads(reply.body).get("full_name", ""))
                except ValueError:
                    actual = ""
                if actual.lower() != entry["expectedFullName"].lower():
                    add("live", entry, f"repository now resolves to '{actual}', expected '{entry['expectedFullName']}'; it was transferred or renamed", actual=actual)
        elif kind == "endpoint" and live:
            # Only the head of the body is needed, and a catalog can be many megabytes.
            reply = get(entry["url"], follow_redirects=False, limit=65536)
            if reply.status != entry["expectStatus"]:
                where = f" to {reply.location}" if reply.location else ""
                add("live", entry, f"endpoint answered HTTP {reply.status}{where}, expected {entry['expectStatus']} with no redirect",
                    status=reply.status, location=reply.location)
            elif entry.get("expectBodyContains") and entry["expectBodyContains"].encode() not in reply.body:
                add("live", entry, f"response head does not contain {entry['expectBodyContains']!r}; the payload shape changed")
    return findings


def repin(data: dict[str, Any], target: str, get: Callable[..., Response] = http_get) -> list[str]:
    changed: list[str] = []
    for entry in data["contracts"]:
        if entry["kind"] != "document" or target not in ("all", entry["name"]):
            continue
        commit = latest_commit(entry, get)
        if not SHA_RE.match(commit):
            raise ContractError(f"{entry['name']}: could not resolve the tip commit for {entry['path']}")
        reply = get(raw_url(entry, commit))
        if reply.status != 200:
            raise ContractError(f"{entry['name']}: could not fetch {entry['path']} at {commit[:12]}")
        new = digest(reply.body)
        if new != entry["sha256"] or commit != entry["pinnedCommit"]:
            entry["pinnedCommit"], entry["sha256"] = commit, new
            changed.append(entry["name"])
    if changed:
        data["reviewedAt"] = datetime.date.today().isoformat()
    return changed


def report(findings: list[dict[str, Any]]) -> str:
    if not findings:
        return "contracts: clean"
    lines = [f"contracts: {len(findings)} finding(s)", ""]
    for f in findings:
        lines.append(f"[{f['level'].upper()}] {f['name']}")
        lines.append(f"  {f['message']}")
        if f.get("headCommit"):
            lines.append(f"  upstream tip commit for this path: {f['headCommit']}")
        lines.append("  re-check these assumptions:")
        lines += [f"    - {a}" for a in f["assumptions"]]
        if f["consumers"]:
            lines.append("  then update what repeats them:")
            lines += [f"    - {c}" for c in f["consumers"]]
        lines.append("")
    return "\n".join(lines).rstrip()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--file", type=pathlib.Path, default=DEFAULT_FILE)
    parser.add_argument("--online", action="store_true")
    parser.add_argument("--check-heads", action="store_true")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--repin", metavar="NAME")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        data = load(args.file)
        if args.repin:
            changed = repin(data, args.repin)
            if changed:
                args.file.write_text(json.dumps(data, indent=2) + "\n")
            print("re-pinned: " + (", ".join(changed) if changed else "nothing to change"))
            return 0
        findings = check(data, args.online, args.check_heads, args.live)
    except ContractError as error:
        print(f"contracts: INVALID: {error}", file=sys.stderr)
        return 2
    print(json.dumps(findings, indent=2) if args.json else report(findings))
    levels = {f["level"] for f in findings}
    if "broken-pin" in levels:
        return 2
    if "drift" in levels:
        return 3
    if "live" in levels:
        return 4
    return 0


if __name__ == "__main__":
    sys.exit(main())
