import shutil
from pathlib import Path

from scripts.run_persistent_hub_screen import completion_proof, profile_check


def test_zero_exit_without_completed_assertions_is_not_success() -> None:
    assert not completion_proof({"returncode": 0, "stdout": ""})
    assert not completion_proof({"returncode": 1, "stdout": '{"checks":22,"passed":true}'})
    assert completion_proof({"returncode": 0, "stdout": '{"checks":22,"passed":true}'})


def test_independent_resource_check_detects_partial_native_install(tmp_path: Path) -> None:
    source = tmp_path / "sources/example/skills/example"
    source.mkdir(parents=True)
    (source / "SKILL.md").write_text(
        "---\nname: example\ndescription: Example task.\n---\nUse the reference.\n"
    )
    (source / "reference.md").write_text("Complete supporting material.")
    target = tmp_path / "kairn/.agents/skills/example"
    shutil.copytree(source, target)
    assert profile_check(tmp_path, "kairn")["passed"]
    (target / "reference.md").unlink()
    assert not profile_check(tmp_path, "kairn")["passed"]
    (target / "reference.md").write_bytes((source / "reference.md").read_bytes())
    assert profile_check(tmp_path, "kairn")["passed"]


def test_independent_eligibility_check_detects_explicit_only_profile(tmp_path: Path) -> None:
    source = tmp_path / "sources/example/skills/example"
    source.mkdir(parents=True)
    (source / "SKILL.md").write_text(
        "---\nname: example\ndescription: Example.\ndisable-model-invocation: true\n"
        "---\nManual only.\n"
    )
    shutil.copytree(source, tmp_path / "kairn/.agents/skills/example")
    assert not profile_check(tmp_path, "kairn")["passed"]
