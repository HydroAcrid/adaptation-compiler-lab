use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::collections::BTreeMap;
use std::env;
use std::fs::File;
use std::io::{self, BufRead, BufReader, Read, Write};
#[cfg(target_os = "windows")]
use std::os::windows::process::CommandExt;
use std::path::{Path, PathBuf};
use std::process::{Child, ChildStdin, ChildStdout, Command, Stdio};
use std::sync::mpsc::{self, Receiver, RecvTimeoutError};
use std::sync::{Mutex, TryLockError};
use std::thread::{self, JoinHandle};
use std::time::{Duration, Instant};
use tauri::menu::{Menu, MenuItem};
use tauri::plugin::PermissionState;
use tauri::tray::TrayIconBuilder;
use tauri::{Manager, WindowEvent};
use tauri_plugin_autostart::{MacosLauncher, ManagerExt as AutostartManagerExt};
use tauri_plugin_notification::NotificationExt;
use uuid::Uuid;

use temper_hook_transport as hook_ipc;

const PROTOCOL_VERSION: &str = "temper-engine-protocol/v1";
const MAX_FRAME_BYTES: usize = 1_048_576;
const ENGINE_RESPONSE_TIMEOUT: Duration = Duration::from_secs(15);
const ENGINE_ANALYSIS_TIMEOUT: Duration = Duration::from_secs(240);
const ENGINE_RECOVERY_TIMEOUT: Duration = Duration::from_secs(60);
const ENGINE_HOOK_TIMEOUT: Duration = Duration::from_millis(100);
const ENGINE_SHUTDOWN_TIMEOUT: Duration = Duration::from_secs(3);
#[cfg(target_os = "windows")]
const CREATE_NO_WINDOW: u32 = 0x0800_0000;
const BACKGROUND_POLL_INTERVAL: Duration = Duration::from_secs(5 * 60);
const CLAUDE_PROJECTION_REFRESH_INTERVAL: Duration = Duration::from_secs(2 * 60);
const REVIEW_NOTIFICATION_BODY: &str = "A possible adaptation is ready for review.";
const EXPECTED_ENGINE_VERSION: &str = match option_env!("TEMPER_EXPECTED_ENGINE_VERSION") {
    Some(value) => value,
    None => "",
};
const EXPECTED_SCHEMA_DIGEST: &str = match option_env!("TEMPER_EXPECTED_SCHEMA_DIGEST") {
    Some(value) => value,
    None => "",
};
const EXPECTED_ENGINE_SHA256: &str = match option_env!("TEMPER_EXPECTED_ENGINE_SHA256") {
    Some(value) => value,
    None => "",
};

#[derive(Debug, Deserialize, Serialize)]
struct EngineError {
    code: String,
    message: String,
    #[serde(default)]
    retryable: bool,
}

#[derive(Debug, Deserialize, Serialize)]
struct EngineResponse {
    protocol_version: String,
    request_id: String,
    ok: bool,
    result: Option<Value>,
    error: Option<EngineError>,
    snapshot_digest: Option<String>,
}

#[derive(Debug, Serialize)]
struct PublicError {
    code: &'static str,
    message: &'static str,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
struct PreferencesUpdateRequest {
    background_enabled: bool,
    aggregate_reporting_enabled: bool,
    decision_notifications_enabled: bool,
    launch_at_login_enabled: bool,
}

struct EngineProcess {
    child: Child,
    stdin: Option<ChildStdin>,
    responses: Receiver<io::Result<String>>,
    reader: Option<JoinHandle<()>>,
}

impl EngineProcess {
    fn spawn() -> Result<Self, PublicError> {
        let mut command = engine_command()?;
        configure_engine_process(&mut command);
        let mut child = command.spawn().map_err(|_| unavailable())?;
        let stdin = child.stdin.take().ok_or_else(unavailable)?;
        let stdout = child.stdout.take().ok_or_else(unavailable)?;
        let (sender, responses) = mpsc::sync_channel(1);
        let reader = thread::spawn(move || read_engine_frames(stdout, sender));
        Ok(Self {
            child,
            stdin: Some(stdin),
            responses,
            reader: Some(reader),
        })
    }

    fn request(
        &mut self,
        method: &str,
        params: Value,
        expected_snapshot_digest: Option<&str>,
        idempotency_key: Option<&str>,
    ) -> Result<EngineResponse, PublicError> {
        let request_id = Uuid::new_v4().to_string();
        let frame = json!({
            "protocol_version": PROTOCOL_VERSION,
            "request_id": request_id,
            "method": method,
            "params": params,
            "expected_snapshot_digest": expected_snapshot_digest,
            "idempotency_key": idempotency_key
        });
        let encoded = serde_json::to_vec(&frame).map_err(|_| unavailable())?;
        if encoded.len() > MAX_FRAME_BYTES {
            return Err(unavailable());
        }
        let stdin = self.stdin.as_mut().ok_or_else(unavailable)?;
        stdin.write_all(&encoded).map_err(|_| unavailable())?;
        stdin.write_all(b"\n").map_err(|_| unavailable())?;
        stdin.flush().map_err(|_| unavailable())?;

        let timeout = match method {
            "instruction_environment.analyze" => ENGINE_ANALYSIS_TIMEOUT,
            "recovery.export.preview" | "recovery.export.create" | "recovery.restore" => {
                ENGINE_RECOVERY_TIMEOUT
            }
            "claude.hook.handle" => ENGINE_HOOK_TIMEOUT,
            _ => ENGINE_RESPONSE_TIMEOUT,
        };
        let line = receive_engine_frame(&self.responses, timeout)?;
        if line.is_empty() || line.len() > MAX_FRAME_BYTES {
            return Err(unavailable());
        }
        let response: EngineResponse = serde_json::from_str(&line).map_err(|_| unavailable())?;
        if response.protocol_version != PROTOCOL_VERSION || response.request_id != request_id {
            return Err(incompatible());
        }
        if method == "system.handshake" {
            validate_handshake(&response, EXPECTED_ENGINE_VERSION, EXPECTED_SCHEMA_DIGEST)?;
        }
        Ok(response)
    }
}

fn configure_engine_process(command: &mut Command) {
    command
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::null());
    #[cfg(target_os = "windows")]
    {
        // The engine is an stdio sidecar, not a user-facing terminal. Keep its
        // console subsystem intact for direct admission tests while preventing
        // Windows from creating or attaching a console for the desktop child.
        command.creation_flags(CREATE_NO_WINDOW);
    }
}

impl Drop for EngineProcess {
    fn drop(&mut self) {
        // Closing stdin lets a onefile sidecar's inner process observe EOF and
        // exit before its bootstrap parent. Killing only the bootstrap can
        // orphan the inner process while it still owns stdout, which would
        // make joining the reader block the desktop forever.
        self.stdin.take();
        let graceful = wait_for_child_exit(&mut self.child, ENGINE_SHUTDOWN_TIMEOUT);
        if !graceful {
            let _ = self.child.kill();
            let _ = self.child.wait();
        }
        let (_replacement_sender, replacement_receiver) = mpsc::sync_channel(1);
        let responses = std::mem::replace(&mut self.responses, replacement_receiver);
        drop(responses);
        if let Some(reader) = self.reader.take() {
            if graceful {
                let _ = reader.join();
            }
        }
    }
}

fn wait_for_child_exit(child: &mut Child, timeout: Duration) -> bool {
    let deadline = Instant::now() + timeout;
    loop {
        match child.try_wait() {
            Ok(Some(_)) => return true,
            Ok(None) if Instant::now() < deadline => thread::sleep(Duration::from_millis(10)),
            Ok(None) | Err(_) => return false,
        }
    }
}

fn read_engine_frames(stdout: ChildStdout, sender: mpsc::SyncSender<io::Result<String>>) {
    let mut reader = BufReader::new(stdout);
    loop {
        let mut line = String::new();
        let result = reader
            .by_ref()
            .take((MAX_FRAME_BYTES + 1) as u64)
            .read_line(&mut line)
            .and_then(|read| {
                if read == 0 {
                    Err(io::Error::new(
                        io::ErrorKind::UnexpectedEof,
                        "Temper engine closed its response stream",
                    ))
                } else {
                    Ok(line)
                }
            });
        if sender.send(result).is_err() {
            break;
        }
    }
}

fn receive_engine_frame(
    responses: &Receiver<io::Result<String>>,
    timeout: Duration,
) -> Result<String, PublicError> {
    match responses.recv_timeout(timeout) {
        Ok(Ok(line)) => Ok(line),
        Ok(Err(_)) | Err(RecvTimeoutError::Disconnected | RecvTimeoutError::Timeout) => {
            Err(unavailable())
        }
    }
}

fn engine_command() -> Result<Command, PublicError> {
    let mut command = if cfg!(debug_assertions) {
        if let Ok(binary) = env::var("TEMPER_ENGINE_BINARY") {
            Command::new(binary)
        } else {
            let python = env::var("TEMPER_PYTHON").unwrap_or_else(|_| "python3".to_owned());
            let mut value = Command::new(python);
            value.args(["-m", "adaptation_compiler_lab.desktop.engine_main"]);
            value
        }
    } else {
        let current = env::current_exe().map_err(|_| unavailable())?;
        let extension = current
            .extension()
            .and_then(|item| item.to_str())
            .unwrap_or("");
        let name = if extension.eq_ignore_ascii_case("exe") {
            "temper-engine.exe"
        } else {
            "temper-engine"
        };
        let binary = current.with_file_name(name);
        verify_engine_digest(&binary, EXPECTED_ENGINE_SHA256)?;
        Command::new(binary)
    };
    if let Ok(config) = env::var("TEMPER_RUNTIME_CONFIG") {
        command.arg("--config").arg(config);
    }
    if let Ok(predecessor) = env::var("TEMPER_PREDECESSOR_CONFIG") {
        command.arg("--predecessor-config").arg(predecessor);
    }
    if let Some(helper) = claude_hook_helper_path() {
        command.env("TEMPER_HOOK_HELPER_BINARY", helper);
    }
    if let Some(settings) = claude_settings_path() {
        command.env("TEMPER_CLAUDE_SETTINGS_PATH", settings);
    }
    Ok(command)
}

fn claude_hook_helper_path() -> Option<PathBuf> {
    if cfg!(debug_assertions)
        && let Some(path) = env::var_os("TEMPER_HOOK_HELPER_BINARY")
    {
        let candidate = PathBuf::from(path);
        return candidate.is_file().then_some(candidate);
    }
    let current = env::current_exe().ok()?;
    let name = if cfg!(target_os = "windows") {
        "temper-hook.exe"
    } else {
        "temper-hook"
    };
    let candidate = current.with_file_name(name);
    candidate.is_file().then_some(candidate)
}

fn claude_settings_path() -> Option<PathBuf> {
    let home = if cfg!(target_os = "windows") {
        env::var_os("USERPROFILE")
    } else {
        env::var_os("HOME")
    }?;
    Some(PathBuf::from(home).join(".claude").join("settings.json"))
}

fn validate_handshake(
    response: &EngineResponse,
    expected_engine_version: &str,
    expected_schema_digest: &str,
) -> Result<(), PublicError> {
    if !response.ok || expected_engine_version.is_empty() || expected_schema_digest.is_empty() {
        return Ok(());
    }
    let result = response.result.as_ref().ok_or_else(incompatible)?;
    if result.get("engine_version").and_then(Value::as_str) != Some(expected_engine_version)
        || result.get("snapshot_schema_digest").and_then(Value::as_str)
            != Some(expected_schema_digest)
    {
        return Err(incompatible());
    }
    Ok(())
}

fn verify_engine_digest(path: &Path, expected_digest: &str) -> Result<(), PublicError> {
    if expected_digest.len() != 64 {
        return Err(incompatible());
    }
    let mut source = File::open(path).map_err(|_| unavailable())?;
    let mut hasher = Sha256::new();
    let mut buffer = [0_u8; 64 * 1024];
    loop {
        let read = source.read(&mut buffer).map_err(|_| unavailable())?;
        if read == 0 {
            break;
        }
        hasher.update(&buffer[..read]);
    }
    let actual = format!("{:x}", hasher.finalize());
    if actual != expected_digest {
        return Err(incompatible());
    }
    Ok(())
}

fn unavailable() -> PublicError {
    PublicError {
        code: "engine_unavailable",
        message: "The local Temper engine is unavailable.",
    }
}

fn incompatible() -> PublicError {
    PublicError {
        code: "engine_incompatible",
        message: "The desktop and local engine versions do not match.",
    }
}

fn cancelled() -> PublicError {
    PublicError {
        code: "cancelled",
        message: "Nothing changed.",
    }
}

struct EngineState(Mutex<Option<EngineProcess>>);

struct PollScheduler(Mutex<Option<mpsc::Sender<()>>>);

struct HookIpcState(Mutex<Option<hook_ipc::HookIpcServer>>);

#[derive(Debug, PartialEq, Eq)]
struct PollEligibility {
    background_enabled: bool,
    consent_current: bool,
    pending_review_count: u64,
    aggregate_reporting_enabled: bool,
    decision_notifications_enabled: bool,
    launch_at_login_enabled: bool,
}

fn call_engine(
    state: &EngineState,
    method: &str,
    params: Value,
    expected_snapshot_digest: Option<&str>,
    idempotency_key: Option<&str>,
) -> Result<EngineResponse, PublicError> {
    let mut guard = state.0.lock().map_err(|_| unavailable())?;
    if guard.is_none() {
        *guard = Some(EngineProcess::spawn()?);
    }
    let response = guard.as_mut().ok_or_else(unavailable)?.request(
        method,
        params,
        expected_snapshot_digest,
        idempotency_key,
    );
    if response.is_err() {
        *guard = None;
    }
    response
}

fn call_running_engine(
    state: &EngineState,
    method: &str,
    params: Value,
) -> Result<EngineResponse, PublicError> {
    let mut guard = match state.0.try_lock() {
        Ok(value) => value,
        Err(TryLockError::WouldBlock | TryLockError::Poisoned(_)) => return Err(unavailable()),
    };
    let Some(engine) = guard.as_mut() else {
        return Err(unavailable());
    };
    let response = engine.request(method, params, None, None);
    if response.is_err() {
        *guard = None;
    }
    response
}

fn hook_output_from_response(response: EngineResponse) -> Option<Value> {
    if !response.ok {
        return None;
    }
    response
        .result
        .and_then(|value| value.get("output").cloned())
        .filter(|value| !value.is_null())
}

fn poll_eligibility(response: &EngineResponse) -> Option<PollEligibility> {
    if !response.ok {
        return None;
    }
    let value = response.result.as_ref()?;
    Some(PollEligibility {
        background_enabled: value.get("background_enabled")?.as_bool()?,
        consent_current: !value.get("consent")?.get("renewal_required")?.as_bool()?,
        pending_review_count: value
            .get("suggestions")?
            .as_array()?
            .len()
            .try_into()
            .ok()?,
        aggregate_reporting_enabled: value.get("aggregate_reporting_enabled")?.as_bool()?,
        decision_notifications_enabled: value.get("decision_notifications_enabled")?.as_bool()?,
        launch_at_login_enabled: value.get("launch_at_login_enabled")?.as_bool()?,
    })
}

fn show_main_window(app: &tauri::AppHandle) {
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.show();
        let _ = window.set_focus();
    }
}

fn show_review_notification(app: &tauri::AppHandle) {
    if app.notification().permission_state().ok() != Some(PermissionState::Granted) {
        return;
    }
    let _ = app
        .notification()
        .builder()
        .title("Temper")
        .body(REVIEW_NOTIFICATION_BODY)
        .show();
}

fn run_background_poll(app: &tauri::AppHandle) {
    let state = app.state::<EngineState>();
    let before = match call_engine(state.inner(), "snapshot.get", json!({}), None, None) {
        Ok(response) => response,
        Err(_) => return,
    };
    let Some(eligibility) = poll_eligibility(&before) else {
        return;
    };
    if !eligibility.background_enabled || !eligibility.consent_current {
        return;
    }
    let Some(snapshot_digest) = before.snapshot_digest.as_deref() else {
        return;
    };
    let polled = call_engine(
        state.inner(),
        "learning.poll",
        json!({}),
        Some(snapshot_digest),
        Some(&Uuid::new_v4().to_string()),
    );
    let Ok(polled) = polled else { return };
    if !polled.ok {
        return;
    }
    let current_snapshot_digest = polled
        .snapshot_digest
        .as_deref()
        .unwrap_or(snapshot_digest)
        .to_owned();
    if let Ok(environments) = call_engine(
        state.inner(),
        "instruction_environment.get",
        json!({}),
        None,
        None,
    ) && let Some((project_id, target)) = pending_instruction_analysis(&environments)
    {
        let _ = call_engine(
            state.inner(),
            "instruction_environment.analyze",
            json!({"project_id": project_id, "target": target}),
            Some(&current_snapshot_digest),
            Some(&Uuid::new_v4().to_string()),
        );
    }
    let Ok(after) = call_engine(state.inner(), "snapshot.get", json!({}), None, None) else {
        return;
    };
    let Some(after_eligibility) = poll_eligibility(&after) else {
        return;
    };
    if after_eligibility.decision_notifications_enabled
        && after_eligibility.pending_review_count > eligibility.pending_review_count
    {
        show_review_notification(app);
    }
}

fn refresh_claude_projections(app: &tauri::AppHandle) {
    let state = app.state::<EngineState>();
    let _ = call_running_engine(state.inner(), "claude.runtime.refresh", json!({}));
}

fn pending_instruction_analysis(response: &EngineResponse) -> Option<(String, String)> {
    if !response.ok {
        return None;
    }
    response
        .result
        .as_ref()?
        .get("environments")?
        .as_array()?
        .iter()
        .find(|environment| {
            environment.get("source_count").and_then(Value::as_u64) > Some(0)
                && !matches!(
                    environment
                        .get("semantic_analysis_status")
                        .and_then(Value::as_str),
                    Some("current" | "unavailable")
                )
                && environment.get("status").and_then(Value::as_str) != Some("incomplete")
        })
        .and_then(|environment| {
            Some((
                environment.get("project_id")?.as_str()?.to_owned(),
                environment.get("target")?.as_str()?.to_owned(),
            ))
        })
}

fn toggle_learning(app: &tauri::AppHandle) {
    let state = app.state::<EngineState>();
    let Ok(snapshot) = call_engine(state.inner(), "snapshot.get", json!({}), None, None) else {
        return;
    };
    let Some(eligibility) = poll_eligibility(&snapshot) else {
        return;
    };
    let Some(snapshot_digest) = snapshot.snapshot_digest.as_deref() else {
        return;
    };
    let _ = call_engine(
        state.inner(),
        "preferences.update",
        json!({
            "background_enabled": !eligibility.background_enabled,
            "aggregate_reporting_enabled": eligibility.aggregate_reporting_enabled,
            "decision_notifications_enabled": eligibility.decision_notifications_enabled,
            "launch_at_login_enabled": eligibility.launch_at_login_enabled,
        }),
        Some(snapshot_digest),
        Some(&Uuid::new_v4().to_string()),
    );
}

fn stop_scheduler(app: &tauri::AppHandle) {
    if let Some(scheduler) = app.try_state::<PollScheduler>() {
        if let Ok(mut sender) = scheduler.0.lock() {
            if let Some(stop) = sender.take() {
                let _ = stop.send(());
            }
        }
    }
}

fn stop_hook_server(app: &tauri::AppHandle) {
    if let Some(state) = app.try_state::<HookIpcState>() {
        if let Ok(mut server) = state.0.lock() {
            server.take();
        }
    }
}

fn start_hook_server(app: &tauri::App) {
    let Ok(descriptor) = hook_ipc::default_descriptor_path() else {
        return;
    };
    let handle = app.handle().clone();
    let Ok(server) = hook_ipc::HookIpcServer::start(descriptor, move |payload| {
        let state = handle.state::<EngineState>();
        call_running_engine(
            state.inner(),
            "claude.hook.handle",
            json!({"payload": payload}),
        )
        .ok()
        .and_then(hook_output_from_response)
    }) else {
        return;
    };
    let state = app.state::<HookIpcState>();
    if let Ok(mut active) = state.0.lock() {
        *active = Some(server);
    }
}

fn install_tray_and_scheduler(app: &mut tauri::App) -> Result<(), Box<dyn std::error::Error>> {
    let open_item = MenuItem::with_id(app, "open", "Open Temper", true, None::<&str>)?;
    let learning_item = MenuItem::with_id(
        app,
        "learning",
        "Pause / resume learning",
        true,
        None::<&str>,
    )?;
    let quit_item = MenuItem::with_id(app, "quit", "Quit Temper", true, None::<&str>)?;
    let menu = Menu::with_items(app, &[&open_item, &learning_item, &quit_item])?;
    TrayIconBuilder::with_id("temper-tray")
        .icon(
            app.default_window_icon()
                .cloned()
                .ok_or_else(|| std::io::Error::other("Temper tray icon is unavailable"))?,
        )
        .tooltip("Temper")
        .menu(&menu)
        .on_menu_event(|app, event| match event.id.as_ref() {
            "open" => show_main_window(app),
            "learning" => {
                let handle = app.clone();
                tauri::async_runtime::spawn_blocking(move || toggle_learning(&handle));
            }
            "quit" => {
                stop_scheduler(app);
                stop_hook_server(app);
                app.exit(0);
            }
            _ => {}
        })
        .build(app)?;

    let (stop_sender, stop_receiver) = mpsc::channel();
    app.manage(PollScheduler(Mutex::new(Some(stop_sender))));
    let handle = app.handle().clone();
    thread::spawn(move || {
        let mut next_background_poll = Instant::now() + BACKGROUND_POLL_INTERVAL;
        loop {
            match stop_receiver.recv_timeout(CLAUDE_PROJECTION_REFRESH_INTERVAL) {
                Ok(()) | Err(RecvTimeoutError::Disconnected) => break,
                Err(RecvTimeoutError::Timeout) => {
                    refresh_claude_projections(&handle);
                    if Instant::now() >= next_background_poll {
                        run_background_poll(&handle);
                        next_background_poll = Instant::now() + BACKGROUND_POLL_INTERVAL;
                    }
                }
            }
        }
    });
    start_hook_server(app);
    Ok(())
}

#[tauri::command]
fn engine_handshake(state: tauri::State<'_, EngineState>) -> Result<EngineResponse, PublicError> {
    call_engine(&state, "system.handshake", json!({}), None, None)
}

#[tauri::command]
fn snapshot_get(state: tauri::State<'_, EngineState>) -> Result<EngineResponse, PublicError> {
    call_engine(&state, "snapshot.get", json!({}), None, None)
}

#[tauri::command]
fn learning_poll(
    state: tauri::State<'_, EngineState>,
    expected_snapshot_digest: String,
    idempotency_key: String,
) -> Result<EngineResponse, PublicError> {
    call_engine(
        &state,
        "learning.poll",
        json!({}),
        Some(&expected_snapshot_digest),
        Some(&idempotency_key),
    )
}

#[tauri::command]
#[allow(clippy::too_many_arguments)]
fn review_decide(
    state: tauri::State<'_, EngineState>,
    queue_id: String,
    proposal_digest: String,
    decision: String,
    project_id: Option<String>,
    refined_scope: Option<Value>,
    expected_snapshot_digest: String,
    idempotency_key: String,
) -> Result<EngineResponse, PublicError> {
    let mut params = serde_json::Map::from_iter([
        ("queue_id".to_owned(), json!(queue_id)),
        ("proposal_digest".to_owned(), json!(proposal_digest)),
        ("decision".to_owned(), json!(decision)),
    ]);
    if let Some(project) = project_id {
        params.insert("project_id".to_owned(), json!(project));
    }
    if let Some(scope) = refined_scope {
        params.insert("refined_scope".to_owned(), scope);
    }
    call_engine(
        &state,
        "review.decide",
        Value::Object(params),
        Some(&expected_snapshot_digest),
        Some(&idempotency_key),
    )
}

#[tauri::command]
fn adaptation_revoke(
    state: tauri::State<'_, EngineState>,
    artifact_id: String,
    artifact_digest: String,
    expected_snapshot_digest: String,
    idempotency_key: String,
) -> Result<EngineResponse, PublicError> {
    call_engine(
        &state,
        "adaptation.revoke",
        json!({"artifact_id": artifact_id, "artifact_digest": artifact_digest}),
        Some(&expected_snapshot_digest),
        Some(&idempotency_key),
    )
}

#[tauri::command]
fn adaptation_undo(
    state: tauri::State<'_, EngineState>,
    notice_id: String,
    notice_digest: String,
    artifact_id: String,
    expected_snapshot_digest: String,
    idempotency_key: String,
) -> Result<EngineResponse, PublicError> {
    call_engine(
        &state,
        "adaptation.undo",
        json!({
            "notice_id": notice_id,
            "notice_digest": notice_digest,
            "artifact_id": artifact_id,
        }),
        Some(&expected_snapshot_digest),
        Some(&idempotency_key),
    )
}

#[tauri::command]
fn feedback_record(
    state: tauri::State<'_, EngineState>,
    activation_id: String,
    delivery_receipt_digest: String,
    outcome: String,
    expected_snapshot_digest: String,
    idempotency_key: String,
) -> Result<EngineResponse, PublicError> {
    call_engine(
        &state,
        "feedback.record",
        json!({
            "activation_id": activation_id,
            "delivery_receipt_digest": delivery_receipt_digest,
            "outcome": outcome,
        }),
        Some(&expected_snapshot_digest),
        Some(&idempotency_key),
    )
}

#[tauri::command]
fn consent_renew(
    state: tauri::State<'_, EngineState>,
    current_expires_at: String,
    expected_snapshot_digest: String,
    idempotency_key: String,
) -> Result<EngineResponse, PublicError> {
    call_engine(
        &state,
        "consent.renew",
        json!({"current_expires_at": current_expires_at}),
        Some(&expected_snapshot_digest),
        Some(&idempotency_key),
    )
}

#[tauri::command]
fn preferences_update(
    app: tauri::AppHandle,
    state: tauri::State<'_, EngineState>,
    preferences: PreferencesUpdateRequest,
    expected_snapshot_digest: String,
    idempotency_key: String,
) -> Result<EngineResponse, PublicError> {
    let autostart = app.autolaunch();
    let was_enabled = autostart.is_enabled().map_err(|_| unavailable())?;
    let native_result = if preferences.launch_at_login_enabled {
        autostart.enable()
    } else {
        autostart.disable()
    };
    native_result.map_err(|_| unavailable())?;
    let response = call_engine(
        &state,
        "preferences.update",
        json!({
            "background_enabled": preferences.background_enabled,
            "aggregate_reporting_enabled": preferences.aggregate_reporting_enabled,
            "decision_notifications_enabled": preferences.decision_notifications_enabled,
            "launch_at_login_enabled": preferences.launch_at_login_enabled,
        }),
        Some(&expected_snapshot_digest),
        Some(&idempotency_key),
    );
    if !matches!(&response, Ok(value) if value.ok) {
        let _ = if was_enabled {
            autostart.enable()
        } else {
            autostart.disable()
        };
    }
    response
}

#[tauri::command]
fn setup_status(state: tauri::State<'_, EngineState>) -> Result<EngineResponse, PublicError> {
    call_engine(&state, "setup.status", json!({}), None, None)
}

#[tauri::command]
fn connection_inspect(state: tauri::State<'_, EngineState>) -> Result<EngineResponse, PublicError> {
    call_engine(&state, "connection.inspect", json!({}), None, None)
}

#[tauri::command]
fn claude_connection_preview(
    state: tauri::State<'_, EngineState>,
    operation: String,
) -> Result<EngineResponse, PublicError> {
    call_engine(
        &state,
        "connection.claude.preview",
        json!({"operation": operation}),
        None,
        None,
    )
}

#[tauri::command]
async fn claude_connection_apply(
    app: tauri::AppHandle,
    preview_token: String,
    expected_before_digest: String,
    consent_confirmed: bool,
    expected_snapshot_digest: String,
    idempotency_key: String,
) -> Result<EngineResponse, PublicError> {
    tauri::async_runtime::spawn_blocking(move || {
        let state = app.state::<EngineState>();
        let response = call_engine(
            &state,
            "connection.claude.apply",
            json!({
                "preview_token": preview_token,
                "expected_before_digest": expected_before_digest,
                "consent_confirmed": consent_confirmed,
            }),
            Some(&expected_snapshot_digest),
            Some(&idempotency_key),
        )?;
        if response.ok {
            let mut guard = state.0.lock().map_err(|_| unavailable())?;
            *guard = None;
        }
        Ok(response)
    })
    .await
    .map_err(|_| unavailable())?
}

#[tauri::command]
fn target_authorization_preview(
    state: tauri::State<'_, EngineState>,
    project_id: String,
    target_family: String,
) -> Result<EngineResponse, PublicError> {
    call_engine(
        &state,
        "target.authorization.preview",
        json!({"project_id": project_id, "target_family": target_family}),
        None,
        None,
    )
}

#[tauri::command]
async fn target_authorization_apply(
    app: tauri::AppHandle,
    preview_token: String,
    selected_artifact_refs: Vec<Value>,
    confirmed: bool,
    expected_snapshot_digest: String,
    idempotency_key: String,
) -> Result<EngineResponse, PublicError> {
    tauri::async_runtime::spawn_blocking(move || {
        let state = app.state::<EngineState>();
        let response = call_engine(
            &state,
            "target.authorization.apply",
            json!({
                "preview_token": preview_token,
                "selected_artifact_refs": selected_artifact_refs,
                "confirmed": confirmed,
            }),
            Some(&expected_snapshot_digest),
            Some(&idempotency_key),
        )?;
        if response.ok {
            let mut guard = state.0.lock().map_err(|_| unavailable())?;
            *guard = None;
        }
        Ok(response)
    })
    .await
    .map_err(|_| unavailable())?
}

#[tauri::command]
fn setup_existing_preview(
    state: tauri::State<'_, EngineState>,
) -> Result<EngineResponse, PublicError> {
    let config = rfd::FileDialog::new()
        .add_filter("Temper configuration", &["json"])
        .pick_file()
        .ok_or_else(cancelled)?;
    call_engine(
        &state,
        "setup.existing.preview",
        json!({"path": config}),
        None,
        None,
    )
}

#[tauri::command]
async fn setup_existing_adopt(
    app: tauri::AppHandle,
    preview_token: String,
    expected_snapshot_digest: String,
    idempotency_key: String,
) -> Result<EngineResponse, PublicError> {
    tauri::async_runtime::spawn_blocking(move || {
        let state = app.state::<EngineState>();
        let response = call_engine(
            &state,
            "setup.existing.adopt",
            json!({"preview_token": preview_token}),
            Some(&expected_snapshot_digest),
            Some(&idempotency_key),
        )?;
        if response.ok {
            let mut guard = state.0.lock().map_err(|_| unavailable())?;
            *guard = None;
        }
        Ok(response)
    })
    .await
    .map_err(|_| unavailable())?
}

#[tauri::command]
fn setup_project_preview(
    state: tauri::State<'_, EngineState>,
) -> Result<EngineResponse, PublicError> {
    let project = rfd::FileDialog::new().pick_folder().ok_or_else(cancelled)?;
    call_engine(
        &state,
        "setup.project.preview",
        json!({"path": project}),
        None,
        None,
    )
}

#[tauri::command]
async fn setup_initialize(
    app: tauri::AppHandle,
    preview_token: String,
    consent_confirmed: bool,
    expected_snapshot_digest: String,
    idempotency_key: String,
) -> Result<EngineResponse, PublicError> {
    tauri::async_runtime::spawn_blocking(move || {
        let state = app.state::<EngineState>();
        let response = call_engine(
            &state,
            "setup.initialize",
            json!({
                "preview_token": preview_token,
                "consent_confirmed": consent_confirmed,
            }),
            Some(&expected_snapshot_digest),
            Some(&idempotency_key),
        )?;
        if response.ok {
            let mut guard = state.0.lock().map_err(|_| unavailable())?;
            *guard = None;
        }
        Ok(response)
    })
    .await
    .map_err(|_| unavailable())?
}

#[tauri::command]
fn project_registration_preview(
    state: tauri::State<'_, EngineState>,
) -> Result<EngineResponse, PublicError> {
    let project = rfd::FileDialog::new().pick_folder().ok_or_else(cancelled)?;
    call_engine(
        &state,
        "project.registration.preview",
        json!({"path": project}),
        None,
        None,
    )
}

#[tauri::command]
fn project_register(
    state: tauri::State<'_, EngineState>,
    preview_token: String,
    expected_snapshot_digest: String,
    idempotency_key: String,
) -> Result<EngineResponse, PublicError> {
    call_engine(
        &state,
        "project.register",
        json!({"preview_token": preview_token}),
        Some(&expected_snapshot_digest),
        Some(&idempotency_key),
    )
}

#[tauri::command]
fn instruction_environment_get(
    state: tauri::State<'_, EngineState>,
) -> Result<EngineResponse, PublicError> {
    call_engine(&state, "instruction_environment.get", json!({}), None, None)
}

#[tauri::command]
fn instruction_environment_refresh(
    state: tauri::State<'_, EngineState>,
    project_id: String,
    target: String,
) -> Result<EngineResponse, PublicError> {
    call_engine(
        &state,
        "instruction_environment.refresh",
        json!({"project_id": project_id, "target": target}),
        None,
        None,
    )
}

#[tauri::command]
fn instruction_environment_analyze(
    state: tauri::State<'_, EngineState>,
    project_id: String,
    target: String,
    expected_snapshot_digest: String,
    idempotency_key: String,
) -> Result<EngineResponse, PublicError> {
    call_engine(
        &state,
        "instruction_environment.analyze",
        json!({"project_id": project_id, "target": target}),
        Some(&expected_snapshot_digest),
        Some(&idempotency_key),
    )
}

#[tauri::command]
fn instruction_environment_global_preview(
    state: tauri::State<'_, EngineState>,
    target: String,
) -> Result<EngineResponse, PublicError> {
    let root = rfd::FileDialog::new().pick_folder().ok_or_else(cancelled)?;
    call_engine(
        &state,
        "instruction_environment.global.preview",
        json!({"path": root, "target": target}),
        None,
        None,
    )
}

#[tauri::command]
fn instruction_environment_global_enable(
    state: tauri::State<'_, EngineState>,
    preview_token: String,
    target: String,
    expected_snapshot_digest: String,
    idempotency_key: String,
) -> Result<EngineResponse, PublicError> {
    call_engine(
        &state,
        "instruction_environment.global.enable",
        json!({"preview_token": preview_token, "target": target}),
        Some(&expected_snapshot_digest),
        Some(&idempotency_key),
    )
}

#[tauri::command]
fn instruction_environment_global_disable(
    state: tauri::State<'_, EngineState>,
    target: String,
    expected_snapshot_digest: String,
    idempotency_key: String,
) -> Result<EngineResponse, PublicError> {
    call_engine(
        &state,
        "instruction_environment.global.disable",
        json!({"target": target}),
        Some(&expected_snapshot_digest),
        Some(&idempotency_key),
    )
}

#[tauri::command]
#[allow(clippy::too_many_arguments)]
fn instruction_environment_change_preview(
    state: tauri::State<'_, EngineState>,
    project_id: String,
    target: String,
    source_id: String,
    expected_environment_digest: String,
    instruction_text: Option<String>,
    expected_snapshot_digest: String,
) -> Result<EngineResponse, PublicError> {
    call_engine(
        &state,
        "instruction_environment.change.preview",
        json!({
            "project_id": project_id,
            "target": target,
            "source_id": source_id,
            "expected_environment_digest": expected_environment_digest,
            "instruction_text": instruction_text,
        }),
        Some(&expected_snapshot_digest),
        None,
    )
}

#[tauri::command]
fn instruction_environment_change_apply(
    state: tauri::State<'_, EngineState>,
    preview_token: String,
    target: String,
    expected_environment_digest: String,
    expected_snapshot_digest: String,
    idempotency_key: String,
) -> Result<EngineResponse, PublicError> {
    call_engine(
        &state,
        "instruction_environment.change.apply",
        json!({
            "preview_token": preview_token,
            "target": target,
            "expected_environment_digest": expected_environment_digest,
        }),
        Some(&expected_snapshot_digest),
        Some(&idempotency_key),
    )
}

#[tauri::command]
fn instruction_environment_change_rollback(
    state: tauri::State<'_, EngineState>,
    receipt_id: String,
    target: String,
    expected_environment_digest: String,
    expected_snapshot_digest: String,
    idempotency_key: String,
) -> Result<EngineResponse, PublicError> {
    call_engine(
        &state,
        "instruction_environment.change.rollback",
        json!({
            "receipt_id": receipt_id,
            "target": target,
            "expected_environment_digest": expected_environment_digest,
        }),
        Some(&expected_snapshot_digest),
        Some(&idempotency_key),
    )
}

#[tauri::command]
fn profile_export_preview(
    state: tauri::State<'_, EngineState>,
) -> Result<EngineResponse, PublicError> {
    call_engine(&state, "portability.export.preview", json!({}), None, None)
}

#[tauri::command]
fn recovery_export_preview(
    state: tauri::State<'_, EngineState>,
) -> Result<EngineResponse, PublicError> {
    call_engine(&state, "recovery.export.preview", json!({}), None, None)
}

#[tauri::command]
fn recovery_export(
    state: tauri::State<'_, EngineState>,
    preview_token: String,
    bundle_digest: String,
    passphrase: String,
    expected_snapshot_digest: String,
    idempotency_key: String,
) -> Result<EngineResponse, PublicError> {
    let mut destination = rfd::FileDialog::new()
        .set_file_name("temper-recovery.temper-recovery")
        .add_filter("Temper recovery", &["temper-recovery"])
        .save_file()
        .ok_or_else(cancelled)?;
    if destination.extension().and_then(|value| value.to_str()) != Some("temper-recovery") {
        destination.set_extension("temper-recovery");
    }
    call_engine(
        &state,
        "recovery.export.create",
        json!({
            "preview_token": preview_token,
            "bundle_digest": bundle_digest,
            "passphrase": passphrase,
            "destination": destination,
        }),
        Some(&expected_snapshot_digest),
        Some(&idempotency_key),
    )
}

#[tauri::command]
fn recovery_import_preview(
    state: tauri::State<'_, EngineState>,
    passphrase: String,
) -> Result<EngineResponse, PublicError> {
    let source = rfd::FileDialog::new()
        .add_filter("Temper recovery", &["temper-recovery"])
        .pick_file()
        .ok_or_else(cancelled)?;
    call_engine(
        &state,
        "recovery.import.preview",
        json!({"source": source, "passphrase": passphrase}),
        None,
        None,
    )
}

#[tauri::command]
fn recovery_project_select(
    state: tauri::State<'_, EngineState>,
    preview_token: String,
    project_id: String,
) -> Result<EngineResponse, PublicError> {
    let root = rfd::FileDialog::new().pick_folder().ok_or_else(cancelled)?;
    call_engine(
        &state,
        "recovery.project.select",
        json!({
            "preview_token": preview_token,
            "project_id": project_id,
            "root": root,
        }),
        None,
        None,
    )
}

#[tauri::command]
async fn recovery_restore(
    app: tauri::AppHandle,
    preview_token: String,
    bundle_digest: String,
    project_selection_tokens: BTreeMap<String, String>,
    expected_snapshot_digest: String,
    idempotency_key: String,
) -> Result<EngineResponse, PublicError> {
    tauri::async_runtime::spawn_blocking(move || {
        let state = app.state::<EngineState>();
        let response = call_engine(
            &state,
            "recovery.restore",
            json!({
                "preview_token": preview_token,
                "bundle_digest": bundle_digest,
                "project_selection_tokens": project_selection_tokens,
                "confirmed": true,
            }),
            Some(&expected_snapshot_digest),
            Some(&idempotency_key),
        )?;
        if response.ok {
            let mut guard = state.0.lock().map_err(|_| unavailable())?;
            *guard = None;
        }
        Ok(response)
    })
    .await
    .map_err(|_| unavailable())?
}

#[tauri::command]
fn profile_export(
    state: tauri::State<'_, EngineState>,
    export_token: String,
    passphrase: String,
    expected_snapshot_digest: String,
    idempotency_key: String,
) -> Result<EngineResponse, PublicError> {
    let mut destination = rfd::FileDialog::new()
        .set_file_name("temper-core.temper-profile")
        .add_filter("Temper profile", &["temper-profile"])
        .save_file()
        .ok_or_else(cancelled)?;
    if destination.extension().and_then(|value| value.to_str()) != Some("temper-profile") {
        destination.set_extension("temper-profile");
    }
    call_engine(
        &state,
        "portability.export.create",
        json!({
            "destination": destination,
            "export_token": export_token,
            "passphrase": passphrase,
        }),
        Some(&expected_snapshot_digest),
        Some(&idempotency_key),
    )
}

#[tauri::command]
fn profile_import_preview(
    state: tauri::State<'_, EngineState>,
    passphrase: String,
) -> Result<EngineResponse, PublicError> {
    let source = rfd::FileDialog::new()
        .add_filter("Temper profile", &["temper-profile"])
        .pick_file()
        .ok_or_else(cancelled)?;
    call_engine(
        &state,
        "portability.import.preview",
        json!({"passphrase": passphrase, "source": source}),
        None,
        None,
    )
}

#[tauri::command]
fn profile_import_stage(
    state: tauri::State<'_, EngineState>,
    import_token: String,
    package_digest: String,
    passphrase: String,
    expected_snapshot_digest: String,
    idempotency_key: String,
) -> Result<EngineResponse, PublicError> {
    call_engine(
        &state,
        "portability.import.stage",
        json!({
            "import_token": import_token,
            "package_digest": package_digest,
            "passphrase": passphrase,
        }),
        Some(&expected_snapshot_digest),
        Some(&idempotency_key),
    )
}

#[tauri::command]
fn package_export_preview(
    state: tauri::State<'_, EngineState>,
    package_type: String,
    mode_id: Option<String>,
) -> Result<EngineResponse, PublicError> {
    let params = match mode_id {
        Some(value) => json!({"package_type": package_type, "mode_id": value}),
        None => json!({"package_type": package_type}),
    };
    call_engine(&state, "package.export.preview", params, None, None)
}

#[tauri::command]
fn package_export(
    state: tauri::State<'_, EngineState>,
    export_token: String,
    suggested_name: String,
    expected_snapshot_digest: String,
    idempotency_key: String,
) -> Result<EngineResponse, PublicError> {
    let safe_name = if suggested_name
        .chars()
        .all(|character| character.is_ascii_alphanumeric() || "-_.".contains(character))
        && !suggested_name.starts_with('.')
        && suggested_name.len() <= 96
    {
        suggested_name
    } else {
        "temper-package.temper-pack".to_owned()
    };
    let mut destination = rfd::FileDialog::new()
        .set_file_name(safe_name)
        .add_filter("Temper package", &["temper-pack"])
        .save_file()
        .ok_or_else(cancelled)?;
    if destination.extension().and_then(|value| value.to_str()) != Some("temper-pack") {
        destination.set_extension("temper-pack");
    }
    call_engine(
        &state,
        "package.export.create",
        json!({"destination": destination, "export_token": export_token}),
        Some(&expected_snapshot_digest),
        Some(&idempotency_key),
    )
}

#[tauri::command]
fn package_import_preview(
    state: tauri::State<'_, EngineState>,
) -> Result<EngineResponse, PublicError> {
    let source = rfd::FileDialog::new()
        .add_filter("Temper package", &["temper-pack"])
        .pick_file()
        .ok_or_else(cancelled)?;
    call_engine(
        &state,
        "package.import.preview",
        json!({"source": source}),
        None,
        None,
    )
}

#[tauri::command]
fn package_import_stage(
    state: tauri::State<'_, EngineState>,
    import_token: String,
    package_digest: String,
    expected_snapshot_digest: String,
    idempotency_key: String,
) -> Result<EngineResponse, PublicError> {
    call_engine(
        &state,
        "package.import.stage",
        json!({"import_token": import_token, "package_digest": package_digest}),
        Some(&expected_snapshot_digest),
        Some(&idempotency_key),
    )
}

#[tauri::command]
fn package_review_list(
    state: tauri::State<'_, EngineState>,
) -> Result<EngineResponse, PublicError> {
    call_engine(&state, "package.review.list", json!({}), None, None)
}

#[tauri::command]
fn package_review_decide(
    state: tauri::State<'_, EngineState>,
    review_id: String,
    review_digest: String,
    decision: String,
    mapped_project_ids: Vec<String>,
    expected_snapshot_digest: String,
    idempotency_key: String,
) -> Result<EngineResponse, PublicError> {
    call_engine(
        &state,
        "package.review.decide",
        json!({
            "review_id": review_id,
            "review_digest": review_digest,
            "decision": decision,
            "mapped_project_ids": mapped_project_ids,
        }),
        Some(&expected_snapshot_digest),
        Some(&idempotency_key),
    )
}

#[tauri::command]
fn modes_list(state: tauri::State<'_, EngineState>) -> Result<EngineResponse, PublicError> {
    call_engine(&state, "mode.list", json!({}), None, None)
}

#[tauri::command]
fn mode_run_task(
    state: tauri::State<'_, EngineState>,
    mode_id: String,
    project_id: String,
    task: String,
    expected_snapshot_digest: String,
    idempotency_key: String,
) -> Result<EngineResponse, PublicError> {
    call_engine(
        &state,
        "mode.task.run",
        json!({"mode_id": mode_id, "project_id": project_id, "task": task}),
        Some(&expected_snapshot_digest),
        Some(&idempotency_key),
    )
}

#[tauri::command]
fn task_run(
    state: tauri::State<'_, EngineState>,
    project_id: String,
    task: String,
    expected_snapshot_digest: String,
    idempotency_key: String,
) -> Result<EngineResponse, PublicError> {
    call_engine(
        &state,
        "task.run",
        json!({"project_id": project_id, "task": task}),
        Some(&expected_snapshot_digest),
        Some(&idempotency_key),
    )
}

#[tauri::command]
fn task_apply(
    state: tauri::State<'_, EngineState>,
    session_id: String,
    expected_head: String,
    expected_snapshot_digest: String,
    idempotency_key: String,
) -> Result<EngineResponse, PublicError> {
    call_engine(
        &state,
        "task.apply",
        json!({"session_id": session_id, "expected_head": expected_head}),
        Some(&expected_snapshot_digest),
        Some(&idempotency_key),
    )
}

#[tauri::command]
fn task_discard(
    state: tauri::State<'_, EngineState>,
    session_id: String,
    expected_snapshot_digest: String,
    idempotency_key: String,
) -> Result<EngineResponse, PublicError> {
    call_engine(
        &state,
        "task.discard",
        json!({"session_id": session_id}),
        Some(&expected_snapshot_digest),
        Some(&idempotency_key),
    )
}

#[tauri::command]
fn diagnostics_get(state: tauri::State<'_, EngineState>) -> Result<EngineResponse, PublicError> {
    call_engine(&state, "diagnostics.get", json!({}), None, None)
}

fn notification_permission_label(state: PermissionState) -> &'static str {
    match state {
        PermissionState::Granted => "granted",
        PermissionState::Denied => "denied",
        PermissionState::Prompt => "prompt",
        PermissionState::PromptWithRationale => "prompt-with-rationale",
    }
}

#[tauri::command]
fn notification_permission(
    app: tauri::AppHandle,
    request: bool,
) -> Result<&'static str, PublicError> {
    let state = if request {
        app.notification().request_permission()
    } else {
        app.notification().permission_state()
    }
    .map_err(|_| unavailable())?;
    Ok(notification_permission_label(state))
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_autostart::init(
            MacosLauncher::LaunchAgent,
            None,
        ))
        .plugin(tauri_plugin_notification::init())
        .manage(EngineState(Mutex::new(None)))
        .manage(HookIpcState(Mutex::new(None)))
        .setup(install_tray_and_scheduler)
        .on_window_event(|window, event| {
            if let WindowEvent::CloseRequested { api, .. } = event {
                api.prevent_close();
                let _ = window.hide();
            }
        })
        .invoke_handler(tauri::generate_handler![
            engine_handshake,
            snapshot_get,
            learning_poll,
            review_decide,
            adaptation_revoke,
            adaptation_undo,
            feedback_record,
            consent_renew,
            preferences_update,
            setup_status,
            connection_inspect,
            claude_connection_preview,
            claude_connection_apply,
            target_authorization_preview,
            target_authorization_apply,
            setup_existing_preview,
            setup_existing_adopt,
            setup_project_preview,
            setup_initialize,
            project_registration_preview,
            project_register,
            instruction_environment_get,
            instruction_environment_refresh,
            instruction_environment_analyze,
            instruction_environment_global_preview,
            instruction_environment_global_enable,
            instruction_environment_global_disable,
            instruction_environment_change_preview,
            instruction_environment_change_apply,
            instruction_environment_change_rollback,
            recovery_export_preview,
            recovery_export,
            recovery_import_preview,
            recovery_project_select,
            recovery_restore,
            profile_export_preview,
            profile_export,
            profile_import_preview,
            profile_import_stage,
            package_export_preview,
            package_export,
            package_import_preview,
            package_import_stage,
            package_review_list,
            package_review_decide,
            modes_list,
            mode_run_task,
            task_run,
            task_apply,
            task_discard,
            diagnostics_get,
            notification_permission
        ])
        .run(tauri::generate_context!())
        .expect("error while running Temper");
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
    use std::time::Instant;

    #[test]
    fn public_errors_do_not_include_process_or_path_details() {
        assert_eq!(unavailable().code, "engine_unavailable");
        assert_eq!(incompatible().code, "engine_incompatible");
        assert!(!unavailable().message.contains('/'));
        assert!(!unavailable().message.contains('\\'));
        assert_eq!(cancelled().code, "cancelled");
    }

    #[test]
    fn renderer_contract_has_no_generic_engine_command() {
        let source = include_str!("lib.rs");
        let generic_engine_command = ["fn engine_", "request("].concat();
        let generic_process_command = ["fn process_", "run("].concat();
        assert!(!source.contains(&generic_engine_command));
        assert!(!source.contains(&generic_process_command));
    }

    #[test]
    fn renderer_commands_never_accept_an_arbitrary_path() {
        let source = include_str!("lib.rs");
        assert!(!source.contains(
            "fn profile_export(\n    state: tauri::State<'_, EngineState>,\n    destination"
        ));
        assert!(!source.contains(
            "fn profile_import_preview(\n    state: tauri::State<'_, EngineState>,\n    source"
        ));
        assert!(!source.contains(
            "fn package_export(\n    state: tauri::State<'_, EngineState>,\n    destination"
        ));
        assert!(!source.contains(
            "fn package_import_preview(\n    state: tauri::State<'_, EngineState>,\n    source"
        ));
    }

    #[test]
    fn app_manifest_declares_every_renderer_command() {
        let manifest = include_str!("../build.rs");
        for command in [
            "engine_handshake",
            "snapshot_get",
            "learning_poll",
            "review_decide",
            "adaptation_revoke",
            "adaptation_undo",
            "feedback_record",
            "consent_renew",
            "preferences_update",
            "setup_status",
            "connection_inspect",
            "claude_connection_preview",
            "claude_connection_apply",
            "target_authorization_preview",
            "target_authorization_apply",
            "setup_existing_preview",
            "setup_existing_adopt",
            "setup_project_preview",
            "setup_initialize",
            "project_registration_preview",
            "project_register",
            "instruction_environment_get",
            "instruction_environment_refresh",
            "instruction_environment_analyze",
            "instruction_environment_global_preview",
            "instruction_environment_global_enable",
            "instruction_environment_global_disable",
            "instruction_environment_change_preview",
            "instruction_environment_change_apply",
            "instruction_environment_change_rollback",
            "recovery_export_preview",
            "recovery_export",
            "recovery_import_preview",
            "recovery_project_select",
            "recovery_restore",
            "profile_export_preview",
            "profile_export",
            "profile_import_preview",
            "profile_import_stage",
            "package_export_preview",
            "package_export",
            "package_import_preview",
            "package_import_stage",
            "package_review_list",
            "package_review_decide",
            "modes_list",
            "mode_run_task",
            "task_run",
            "task_apply",
            "task_discard",
            "diagnostics_get",
            "notification_permission",
        ] {
            assert!(
                manifest.contains(&format!("\"{command}\"")),
                "missing command in app manifest: {command}"
            );
        }
    }

    #[test]
    fn handshake_validation_rejects_version_or_schema_drift() {
        let response = EngineResponse {
            protocol_version: PROTOCOL_VERSION.to_owned(),
            request_id: "request-1".to_owned(),
            ok: true,
            result: Some(json!({
                "engine_version": "0.3.0a2",
                "snapshot_schema_digest": format!("sha256:{}", "a".repeat(64)),
            })),
            error: None,
            snapshot_digest: None,
        };

        assert!(
            validate_handshake(&response, "0.3.0a2", &format!("sha256:{}", "a".repeat(64)),)
                .is_ok()
        );
        assert!(validate_handshake(&response, "0.3.0a3", &"a".repeat(71)).is_err());
    }

    #[test]
    fn sidecar_digest_tampering_fails_closed() {
        let directory = tempfile::tempdir().expect("temporary directory");
        let binary = directory.path().join("temper-engine");
        fs::write(&binary, b"exact engine").expect("write fixture");
        let exact = format!("{:x}", Sha256::digest(b"exact engine"));

        assert!(verify_engine_digest(&binary, &exact).is_ok());
        fs::write(&binary, b"tampered engine").expect("tamper fixture");
        assert!(verify_engine_digest(&binary, &exact).is_err());
    }

    #[test]
    fn missing_engine_response_times_out() {
        let (_sender, responses) = mpsc::sync_channel(1);
        let timeout = Duration::from_millis(5);
        let started = Instant::now();

        assert!(receive_engine_frame(&responses, timeout).is_err());
        assert!(started.elapsed() < Duration::from_secs(1));
    }

    #[test]
    fn engine_drop_closes_stdin_before_waiting_for_the_sidecar() {
        #[cfg(target_os = "windows")]
        let mut command = {
            let mut value = Command::new("cmd.exe");
            value.args(["/C", "more > NUL"]);
            value
        };
        #[cfg(not(target_os = "windows"))]
        let mut command = {
            let mut value = Command::new("sh");
            value.args(["-c", "cat >/dev/null"]);
            value
        };
        command
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::null());
        let mut child = command.spawn().expect("spawn stdin-bound fixture");
        let stdin = child.stdin.take().expect("fixture stdin");
        let stdout = child.stdout.take().expect("fixture stdout");
        let (sender, responses) = mpsc::sync_channel(1);
        let reader = thread::spawn(move || read_engine_frames(stdout, sender));
        let process = EngineProcess {
            child,
            stdin: Some(stdin),
            responses,
            reader: Some(reader),
        };

        let started = Instant::now();
        drop(process);

        assert!(started.elapsed() < Duration::from_secs(2));
    }

    #[cfg(target_os = "windows")]
    #[test]
    fn windows_engine_processes_use_the_no_console_creation_flag() {
        assert_eq!(CREATE_NO_WINDOW, 0x0800_0000);
    }

    #[test]
    fn background_polling_is_disabled_by_learning_or_expired_consent() {
        fn response(
            background_enabled: bool,
            renewal_required: bool,
            notifications_enabled: bool,
        ) -> EngineResponse {
            EngineResponse {
                protocol_version: PROTOCOL_VERSION.to_owned(),
                request_id: "snapshot".to_owned(),
                ok: true,
                result: Some(json!({
                    "background_enabled": background_enabled,
                    "aggregate_reporting_enabled": false,
                    "decision_notifications_enabled": notifications_enabled,
                    "launch_at_login_enabled": false,
                    "consent": {"renewal_required": renewal_required},
                    "suggestions": [],
                })),
                error: None,
                snapshot_digest: Some(format!("sha256:{}", "a".repeat(64))),
            }
        }

        let disabled = poll_eligibility(&response(false, false, true)).expect("eligible shape");
        let expired = poll_eligibility(&response(true, true, true)).expect("eligible shape");
        let enabled = poll_eligibility(&response(true, false, true)).expect("eligible shape");
        let quiet = poll_eligibility(&response(true, false, false)).expect("eligible shape");

        assert!(!disabled.background_enabled);
        assert!(!expired.consent_current);
        assert!(enabled.background_enabled && enabled.consent_current);
        assert!(!quiet.decision_notifications_enabled);
    }

    #[test]
    fn hook_engine_response_exposes_only_exact_output() {
        let output = json!({
            "hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "additionalContext": "Use the approved projection."
            }
        });
        let response = EngineResponse {
            protocol_version: PROTOCOL_VERSION.to_owned(),
            request_id: "hook".to_owned(),
            ok: true,
            result: Some(json!({
                "available": true,
                "output": output,
                "raw_payloads_exposed": false,
            })),
            error: None,
            snapshot_digest: None,
        };
        assert_eq!(hook_output_from_response(response), Some(output));

        let unavailable = EngineResponse {
            protocol_version: PROTOCOL_VERSION.to_owned(),
            request_id: "hook".to_owned(),
            ok: true,
            result: Some(json!({"available": false, "output": null})),
            error: None,
            snapshot_digest: None,
        };
        assert!(hook_output_from_response(unavailable).is_none());
    }

    #[test]
    fn background_analysis_selects_only_one_complete_stale_environment() {
        let response = EngineResponse {
            protocol_version: PROTOCOL_VERSION.to_owned(),
            request_id: "instructions".to_owned(),
            ok: true,
            result: Some(json!({
                "environments": [
                    {
                        "project_id": "empty",
                        "target": "codex",
                        "source_count": 0,
                        "status": "understood",
                        "semantic_analysis_status": "not_requested"
                    },
                    {
                        "project_id": "alpha",
                        "target": "codex",
                        "source_count": 1,
                        "status": "changed",
                        "semantic_analysis_status": "stale"
                    },
                    {
                        "project_id": "beta",
                        "target": "codex",
                        "source_count": 2,
                        "status": "understood",
                        "semantic_analysis_status": "not_requested"
                    }
                ]
            })),
            error: None,
            snapshot_digest: None,
        };

        assert_eq!(
            pending_instruction_analysis(&response),
            Some(("alpha".to_owned(), "codex".to_owned()))
        );
    }

    #[test]
    fn notification_copy_does_not_expose_behavior_or_evidence() {
        assert_eq!(
            REVIEW_NOTIFICATION_BODY,
            "A possible adaptation is ready for review."
        );
        for forbidden in ["evidence", "behavior", "prompt", "transcript", "project"] {
            assert!(!REVIEW_NOTIFICATION_BODY.to_lowercase().contains(forbidden));
        }
    }

    #[test]
    fn notification_permission_labels_are_stable() {
        assert_eq!(
            notification_permission_label(PermissionState::Granted),
            "granted"
        );
        assert_eq!(
            notification_permission_label(PermissionState::Denied),
            "denied"
        );
        assert_eq!(
            notification_permission_label(PermissionState::Prompt),
            "prompt"
        );
        assert_eq!(
            notification_permission_label(PermissionState::PromptWithRationale),
            "prompt-with-rationale"
        );
    }
}
