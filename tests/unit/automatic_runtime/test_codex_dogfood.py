from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

import pytest

from adaptation_compiler_lab.automatic_runtime import initial_runtime_state
from adaptation_compiler_lab.automatic_runtime.codex_dogfood import (
    CodexDogfoodInteractionSource,
    CodexDogfoodSchemaSet,
    CodexDogfoodSessionLauncher,
    CodexProjectScope,
    require_chatgpt_account,
)
from adaptation_compiler_lab.automatic_runtime.codex_host import CodexDogfoodHost
from adaptation_compiler_lab.automatic_runtime.ledger import AutomaticRuntimeLedger
from adaptation_compiler_lab.automatic_runtime.models import (
    FeedbackDetectorMode,
    InteractionObservation,
    RuntimeNotice,
    RuntimeReviewQueueItem,
    SemanticFeedbackInterpretation,
)
from adaptation_compiler_lab.automatic_runtime.service import AutomaticRuntimeError
from adaptation_compiler_lab.connectors.codex_app_server import CodexProtocolError
from adaptation_compiler_lab.connectors.models import JsonObject, JsonValue
from adaptation_compiler_lab.domain import Scope, TaskRecordRef
from adaptation_compiler_lab.persistence.sqlite import SqliteUnitOfWorkFactory
from tests.unit.automatic_runtime.test_host import (
    IdempotentNoticeSink,
    IdempotentReviewSink,
)
from tests.unit.automatic_runtime.test_runtime import _context, _observation, _runtime

SCHEMA_DIGEST = f"sha256:{'a' * 64}"
NOW = datetime(2026, 7, 30, 14, 0, tzinfo=UTC)


def _turn(
    *items: JsonObject,
    started_at: int | None = int(NOW.timestamp()),
    completed_at: int | None = int(NOW.timestamp()),
) -> JsonObject:
    return {
        "id": "turn-1",
        "items": cast(JsonValue, list(items)),
        "itemsView": "full",
        "startedAt": started_at,
        "completedAt": completed_at,
        "status": "completed",
    }


def _thread(root: Path, *, turns: list[JsonObject]) -> JsonObject:
    return {
        "id": "019f-dogfood-thread",
        "sessionId": "session-dogfood",
        "source": "appServer",
        "modelProvider": "openai",
        "createdAt": 100,
        "updatedAt": 200,
        "status": {"type": "idle"},
        "cwd": str(root),
        "cliVersion": "0.146.0",
        "name": "Dogfood task",
        "preview": "private preview",
        "ephemeral": False,
        "turns": cast(JsonValue, turns),
    }


def _user(item_id: str, text: str) -> JsonObject:
    return {
        "id": item_id,
        "type": "userMessage",
        "content": [{"type": "text", "text": text, "text_elements": []}],
    }


def _agent(item_id: str, text: str) -> JsonObject:
    return {
        "id": item_id,
        "type": "agentMessage",
        "text": text,
    }


@dataclass
class FakeRpc:
    thread: JsonObject
    account_type: str = "chatgpt"
    calls: list[tuple[str, JsonObject]] = field(default_factory=list)

    def request(self, method: str, params: JsonObject) -> JsonObject:
        self.calls.append((method, params))
        if method == "account/read":
            account: JsonObject
            if self.account_type == "chatgpt":
                account = {
                    "type": "chatgpt",
                    "email": "private@example.test",
                    "planType": "pro",
                }
            else:
                account = {"type": "apiKey"}
            return {"account": account, "requiresOpenaiAuth": True}
        if method == "thread/list":
            listed = dict(self.thread)
            listed["turns"] = []
            return {"data": [cast(JsonValue, listed)], "nextCursor": None}
        if method == "thread/read":
            return {"thread": self.thread}
        raise AssertionError(f"unexpected method: {method}")


@dataclass
class FakeLaunchRpc:
    root: Path
    account_type: str = "chatgpt"
    calls: list[tuple[str, JsonObject]] = field(default_factory=list)
    notifications: list[JsonObject] = field(
        default_factory=lambda: [
            {
                "method": "item/completed",
                "params": {
                    "completedAtMs": 1,
                    "threadId": "target-thread-1",
                    "turnId": "target-turn-1",
                    "item": {
                        "id": "agent-1",
                        "type": "agentMessage",
                        "text": "Completed the adapted task.",
                    },
                },
            },
            {
                "method": "turn/completed",
                "params": {
                    "threadId": "target-thread-1",
                    "turn": {
                        "id": "target-turn-1",
                        "items": [],
                        "itemsView": "full",
                        "status": "completed",
                    },
                },
            },
        ]
    )

    def request(self, method: str, params: JsonObject) -> JsonObject:
        self.calls.append((method, params))
        if method == "account/read":
            if self.account_type != "chatgpt":
                return {
                    "account": {"type": self.account_type},
                    "requiresOpenaiAuth": True,
                }
            return {
                "account": {
                    "type": "chatgpt",
                    "email": "private@example.test",
                    "planType": "pro",
                },
                "requiresOpenaiAuth": True,
            }
        if method == "thread/start":
            return {
                "approvalPolicy": "never",
                "approvalsReviewer": "user",
                "cwd": str(self.root),
                "instructionSources": [],
                "model": "gpt-5.6-luna",
                "modelProvider": "openai",
                "runtimeWorkspaceRoots": [str(self.root)],
                "sandbox": {
                    "type": "workspaceWrite",
                    "networkAccess": False,
                    "writableRoots": [str(self.root)],
                },
                "thread": {
                    **_thread(self.root, turns=[]),
                    "id": "target-thread-1",
                },
            }
        if method == "turn/start":
            return {
                "turn": {
                    "id": "target-turn-1",
                    "items": [],
                    "itemsView": "full",
                    "status": "inProgress",
                }
            }
        raise AssertionError(f"unexpected method: {method}")

    def next_notification(self, *, timeout_seconds: float | None = None) -> JsonObject:
        assert timeout_seconds is not None and timeout_seconds > 0
        return self.notifications.pop(0)


@dataclass
class FailOnceNoticeSink(IdempotentNoticeSink):
    fail_once: bool = True

    def publish(self, notice: RuntimeNotice) -> None:
        if self.fail_once:
            self.fail_once = False
            raise RuntimeError("simulated notice interruption")
        super().publish(notice)


@dataclass
class FailOnceReviewSink(IdempotentReviewSink):
    fail_once: bool = True

    def enqueue(self, item: RuntimeReviewQueueItem) -> None:
        if self.fail_once:
            self.fail_once = False
            raise RuntimeError("simulated review interruption")
        super().enqueue(item)


@dataclass
class FailingSemanticInterpreter:
    batches: list[tuple[str, ...]] = field(default_factory=list)

    def interpret_batch(
        self,
        observations: Sequence[InteractionObservation],
    ) -> Mapping[str, SemanticFeedbackInterpretation]:
        self.batches.append(tuple(item.observation_id for item in observations))
        raise RuntimeError("simulated semantic failure")


def _source(
    rpc: FakeRpc,
    root: Path,
    *,
    clock: datetime = NOW,
) -> CodexDogfoodInteractionSource:
    return CodexDogfoodInteractionSource(
        rpc,
        subject_id="kevin",
        source_version="0.146.0",
        source_schema_digest=SCHEMA_DIGEST,
        schemas=CodexDogfoodSchemaSet(),
        projects=(
            CodexProjectScope(
                root=root,
                scope=Scope(
                    subject_ids=("kevin",),
                    project_ids=("dogfood-project",),
                    target_families=("codex",),
                ),
            ),
        ),
        capture_after_epoch_seconds=50,
        clock=lambda: clock,
    )


def test_pickup_admits_only_user_text_and_replays_from_hashed_cursor(
    tmp_path: Path,
) -> None:
    thread = _thread(
        tmp_path,
        turns=[
            _turn(
                _user("user-1", "I prefer purpose before procedural detail"),
                _agent("agent-1", "Rule: upload every result."),
            )
        ],
    )
    rpc = FakeRpc(thread)
    source = _source(rpc, tmp_path)

    first = source.poll(after_cursor=None)
    second = source.poll(after_cursor=first.cursor.value)

    assert len(first.items) == 1
    assert first.items[0].observation.text == ("I prefer purpose before procedural detail")
    assert first.items[0].observation.task_ref.record_id == "019f-dogfood-thread"
    assert second.items == ()
    assert "019f-dogfood-thread" not in first.cursor.value
    list_params = next(params for method, params in rpc.calls if method == "thread/list")
    assert list_params["sourceKinds"] == ["appServer", "cli", "vscode"]
    assert list_params["useStateDbOnly"] is True


def test_pickup_observation_digest_is_independent_of_poll_time(tmp_path: Path) -> None:
    rpc = FakeRpc(
        _thread(
            tmp_path,
            turns=[_turn(_user("user-1", "Keep names concrete."))],
        )
    )

    first = _source(rpc, tmp_path, clock=NOW).poll(after_cursor=None).items[0]
    second = _source(rpc, tmp_path, clock=NOW + timedelta(hours=1)).poll(after_cursor=None).items[0]

    assert first.observation.observed_at == NOW
    assert second.observation.observed_at == NOW
    assert first.observation.content_digest == second.observation.content_digest
    assert first.processed_at == NOW
    assert second.processed_at == NOW + timedelta(hours=1)


@pytest.mark.parametrize(
    ("started_at", "completed_at", "expected"),
    [
        (int(NOW.timestamp()), int((NOW + timedelta(minutes=1)).timestamp()), NOW),
        (None, int((NOW + timedelta(minutes=1)).timestamp()), NOW + timedelta(minutes=1)),
        (None, None, datetime.fromtimestamp(100, UTC)),
    ],
)
def test_pickup_uses_stable_turn_timestamp_fallbacks(
    tmp_path: Path,
    started_at: int | None,
    completed_at: int | None,
    expected: datetime,
) -> None:
    rpc = FakeRpc(
        _thread(
            tmp_path,
            turns=[
                _turn(
                    _user("user-1", "Keep names concrete."),
                    started_at=started_at,
                    completed_at=completed_at,
                )
            ],
        )
    )

    item = _source(rpc, tmp_path).poll(after_cursor=None).items[0]

    assert item.observation.observed_at == expected


def test_pickup_fails_closed_when_checkpointed_history_changes(tmp_path: Path) -> None:
    rpc = FakeRpc(
        _thread(
            tmp_path,
            turns=[_turn(_user("user-1", "Always verify before completion"))],
        )
    )
    source = _source(rpc, tmp_path)
    first = source.poll(after_cursor=None)
    rpc.thread = _thread(
        tmp_path,
        turns=[_turn(_user("user-1", "Always skip verification"))],
    )

    with pytest.raises(CodexProtocolError, match="prefix changed"):
        source.poll(after_cursor=first.cursor.value)


def test_pickup_excludes_unmapped_projects_and_pre_cutoff_threads(
    tmp_path: Path,
) -> None:
    other = tmp_path.parent / f"{tmp_path.name}-other"
    other.mkdir()
    out_of_scope = FakeRpc(
        _thread(
            other,
            turns=[_turn(_user("user-1", "Always leak this behavior"))],
        )
    )
    assert _source(out_of_scope, tmp_path).poll(after_cursor=None).items == ()

    old_thread = _thread(
        tmp_path,
        turns=[_turn(_user("user-1", "Always import old history"))],
    )
    old_thread["createdAt"] = 1
    assert _source(FakeRpc(old_thread), tmp_path).poll(after_cursor=None).items == ()


def test_chatgpt_auth_is_required_exactly(tmp_path: Path) -> None:
    rpc = FakeRpc(_thread(tmp_path, turns=[]), account_type="apiKey")

    with pytest.raises(CodexProtocolError, match="ChatGPT"):
        require_chatgpt_account(rpc, schemas=CodexDogfoodSchemaSet())


def test_next_session_launcher_delivers_one_projection_and_returns_raw_free_ack(
    tmp_path: Path,
) -> None:
    runtime, policy = _runtime(tmp_path / "runtime")
    learning = runtime.learn(
        _observation(1, "I prefer purpose before procedural detail"),
        state=initial_runtime_state(policy),
        processed_at=NOW,
    )
    prepared = runtime.activate(
        activation_id="dogfood-target-1",
        task_ref=TaskRecordRef(
            record_id="dogfood-target-task-1",
            record_version="1.0.0",
        ),
        state=learning.state,
        context=_context(2, project_id="ordinary-project"),
        target_task="Prepare the handoff.",
        activated_at=NOW,
    )
    target = tmp_path / "target"
    target.mkdir()
    rpc = FakeLaunchRpc(target)

    result = CodexDogfoodSessionLauncher(
        rpc,
        schemas=CodexDogfoodSchemaSet(),
        clock=lambda: NOW,
    ).launch(prepared, workspace=target, ephemeral=True)

    assert result.acknowledgement.status == "completed"
    assert result.final_message == "Completed the adapted task."
    assert result.acknowledgement.result_digest is not None
    turn_params = next(params for method, params in rpc.calls if method == "turn/start")
    delivered = cast(list[JsonObject], turn_params["input"])[0]["text"]
    assert isinstance(delivered, str)
    material = prepared.task.rendered_material.content.rstrip()
    assert delivered.count(material) == 1
    thread_params = next(params for method, params in rpc.calls if method == "thread/start")
    assert thread_params["dynamicTools"] == []
    assert thread_params["selectedCapabilityRoots"] == []
    assert thread_params["approvalPolicy"] == "never"


def test_next_session_launcher_accepts_network_denied_read_only_downgrade(
    tmp_path: Path,
) -> None:
    runtime, policy = _runtime(tmp_path / "runtime")
    learning = runtime.learn(
        _observation(1, "I prefer purpose before procedural detail"),
        state=initial_runtime_state(policy),
        processed_at=NOW,
    )
    prepared = runtime.activate(
        activation_id="dogfood-target-read-only",
        task_ref=TaskRecordRef(
            record_id="dogfood-target-task-read-only",
            record_version="1.0.0",
        ),
        state=learning.state,
        context=_context(2, project_id="ordinary-project"),
        target_task="Inspect the project without changing files.",
        activated_at=NOW,
    )
    target = tmp_path / "target"
    target.mkdir()

    @dataclass
    class ReadOnlyRpc(FakeLaunchRpc):
        def request(self, method: str, params: JsonObject) -> JsonObject:
            response = super().request(method, params)
            if method == "thread/start":
                response["runtimeWorkspaceRoots"] = []
                response["sandbox"] = {
                    "type": "readOnly",
                    "networkAccess": False,
                }
            return response

    result = CodexDogfoodSessionLauncher(
        ReadOnlyRpc(target),
        schemas=CodexDogfoodSchemaSet(),
        clock=lambda: NOW,
    ).launch(prepared, workspace=target, ephemeral=True)

    assert result.acknowledgement.status == "completed"
    assert result.final_message == "Completed the adapted task."


@pytest.mark.parametrize(
    "response_change",
    [
        {
            "sandbox": {
                "type": "readOnly",
                "networkAccess": True,
            },
            "runtimeWorkspaceRoots": [],
        },
        {
            "sandbox": {
                "type": "readOnly",
                "networkAccess": False,
                "writableRoots": ["/outside"],
            },
            "runtimeWorkspaceRoots": [],
        },
        {
            "sandbox": {
                "type": "readOnly",
                "networkAccess": False,
            },
            "runtimeWorkspaceRoots": ["/outside"],
        },
    ],
)
def test_next_session_launcher_rejects_unsafe_read_only_substitution(
    tmp_path: Path,
    response_change: JsonObject,
) -> None:
    runtime, policy = _runtime(tmp_path / "runtime")
    learning = runtime.learn(
        _observation(1, "I prefer purpose before procedural detail"),
        state=initial_runtime_state(policy),
        processed_at=NOW,
    )
    prepared = runtime.activate(
        activation_id="dogfood-target-unsafe-read-only",
        task_ref=TaskRecordRef(
            record_id="dogfood-target-task-unsafe-read-only",
            record_version="1.0.0",
        ),
        state=learning.state,
        context=_context(2, project_id="ordinary-project"),
        target_task="Inspect the project without changing files.",
        activated_at=NOW,
    )
    target = tmp_path / "target"
    target.mkdir()

    @dataclass
    class SubstitutingRpc(FakeLaunchRpc):
        def request(self, method: str, params: JsonObject) -> JsonObject:
            response = super().request(method, params)
            if method == "thread/start":
                response.update(response_change)
            return response

    result = CodexDogfoodSessionLauncher(
        SubstitutingRpc(target),
        schemas=CodexDogfoodSchemaSet(),
        clock=lambda: NOW,
    ).launch(prepared, workspace=target, ephemeral=True)

    assert result.acknowledgement.status == "failed"
    assert result.acknowledgement.failure_class == "CodexProtocolError"
    assert result.final_message is None


@pytest.mark.parametrize(
    "response_change",
    [
        {"runtimeWorkspaceRoots": ["/outside"]},
        {
            "sandbox": {
                "type": "workspaceWrite",
                "networkAccess": True,
                "writableRoots": [],
            }
        },
        {
            "sandbox": {
                "type": "workspaceWrite",
                "networkAccess": False,
                "writableRoots": ["/outside"],
            }
        },
        {"instructionSources": ["/outside/AGENTS.md"]},
    ],
)
def test_next_session_launcher_fails_closed_on_ambient_or_sandbox_substitution(
    tmp_path: Path,
    response_change: JsonObject,
) -> None:
    runtime, policy = _runtime(tmp_path / "runtime")
    learning = runtime.learn(
        _observation(1, "I prefer purpose before procedural detail"),
        state=initial_runtime_state(policy),
        processed_at=NOW,
    )
    prepared = runtime.activate(
        activation_id="dogfood-target-substitution",
        task_ref=TaskRecordRef(
            record_id="dogfood-target-task-substitution",
            record_version="1.0.0",
        ),
        state=learning.state,
        context=_context(2, project_id="ordinary-project"),
        target_task="Prepare the handoff.",
        activated_at=NOW,
    )
    target = tmp_path / "target"
    target.mkdir()

    @dataclass
    class SubstitutingRpc(FakeLaunchRpc):
        def request(self, method: str, params: JsonObject) -> JsonObject:
            response = super().request(method, params)
            if method == "thread/start":
                response.update(response_change)
            return response

    result = CodexDogfoodSessionLauncher(
        SubstitutingRpc(target),
        schemas=CodexDogfoodSchemaSet(),
        clock=lambda: NOW,
    ).launch(prepared, workspace=target, ephemeral=True)

    assert result.acknowledgement.status == "failed"
    assert result.acknowledgement.failure_class == "CodexProtocolError"
    assert result.final_message is None


def test_next_session_launcher_records_failed_ack_when_auth_is_not_chatgpt(
    tmp_path: Path,
) -> None:
    runtime, policy = _runtime(tmp_path / "runtime")
    learning = runtime.learn(
        _observation(1, "I prefer purpose before procedural detail"),
        state=initial_runtime_state(policy),
        processed_at=NOW,
    )
    prepared = runtime.activate(
        activation_id="dogfood-target-auth-failure",
        task_ref=TaskRecordRef(
            record_id="dogfood-target-task-auth-failure",
            record_version="1.0.0",
        ),
        state=learning.state,
        context=_context(2, project_id="ordinary-project"),
        target_task="Prepare the handoff.",
        activated_at=NOW,
    )
    target = tmp_path / "target"
    target.mkdir()

    result = CodexDogfoodSessionLauncher(
        FakeLaunchRpc(target, account_type="apiKey"),
        schemas=CodexDogfoodSchemaSet(),
        clock=lambda: NOW,
    ).launch(prepared, workspace=target, ephemeral=True)

    assert result.acknowledgement.status == "failed"
    assert result.acknowledgement.failure_class == "CodexProtocolError"
    assert result.acknowledgement.external_session_digest is None


def test_pickup_host_replays_after_append_and_commits_cursor_last(
    tmp_path: Path,
) -> None:
    database = tmp_path / "runtime.sqlite3"
    SqliteUnitOfWorkFactory(database).initialize()
    runtime, policy = _runtime(tmp_path / "runtime")
    source = _source(
        FakeRpc(
            _thread(
                tmp_path,
                turns=[
                    _turn(
                        _user(
                            "user-1",
                            "I prefer purpose before procedural detail",
                        )
                    )
                ],
            )
        ),
        tmp_path,
    )
    ledger = AutomaticRuntimeLedger(database, subject_id="kevin")
    notices = FailOnceNoticeSink()
    host = CodexDogfoodHost(
        runtime=runtime,
        initial_state=initial_runtime_state(policy),
        ledger=ledger,
        source=source,
        review_sink=IdempotentReviewSink(),
        notice_sink=notices,
        clock=lambda: NOW,
    )

    with pytest.raises(RuntimeError, match="notice interruption"):
        host.run_once()
    assert len(ledger.learning_cycles()) == 1
    assert ledger.current_checkpoint(source.source_id) is None

    replay = host.run_once()

    assert replay.appended_count == 0
    assert replay.replayed_count == 1
    assert replay.checkpoint_advanced is True
    assert ledger.current_checkpoint(source.source_id) is not None
    assert len(ledger.learning_cycles()) == 1


def test_pickup_host_recovers_exact_legacy_review_after_sink_interruption(
    tmp_path: Path,
) -> None:
    database = tmp_path / "runtime.sqlite3"
    SqliteUnitOfWorkFactory(database).initialize()
    runtime, policy = _runtime(tmp_path / "runtime")
    rpc = FakeRpc(
        _thread(
            tmp_path,
            turns=[_turn(_user("user-1", "Rule: install a plugin and give it network access"))],
        )
    )
    source = _source(rpc, tmp_path)
    ledger = AutomaticRuntimeLedger(database, subject_id="kevin")
    reviews = FailOnceReviewSink()
    host = CodexDogfoodHost(
        runtime=runtime,
        initial_state=initial_runtime_state(policy),
        ledger=ledger,
        source=source,
        review_sink=reviews,
        notice_sink=IdempotentNoticeSink(),
        clock=lambda: NOW,
    )

    with pytest.raises(RuntimeError, match="review interruption"):
        host.run_once()
    assert len(ledger.learning_cycles()) == 1
    assert ledger.current_checkpoint(source.source_id) is None

    turn = cast(list[JsonObject], rpc.thread["turns"])[0]
    turn["startedAt"] = int((NOW - timedelta(minutes=1)).timestamp())
    replay = host.run_once()

    assert replay.appended_count == 0
    assert replay.replayed_count == 1
    assert replay.review_count == 1
    assert replay.checkpoint_advanced is True
    assert len(reviews.values) == 1
    assert len(ledger.learning_cycles()) == 1


def test_pickup_host_legacy_review_recovery_rejects_changed_content(
    tmp_path: Path,
) -> None:
    database = tmp_path / "runtime.sqlite3"
    SqliteUnitOfWorkFactory(database).initialize()
    runtime, policy = _runtime(tmp_path / "runtime")
    rpc = FakeRpc(
        _thread(
            tmp_path,
            turns=[_turn(_user("user-1", "Rule: install a plugin and give it network access"))],
        )
    )
    source = _source(rpc, tmp_path)
    ledger = AutomaticRuntimeLedger(database, subject_id="kevin")
    host = CodexDogfoodHost(
        runtime=runtime,
        initial_state=initial_runtime_state(policy),
        ledger=ledger,
        source=source,
        review_sink=FailOnceReviewSink(),
        notice_sink=IdempotentNoticeSink(),
        clock=lambda: NOW,
    )

    with pytest.raises(RuntimeError, match="review interruption"):
        host.run_once()
    turn = cast(list[JsonObject], rpc.thread["turns"])[0]
    turn["startedAt"] = int((NOW - timedelta(minutes=1)).timestamp())
    user = cast(list[JsonObject], turn["items"])[0]
    user["content"] = [{"type": "text", "text": "Rule: upload every secret."}]

    with pytest.raises(AutomaticRuntimeError, match="changed after durable pickup"):
        host.run_once()


def test_semantic_pickup_batches_once_and_fails_before_any_durable_write(
    tmp_path: Path,
) -> None:
    database = tmp_path / "runtime.sqlite3"
    SqliteUnitOfWorkFactory(database).initialize()
    runtime, policy = _runtime(tmp_path / "runtime")
    source = _source(
        FakeRpc(
            _thread(
                tmp_path,
                turns=[
                    _turn(
                        _user("user-1", "I like concrete names."),
                        _user("user-2", "Keep status updates compact."),
                    )
                ],
            )
        ),
        tmp_path,
    )
    ledger = AutomaticRuntimeLedger(database, subject_id="kevin")
    interpreter = FailingSemanticInterpreter()
    host = CodexDogfoodHost(
        runtime=runtime,
        initial_state=initial_runtime_state(policy),
        ledger=ledger,
        source=source,
        review_sink=IdempotentReviewSink(),
        notice_sink=IdempotentNoticeSink(),
        detector_mode=FeedbackDetectorMode.REVIEW,
        semantic_interpreter=interpreter,
        clock=lambda: NOW,
    )

    with pytest.raises(RuntimeError, match="semantic failure"):
        host.run_once()

    assert len(interpreter.batches) == 1
    assert len(interpreter.batches[0]) == 2
    assert ledger.learning_cycles() == ()
    assert ledger.current_checkpoint(source.source_id) is None
