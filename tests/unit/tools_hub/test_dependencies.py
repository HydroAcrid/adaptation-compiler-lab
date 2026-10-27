from pathlib import Path

import pytest

from adaptation_compiler_lab.tools_hub.dependencies import dependencies
from adaptation_compiler_lab.tools_hub.paths import writer_lock
from tests.unit.tools_hub.test_integration import make_service, prepare, wait_job


def skill(root: Path, name: str, extra: str = "") -> None:
    directory = root / "public-fixture/skills" / name
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: Fictional supporting guidance\n---\n{extra}\n",
        encoding="utf-8",
    )


@pytest.mark.parametrize("reference", ["foreign:child", "superpowers:missing"])
def test_unknown_namespaced_requirements_are_not_silently_ignored(
    tmp_path: Path, reference: str
) -> None:
    path = tmp_path / "SKILL.md"
    path.write_text("---\nname: parent\n---\n", encoding="utf-8")
    parent = {
        "name": "parent",
        "source": "superpowers",
        "path": str(tmp_path),
        "body": f"---\nname: parent\n---\nUse the `{reference}` skill",
    }
    with pytest.raises(ValueError, match="Unresolved named skill dependency"):
        dependencies(parent, [parent])


def test_namespaced_requirement_closure_cannot_exceed_profile_budget(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    skill(
        tmp_path,
        "debugging",
        "Use the `superpowers:first-child` skill.\nUse the `superpowers:second-child` skill.",
    )
    skill(tmp_path, "first-child")
    skill(tmp_path, "second-child")
    preview = service.preview(["repo"], ["superpowers"])
    service.enable(preview["preview_id"])
    assert wait_job(service)["state"] == "complete"
    grant = service.grant(active=True)
    assert grant is not None
    with writer_lock(service.home), service.controller(grant) as hub:
        corpus = hub.get("index")["corpus"]
        with pytest.raises(ValueError, match="Complete profile exceeds its budget"):
            hub.selected(["superpowers/skills/debugging"], 2, corpus)
    assert not (tmp_path / "repo/.agents/skills/debugging/SKILL.md").exists()


def test_namespaced_dependency_requires_inspection_and_is_published_complete(
    tmp_path: Path,
) -> None:
    service = make_service(tmp_path)
    skill(tmp_path, "debugging", "Use the `superpowers:child` skill.")
    skill(tmp_path, "child")
    preview = service.preview(["repo"], ["superpowers"])
    service.enable(preview["preview_id"])
    assert wait_job(service)["state"] == "complete"
    proposal = prepare(service)
    ticket = proposal["selection_ticket"]
    with writer_lock(service.home):
        parent = service.inspect(ticket, "superpowers/skills/debugging")
        assert parent["dependencies"] == ["superpowers/skills/child"]
        with pytest.raises(ValueError, match="Inspect every selected skill"):
            service.select(
                ticket,
                "repo",
                "Fix the failing tests",
                "debugging",
                ["superpowers/skills/debugging"],
                [parent["inspection_receipt"]],
            )
        child = service.inspect(ticket, "superpowers/skills/child")
        result = service.select(
            ticket,
            "repo",
            "Fix the failing tests",
            "debugging",
            ["superpowers/skills/debugging"],
            [parent["inspection_receipt"], child["inspection_receipt"]],
        )
    assert result["status"] == "ready"
    for name in ("debugging", "child"):
        assert (tmp_path / f"repo/.agents/skills/{name}/SKILL.md").is_file()
