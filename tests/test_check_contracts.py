"""Offline tests for scripts/check-contracts.py. No network: every fetch is faked."""
import copy
import hashlib
import importlib.util
import json
import pathlib
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("check_contracts", ROOT / "scripts" / "check-contracts.py")
cc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cc)

BODY = b"verify form v1\n"
DOC = {
    "name": "Form", "kind": "document", "repository": "o/r", "ref": "main", "path": "a/form.yml",
    "pinnedCommit": "a" * 40, "sha256": hashlib.sha256(BODY).hexdigest(),
    "assumptions": ["six headings"], "consumers": ["references/x.md"],
}
REPO = {"name": "Identity", "kind": "repository", "repository": "o/r", "expectedFullName": "o/r", "assumptions": ["file here"]}
END = {"name": "Catalog", "kind": "endpoint", "url": "https://h/catalog.json", "expectStatus": 200,
       "expectBodyContains": '"plugins"', "assumptions": ["served directly"]}


def data(*entries):
    return {"schemaVersion": 1, "contracts": [copy.deepcopy(e) for e in entries]}


def fake(table):
    """table maps url -> Response, and records whether redirects were refused."""
    calls = []

    def get(url, follow_redirects=True, limit=0):
        calls.append((url, follow_redirects))
        return table.get(url, cc.Response(404, b""))
    get.calls = calls
    return get


PINNED = "https://raw.githubusercontent.com/o/r/" + "a" * 40 + "/a/form.yml"
HEAD = "https://raw.githubusercontent.com/o/r/main/a/form.yml"
COMMITS = "https://api.github.com/repos/o/r/commits?path=a/form.yml&sha=main&per_page=1"


class Validation(unittest.TestCase):
    def write(self, payload):
        path = pathlib.Path(tempfile.mkdtemp()) / "c.json"
        path.write_text(json.dumps(payload))
        return path

    def test_the_shipped_contracts_file_is_valid(self):
        loaded = cc.load(ROOT / "contracts" / "upstream-contracts.json")
        kinds = {c["kind"] for c in loaded["contracts"]}
        self.assertEqual(kinds, {"document", "repository", "endpoint"})
        for c in loaded["contracts"]:
            if c["kind"] == "document":
                self.assertNotEqual(c["pinnedCommit"], "0" * 40, c["name"] + " was never pinned")

    def test_a_pin_without_assumptions_is_rejected(self):
        bad = copy.deepcopy(DOC); bad["assumptions"] = []
        with self.assertRaisesRegex(cc.ContractError, "assumptions"):
            cc.load(self.write(data(bad)))

    def test_short_shas_traversal_and_plain_http_are_rejected(self):
        for field, value, pattern in (("pinnedCommit", "abc123", "40 character"), ("sha256", "abc", "64 hex"), ("path", "../etc/passwd", "repository-relative")):
            bad = copy.deepcopy(DOC); bad[field] = value
            with self.assertRaisesRegex(cc.ContractError, pattern):
                cc.load(self.write(data(bad)))
        bad = copy.deepcopy(END); bad["url"] = "http://h/x"
        with self.assertRaisesRegex(cc.ContractError, "https"):
            cc.load(self.write(data(bad)))

    def test_duplicate_names_are_rejected(self):
        with self.assertRaisesRegex(cc.ContractError, "duplicate"):
            cc.load(self.write(data(DOC, DOC)))


class Documents(unittest.TestCase):
    def test_unchanged_upstream_is_clean(self):
        get = fake({PINNED: cc.Response(200, BODY), HEAD: cc.Response(200, BODY)})
        self.assertEqual(cc.check(data(DOC), True, True, False, get), [])

    def test_a_changed_document_is_drift_and_carries_what_to_recheck(self):
        get = fake({PINNED: cc.Response(200, BODY), HEAD: cc.Response(200, b"verify form v2\n"),
                    COMMITS: cc.Response(200, json.dumps([{"sha": "b" * 40}]).encode())})
        found = cc.check(data(DOC), True, True, False, get)
        self.assertEqual([f["level"] for f in found], ["drift"])
        self.assertEqual(found[0]["headCommit"], "b" * 12)
        self.assertEqual(found[0]["assumptions"], ["six headings"])
        self.assertEqual(found[0]["consumers"], ["references/x.md"])
        self.assertIn("six headings", cc.report(found))

    def test_a_deleted_document_is_drift_not_silence(self):
        get = fake({PINNED: cc.Response(200, BODY)})
        found = cc.check(data(DOC), False, True, False, get)
        self.assertEqual(found[0]["level"], "drift")
        self.assertIn("moved, renamed or deleted", found[0]["message"])

    def test_a_pin_that_no_longer_hashes_is_a_broken_pin(self):
        get = fake({PINNED: cc.Response(200, b"tampered"), HEAD: cc.Response(200, BODY)})
        self.assertEqual([f["level"] for f in cc.check(data(DOC), True, False, False, get)], ["broken-pin"])

    def test_no_mode_means_no_fetch(self):
        get = fake({})
        self.assertEqual(cc.check(data(DOC, REPO, END), False, False, False, get), [])
        self.assertEqual(get.calls, [])


class Live(unittest.TestCase):
    def test_a_transferred_repository_is_reported_with_its_new_name(self):
        get = fake({"https://api.github.com/repos/o/r": cc.Response(200, json.dumps({"full_name": "neworg/r"}).encode())})
        found = cc.check(data(REPO), False, False, True, get)
        self.assertEqual(found[0]["actual"], "neworg/r")
        self.assertIn("transferred or renamed", found[0]["message"])

    def test_repository_name_comparison_ignores_case(self):
        get = fake({"https://api.github.com/repos/o/r": cc.Response(200, json.dumps({"full_name": "O/R"}).encode())})
        self.assertEqual(cc.check(data(REPO), False, False, True, get), [])

    def test_an_endpoint_that_starts_redirecting_is_reported_and_redirects_are_refused(self):
        get = fake({"https://h/catalog.json": cc.Response(301, b"", "https://new/catalog.json")})
        found = cc.check(data(END), False, False, True, get)
        self.assertEqual(found[0]["status"], 301)
        self.assertIn("https://new/catalog.json", found[0]["message"])
        self.assertEqual(get.calls, [("https://h/catalog.json", False)])

    def test_a_changed_payload_shape_is_reported(self):
        get = fake({"https://h/catalog.json": cc.Response(200, b'{"items":[]}')})
        self.assertIn("payload shape changed", cc.check(data(END), False, False, True, get)[0]["message"])

    def test_a_healthy_endpoint_is_clean(self):
        get = fake({"https://h/catalog.json": cc.Response(200, b'{"generatedAt":1,"plugins":[]}')})
        self.assertEqual(cc.check(data(END), False, False, True, get), [])


class Repin(unittest.TestCase):
    def test_repin_moves_the_pin_and_stamps_the_review_date(self):
        new = b"verify form v2\n"
        tip = "https://raw.githubusercontent.com/o/r/" + "b" * 40 + "/a/form.yml"
        get = fake({COMMITS: cc.Response(200, json.dumps([{"sha": "b" * 40}]).encode()), tip: cc.Response(200, new)})
        d = data(DOC, REPO)
        self.assertEqual(cc.repin(d, "all", get), ["Form"])
        self.assertEqual(d["contracts"][0]["pinnedCommit"], "b" * 40)
        self.assertEqual(d["contracts"][0]["sha256"], hashlib.sha256(new).hexdigest())
        self.assertIn("reviewedAt", d)

    def test_repin_refuses_when_the_tip_cannot_be_resolved(self):
        with self.assertRaisesRegex(cc.ContractError, "tip commit"):
            cc.repin(data(DOC), "Form", fake({}))


if __name__ == "__main__":
    unittest.main()
