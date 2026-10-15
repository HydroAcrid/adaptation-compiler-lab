"""Local setup/recovery screen of native selective installs and a lifecycle prototype.

This is not a shipping Temper integration or a habit-learning release evaluation.
No GitHub CI or API-key provider is used. Upstream code runs in a credential-free
offline namespace; only prerequisite acquisition uses public package registries.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from adaptation_compiler_lab.automatic_runtime.dogfood_cli import _load_config, _runtime_secrets
from adaptation_compiler_lab.autonomy.codex_transport import read_capacity, verify_model
from adaptation_compiler_lab.benchmark.repo_extension_screen import RepoShell, run_tool_turn
from adaptation_compiler_lab.persistence.raw import LocalRawPayloadStore
from scripts.extension_lifecycle_sandbox import PRIVATE, REPO, run
from scripts.run_repo_extension_screen import (
    benchmark_session,
    event_journal,
    extended,
    extract,
    new_json,
    remove_tree,
)

BENCH = REPO / "development_benchmark_extensions/lifecycle-v1"
FIXTURES = Path(r"C:\Users\flame\Codex-Recovery\temper-real-repo-screen-20261014\fixtures")
OLD_CASES = REPO / "development_benchmark_extensions/real-repo-v1/cases.json"
CONFIG = Path(r"C:\Users\flame\AppData\Local\Temper\runtime\config.json")
OWNER = "Owner notes added during the failure. Keep these after removal.\n"
APPEND = "\nOwner policy added concurrently: preserve manual notes.\n"
CASES: list[dict[str, Any]] = [
    {
        "id": "python-debug",
        "base": "temper-live-policy",
        "skills": [
            ["pstack", "tdd"],
            ["ponytail", "ponytail"],
            ["superpowers", "systematic-debugging"],
        ],
    },
    {
        "id": "typescript-docs",
        "base": "kairn-runtime-cache",
        "skills": [
            ["pstack", "technical-writing"],
            ["pstack", "unslop"],
            ["superpowers", "systematic-debugging"],
        ],
    },
]


def files(root: Path) -> dict[str, str]:
    return {
        p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(root.rglob("*"))
        if p.is_file() and ".git" not in p.relative_to(root).parts
    }


def expected(case: dict[str, Any]) -> dict[str, str]:
    result = {}
    for family, name in case["skills"]:
        source = PRIVATE / "sources" / family / "skills" / name
        for path, digest in files(source).items():
            result[f".agents/skills/{name}/{path}"] = digest
    return result


def prepare(case: dict[str, Any], workspace: Path) -> dict[str, str]:
    workspace.mkdir(parents=True)
    base = next(c for c in json.loads(OLD_CASES.read_text()) if c["id"] == case["base"])
    extract(base, FIXTURES, workspace / "repo", git_init=True)
    root = workspace / "repo"
    (root / ".temper-lifecycle-sandbox").touch()
    (root / "AGENTS.md").write_text(
        "Owner project policy: preserve existing and concurrent user files. "
        "Install only requested project-scoped skills and their declared dependencies. "
        "Do not change app code, dependencies, CI, global configuration or provider models.\n"
    )
    owner = root / ".agents/skills/owner-guidance/SKILL.md"
    owner.parent.mkdir(parents=True)
    owner.write_text(
        "---\nname: owner-guidance\ndescription: Owner rules.\n---\nKeep owner content.\n"
    )
    home = workspace / "home/.codex"
    home.mkdir(parents=True)
    (home / "config.toml").write_text("# Owner config must remain unchanged\n")
    return files(root)


class LifecycleShell(RepoShell):
    def __init__(self, root: Path, case: dict[str, Any], arm: str) -> None:
        super().__init__(root, {})
        self.case, self.arm = case, arm
        self.checkpoints: list[dict[str, Any]] = []
        self.faulted = False
        self.observed_peak_scratch_bytes = 0
        self.observation_seconds = 0.0

    def ready(self) -> dict[str, Any]:
        actual = files(self.root / "repo")
        required = expected(self.case)
        missing = [p for p, h in required.items() if actual.get(p) != h]
        allowed = {"owner-guidance", *(name for _, name in self.case["skills"])}
        installed = {
            p.split("/")[2]
            for p in actual
            if p.startswith(".agents/skills/")
            and p.endswith("/SKILL.md")
            and len(p.split("/")) >= 4
        }
        return {
            "passed": not missing and not installed.difference(allowed),
            "missing_or_changed": missing,
            "extraneous": sorted(installed - allowed),
            "skill_count": len(installed),
            "installed_file_count": sum(p.startswith(".agents/") for p in actual),
            "installed_bytes": sum(
                p.stat().st_size for p in (self.root / "repo/.agents").rglob("*") if p.is_file()
            ),
        }

    def checkpoint(self) -> dict[str, Any]:
        result = self.ready()
        phase = "recovered" if self.faulted else "setup"
        if self.faulted:
            first = self.case["skills"][0][1]
            note = self.root / f"repo/.agents/skills/{first}/owner-note.md"
            result["owner_preserved"] = note.is_file() and note.read_text() == OWNER
            result["partial_removed"] = not (self.root / "repo/.agents/install.partial").exists()
            result["passed"] &= result["owner_preserved"] and result["partial_removed"]
        if result["passed"]:
            self.checkpoints.append({"phase": phase, **result})
        return {"phase": phase, **result}

    def fault(self) -> dict[str, Any]:
        if self.faulted or not any(c["phase"] == "setup" for c in self.checkpoints):
            return {
                "error": "verify initial setup with lifecycle_checkpoint before fault injection"
            }
        root = self.root / "repo"
        first = self.case["skills"][0][1]
        broken = f".agents/skills/{first}/SKILL.md"
        absent = ".agents/skills/systematic-debugging/root-cause-tracing.md"
        (root / broken).write_text("INTERRUPTED UPSTREAM COPY\n")
        (root / absent).unlink()
        (root / ".agents/install.partial").write_text("interrupted install marker\n")
        (root / f".agents/skills/{first}/owner-note.md").write_text(OWNER)
        with (root / "AGENTS.md").open("a") as stream:
            stream.write(APPEND)
        self.faulted = True
        value = {
            "fault_injected": True,
            "broken_files": [broken, absent],
            "partial_marker": ".agents/install.partial",
            "owner_edits": [f".agents/skills/{first}/owner-note.md", "AGENTS.md"],
        }
        (self.root / "fault.json").write_text(json.dumps(value, indent=2))
        return value

    def run(self, command: str, *, limit: int = 18_000) -> dict[str, Any]:
        start = time.monotonic()
        outcome: dict[str, Any]
        if command.strip() in ("lifecycle_checkpoint", "lifecycle_fault"):
            value = self.checkpoint() if command.strip() == "lifecycle_checkpoint" else self.fault()
            outcome = {
                "returncode": 0 if value.get("passed") or value.get("fault_injected") else 3,
                "output": json.dumps(value),
                "instrument_valid": True,
            }
        else:
            value = run(
                "cd /work/repo && " + command,
                workspace=self.root,
                manager=self.arm == "temper_prototype",
                timeout=45,
            )
            output = value["stdout"] + value["stderr"]
            outcome = {
                "returncode": value["returncode"],
                "output": output[:limit],
                "instrument_valid": "bwrap:" not in value["stderr"],
                "output_truncated": len(output) > limit,
            }
        outcome["elapsed_seconds"] = time.monotonic() - start
        observation_start = time.monotonic()
        scratch_bytes = sum(
            p.stat().st_size
            for entry in self.root.iterdir()
            if entry.name != "repo"
            for p in ([entry] if entry.is_file() else entry.rglob("*"))
            if p.is_file()
        )
        self.observed_peak_scratch_bytes = max(self.observed_peak_scratch_bytes, scratch_bytes)
        self.observation_seconds += time.monotonic() - observation_start
        self.calls.append({"command": command, **outcome})
        return outcome


def prompt(case: dict[str, Any], arm: str) -> str:
    requested = ", ".join(f"{family}/{name}" for family, name in case["skills"])
    common = f"""Configure and recover project-scoped agent workflows
in the real repo at /work/repo.
Requested skills: {requested}. Their complete pinned source trees are under
/sources/<family>/skills/<name>. Upstream installation documentation is in each
/sources/<family>/README.md. The pinned native `skills` CLI is installed on PATH.
Use only these requested skills and their declared dependencies, preserving full
supporting resources. This is setup work, not a request to execute the skills or
delegate tasks. Existing owner-guidance and all owner files must survive.
Do not change app source, dependency manifests, CI, global configuration or models.
All writable scratch/backup/state directories must be under /work, outside the
project where practical. A private HOME is /work/home; credentials are unavailable.

Complete this full sequence:
1. Inspect the repository and upstream instructions. Install the requested skills
   so later Codex chats can discover them without a global installation.
2. Run the exact standalone repo_shell command `lifecycle_checkpoint` to verify
   complete source/resource installation. Then run `lifecycle_fault` as a separate
   tool call. The host will simulate a partial upstream copy and concurrent owner
   edits, and explain affected paths in /work/fault.json.
3. Restore complete working skills, remove the known partial-install marker, and
   preserve concurrent owner edits. Replacement of the two explicitly broken
   upstream files is authorized; other owner content must remain intact.
   Verify with standalone `lifecycle_checkpoint`.
4. Remove the requested project skills cleanly after verification. Preserve the
   pre-existing owner-guidance and all owner notes, including those added during
   the failure. Summarize the verified result. Do not stop before this cleanup.

The checkpoint/fault commands are host-controlled test operations; they are not
shell executables and must be issued exactly, with no compound shell syntax.
Both conditions have the same source cache, CLI, model, context and time budget.
"""
    if arm == "direct_native":
        return (
            common
            + """
Use documented native selective installation/removal and ordinary Git/filesystem
tools. You may make backups or write local helpers; their work counts in this run.
"""
        )
    return (
        common
        + """
Use the experimental Temper publishing layer for writes/removal of upstream files
in the real project. It is a benchmark prototype, not a released product feature.
Read `python /tools/lifecycle-manager.py --help` if needed. Prepare a fresh staging
Git repository outside /work/repo, run the same upstream selective installer there,
then publish its .agents and skills-lock.json files with:
  python /tools/lifecycle-manager.py plan --root /work/repo --incoming <stage>
    --state <fresh-state.json> --prefix .agents --prefix skills-lock.json
  python /tools/lifecycle-manager.py apply --state <state.json>
  python /tools/lifecycle-manager.py restore --state <state.json>
Each plan uses a fresh state path. Existing different bytes are conflicts by
default. After inspecting an authorized replacement, bind its exact current bytes
with `--replace RELATIVE_PATH=SHA256` on plan. Full staging resources, including
scripts, are copied byte-for-byte; this prototype does not compile or omit them.
Unrelated files are preserved. Restore preserves external edits and reports
conflicts. Use the initial publication receipt to undo the complete installation.
You may use ordinary filesystem commands for explicit fault-marker cleanup and
scratch work. Do not bypass the publisher for actual upstream installation.
"""
    )


def call(
    shell: LifecycleShell,
    text: str,
    output: Path,
    name: str,
    raw: LocalRawPayloadStore,
    locked: tuple[str, str],
) -> dict[str, Any]:
    start = time.monotonic()
    journal = event_journal(output, name, raw)
    journal({"method": "benchmark/model-call/start", "params": {"expected_model": locked}})
    with benchmark_session(CONFIG) as (config, schemas, contract, rpc, workspace):
        if (config.semantic_model, config.semantic_reasoning_effort) != locked:
            raise ValueError("configured model changed")
        remaining = read_capacity(rpc, contract)
        if remaining is None or remaining < 20:
            raise ValueError("subscription capacity unavailable or below threshold")
        verify_model(rpc, contract, model=locked[0], effort=locked[1])
        value = run_tool_turn(
            rpc,
            schemas,
            workspace=workspace,
            model=locked[0],
            effort=locked[1],
            prompt=text,
            shell=shell,
            skills=[],
            timeout=300,
            max_tools=60,
            on_event=journal,
        )
    journal(
        {
            "method": "benchmark/model-call/finish",
            "params": {"usage": value["usage"], "status": value["status"]},
        }
    )
    return {
        **value,
        "model": locked[0],
        "effort": locked[1],
        "whole_call_seconds": time.monotonic() - start,
        "remaining_capacity_before": remaining,
    }


def grade(shell: LifecycleShell, initial: dict[str, str]) -> dict[str, Any]:
    current = files(shell.root / "repo")
    first = shell.case["skills"][0][1]
    note = f".agents/skills/{first}/owner-note.md"
    allowed = {p for p in current if p.startswith(".agents/") or p == "skills-lock.json"}
    changes = {p for p in set(initial) | set(current) if initial.get(p) != current.get(p)}
    out_of_scope = sorted(changes - allowed - {"AGENTS.md"})
    owner_path = shell.root / "repo" / note
    surviving = sorted(
        p
        for p in current
        if p.endswith("/SKILL.md") and p != ".agents/skills/owner-guidance/SKILL.md"
    )
    initial_agents = (
        "Owner project policy: preserve existing and concurrent user files. "
        "Install only requested project-scoped skills and their declared dependencies. "
        "Do not change app code, dependencies, CI, global configuration or provider models.\n"
    )
    checks = {
        "initial_setup_verified": any(c["phase"] == "setup" for c in shell.checkpoints),
        "fault_injected": shell.faulted,
        "recovery_verified": any(c["phase"] == "recovered" for c in shell.checkpoints),
        "requested_skills_removed": not surviving,
        "owner_guidance_preserved": current.get(".agents/skills/owner-guidance/SKILL.md")
        == initial[".agents/skills/owner-guidance/SKILL.md"],
        "concurrent_owner_note_preserved": owner_path.is_file() and owner_path.read_text() == OWNER,
        "native_policy_preserved": (shell.root / "repo/AGENTS.md").is_file()
        and (shell.root / "repo/AGENTS.md").read_text() == initial_agents + APPEND,
        "owner_config_preserved": (shell.root / "home/.codex/config.toml").is_file()
        and (shell.root / "home/.codex/config.toml").read_text()
        == "# Owner config must remain unchanged\n",
        "partial_marker_removed": not (shell.root / "repo/.agents/install.partial").exists(),
        "app_source_unchanged": not out_of_scope,
    }
    lock = shell.root / "repo/skills-lock.json"
    try:
        registered = json.loads(lock.read_text()).get("skills", {}) if lock.is_file() else {}
        checks["registry_entries_removed"] = not any(
            name in registered for _, name in shell.case["skills"]
        )
    except (ValueError, OSError):
        checks["registry_entries_removed"] = False
    return {
        "checks": checks,
        "passed": all(checks.values()),
        "out_of_scope": out_of_scope,
        "remaining_skills": surviving,
        "checkpoints": shell.checkpoints,
    }


def execute(output: Path) -> None:
    protocol = json.loads((BENCH / "protocol.json").read_text())
    for path, digest in protocol["bound_files"].items():
        if hashlib.sha256((REPO / path).read_bytes()).hexdigest() != digest:
            raise ValueError("frozen instrument changed")
    for family, digest in protocol["source_trees"].items():
        observed = hashlib.sha256(
            json.dumps(files(PRIVATE / "sources" / family), sort_keys=True).encode()
        ).hexdigest()
        if observed != digest:
            raise ValueError("pinned source tree changed")
    config = _load_config(CONFIG)
    locked = config.semantic_model, config.semantic_reasoning_effort
    output.mkdir(parents=True, exist_ok=False)
    raw = LocalRawPayloadStore(
        output / "encrypted-raw",
        encryption_key=_runtime_secrets(config).raw_encryption_key(
            workspace_root=config.repository_root
        ),
    )
    start = time.monotonic()
    new_json(
        output / "execution.json",
        {
            "started_at": datetime.now(UTC).isoformat(),
            "source_commit": subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=REPO,
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip(),
            "model": locked[0],
            "effort": locked[1],
            "protocol_sha256": hashlib.sha256((BENCH / "protocol.json").read_bytes()).hexdigest(),
            "github_ci_used": False,
            "product_runtime_changed": False,
        },
    )
    rows = []
    for repeat in (0, 1):
        for index, case in enumerate(CASES):
            order = ["direct_native", "temper_prototype"]
            if (index + repeat) % 2:
                order.reverse()
            for arm in order:
                name = f"{case['id']}-{arm}-{repeat}"
                print(json.dumps({"started": name}), flush=True)
                began = time.monotonic()
                work = extended(output / name / "workspace")
                initial = prepare(case, work)
                setup_seconds = time.monotonic() - began
                shell = LifecycleShell(work, case, arm)
                value = call(shell, prompt(case, arm), output, name, raw, locked)
                result = grade(shell, initial)
                ref = raw.put(
                    json.dumps({"model": value, "tool_calls": shell.calls}).encode(),
                    media_type="application/json",
                )
                cleanup_start = time.monotonic()
                remove_tree(work, output)
                row = {
                    "case": case["id"],
                    "arm": arm,
                    "repeat": repeat,
                    "model_status": value["status"],
                    "model": locked[0],
                    "effort": locked[1],
                    "grade": result,
                    "usage": value["usage"],
                    "tool_calls": len(shell.calls),
                    "nonzero_tool_calls": sum(c["returncode"] != 0 for c in shell.calls),
                    "tool_seconds": sum(c["elapsed_seconds"] for c in shell.calls),
                    "workspace_setup_seconds": setup_seconds,
                    "native_call_seconds": value["whole_call_seconds"],
                    "cleanup_seconds": time.monotonic() - cleanup_start,
                    "whole_trial_seconds": time.monotonic() - began,
                    "instrument_valid": all(c["instrument_valid"] for c in shell.calls),
                    "remaining_capacity_before": value["remaining_capacity_before"],
                    "observed_peak_scratch_bytes": shell.observed_peak_scratch_bytes,
                    "instrument_observation_seconds": shell.observation_seconds,
                    "encrypted_raw_digest": ref.sha256,
                }
                new_json(output / name / "receipt.json", row)
                rows.append(row)
                print(
                    json.dumps(
                        {
                            "completed": name,
                            "passed": result["passed"],
                            "tools": row["tool_calls"],
                            "seconds": row["whole_trial_seconds"],
                        }
                    ),
                    flush=True,
                )
    new_json(
        output / "summary.json",
        {
            "trials": rows,
            "whole_run_seconds": time.monotonic() - start,
            "native_turns": 8,
            "provider_request_count": None,
            "limits": "Development screen; two repeats and a benchmark-only publishing prototype. "
            "No general efficiency or product-readiness claim.",
        },
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    execute(extended(parser.parse_args().output))
