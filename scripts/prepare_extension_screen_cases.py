"""Author fresh fictional cases; never overwrite a prepared screen."""

from __future__ import annotations

# ruff: noqa: E501 -- Embedded fictional source/check bytes are preserved as authored.
from typing import Any

from scripts.run_extension_screen import BENCH, write_new

HEADER = """import json
passed, failed = [], []
def check(name, operation):
    try:
        operation()
    except Exception:
        failed.append(name)
    else:
        passed.append(name)
def equal(actual, expected):
    assert actual == expected
def rejects(operation):
    try:
        operation()
    except ValueError:
        return
    raise AssertionError("expected rejection")
"""
FOOTER = '\nprint(json.dumps({"passed":passed,"failed":failed}))\n'


def cases() -> list[dict[str, Any]]:
    canonical = """import re
import unicodedata
def canonical_key(tenant, name):
    if not re.fullmatch(r"[a-z][a-z0-9-]{1,15}", tenant):
        raise ValueError("invalid tenant")
    normalized = unicodedata.normalize("NFC", name.replace("\\\\", "/"))
    if normalized.startswith("/") or any(part in ("", ".", "..") for part in normalized.split("/")):
        raise ValueError("invalid member")
    return "assets/" + tenant + "/" + normalized
"""
    api = """from normalizer import canonical_key
def upload_location(tenant, name):
    return canonical_key(tenant, name)
def preview_member(tenant, name, payload):
    return {"key": tenant + "/" + name, "bytes": len(payload)}
"""
    api_oracle = api.replace('tenant + "/" + name', "canonical_key(tenant, name)")
    first = {
        "id": "archive-preview",
        "kind": "diagnostic",
        "task": "Archive preview reports a different destination from upload and accepts names upload rejects. Fix preview_member so a preview reports the same canonical storage key and payload byte count as upload. Preserve the upload API and the shared validator's behavior.",
        "project_policy": "Only api.py may change. Existing shared validation is authoritative; do not duplicate or relax it. No new dependencies, test files, configuration or public APIs. The host runs fixed checks after your response; do not claim you ran unavailable tools.",
        "files": {"normalizer.py": canonical, "api.py": api},
        "allowed_paths": ["api.py"],
        "oracle": {"api.py": api_oracle},
        "check_count": 6,
        "hidden_checks": HEADER
        + """import api, ast
check("canonical-destination",lambda:equal(api.preview_member("team","x.txt",b"abc"),{"key":api.upload_location("team","x.txt"),"bytes":3}))
check("traversal-rejected",lambda:rejects(lambda:api.preview_member("team","../private",b"a")))
check("absolute-rejected",lambda:rejects(lambda:api.preview_member("team","/private",b"a")))
check("invalid-tenant-rejected",lambda:rejects(lambda:api.preview_member("OTHER","x",b"a")))
check("unicode-and-separators",lambda:equal(api.preview_member("team","dir\\\\cafe\\u0301.txt",b"abc")["key"],api.upload_location("team","dir\\\\cafe\\u0301.txt")))
def uses_shared():
    tree=ast.parse(open("/work/api.py").read())
    assert any(isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=="canonical_key" for f in tree.body if isinstance(f,ast.FunctionDef) and f.name=="preview_member" for n in ast.walk(f))
check("shared-validator-reused",uses_shared)
"""
        + FOOTER,
    }
    registry = """class Registry:
    def __init__(self):
        self._entries = {}
        self.revision = 0
    def register(self, name):
        if name in self._entries:
            raise ValueError("duplicate")
        self._entries[name] = {"name":name}
        self.revision += 1
    def names(self):
        return tuple(self._entries)
"""
    views = """class LiveView:
    def __init__(self, registry):
        self.registry = registry
        self._items = registry.names()
    def items(self):
        return self._items
    def count(self):
        return len(self._items)
def frozen_export(view):
    return tuple(view.items())
"""
    views_oracle = """class LiveView:
    def __init__(self, registry):
        self.registry = registry
        self._items = registry.names()
        self._revision = registry.revision
    def items(self):
        if self._revision != self.registry.revision:
            self._items = self.registry.names()
            self._revision = self.registry.revision
        return self._items
    def count(self):
        return len(self.items())
def frozen_export(view):
    return tuple(view.items())
"""
    second = {
        "id": "registry-boundary",
        "kind": "diagnostic",
        "task": "Registration succeeds, but already-open views and their counts stay stale until restart. Fix this across the view's public readers. Existing exports must remain snapshots of the time they were created. Preserve duplicate-registration rejection and isolation between registries.",
        "project_policy": "Change only views.py. Keep the Registry API and immutable exported snapshots. Follow the existing revision mechanism. No new dependencies, test files or configuration. The host runs fixed checks after your response; do not claim you ran unavailable tools.",
        "files": {"registry.py": registry, "views.py": views},
        "allowed_paths": ["views.py"],
        "oracle": {"views.py": views_oracle},
        "check_count": 6,
        "hidden_checks": HEADER
        + """from registry import Registry
from views import LiveView,frozen_export
r=Registry(); r.register("a"); v=LiveView(r); frozen=frozen_export(v); r.register("b")
check("live-view-refresh",lambda:equal(v.items(),("a","b")))
check("count-refresh",lambda:equal(v.count(),2))
check("export-stays-frozen",lambda:equal(frozen,("a",)))
def repeated():
    r.register("c"); equal(v.items(),("a","b","c")); equal(v.count(),3)
check("multiple-registrations",repeated)
def duplicates():
    previous=r.revision; rejects(lambda:r.register("a")); equal(r.revision,previous); equal(v.count(),3)
check("duplicate-preserves-revision",duplicates)
def isolation():
    other=Registry(); other.register("z"); equal(LiveView(other).items(),("z",)); equal(v.items(),("a","b","c")); assert isinstance(v.items(),tuple)
check("registry-isolation",isolation)
"""
        + FOOTER,
    }
    third = {
        "id": "copy-only",
        "kind": "neutral_control",
        "task": "In docs/recovery.md replace 'Recover does not copy provider credentials.' with 'Recovery does not copy provider credentials.' Keep everything else exactly as it is.",
        "project_policy": "This is a text-only correction. Change only the requested word in docs/recovery.md. Do not add code, tests, commentary, investigations or dependencies.",
        "files": {
            "docs/recovery.md": "Recovery keeps identity.\nRecover does not copy provider credentials.\n"
        },
        "allowed_paths": ["docs/recovery.md"],
        "oracle": {
            "docs/recovery.md": "Recovery keeps identity.\nRecovery does not copy provider credentials.\n"
        },
        "check_count": 3,
        "hidden_checks": HEADER
        + """from pathlib import Path
data=Path("/work/docs/recovery.md").read_bytes()
check("requested-correction",lambda:equal(data.splitlines()[1],b"Recovery does not copy provider credentials."))
check("unrelated-line-preserved",lambda:equal(data.splitlines()[0],b"Recovery keeps identity."))
check("file-format-preserved",lambda:equal(len(data.splitlines()),2) or equal(data[-1:],b"\\n"))
"""
        + FOOTER,
    }
    return [first, second, third]


if __name__ == "__main__":
    write_new(BENCH / "cases.json", cases())
