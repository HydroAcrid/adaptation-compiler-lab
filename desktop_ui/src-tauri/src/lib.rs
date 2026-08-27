use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::env;
use std::fs::File;
use std::io::{self, BufRead, BufReader, Read, Write};
use std::path::Path;
use std::process::{Child, ChildStdin, ChildStdout, Command, Stdio};
use std::sync::Mutex;
use std::sync::mpsc::{self, Receiver, RecvTimeoutError};
use std::thread::{self, JoinHandle};
use std::time::Duration;
use tauri::menu::{Menu, MenuItem};
use tauri::plugin::PermissionState;
use tauri::tray::TrayIconBuilder;
use tauri::{Manager, WindowEvent};
use tauri_plugin_autostart::{MacosLauncher, ManagerExt as AutostartManagerExt};
use tauri_plugin_notification::NotificationExt;
use uuid::Uuid;

const PROTOCOL_VERSION: &str = "temper-engine-protocol/v1";
const MAX_FRAME_BYTES: usize = 1_048_576;
const ENGINE_RESPONSE_TIMEOUT: Duration = Duration::from_secs(15);
const BACKGROUND_POLL_INTERVAL: Duration = Duration::from_secs(5 * 60);
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

struct EngineProcess {
    child: Child,
    stdin: ChildStdin,
    responses: Receiver<io::Result<String>>,
    reader: Option<JoinHandle<()>>,
}

impl EngineProcess {
    fn spawn() -> Result<Self, PublicError> {
        let mut command = engine_command()?;
        command
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::null());
        let mut child = command.spawn().map_err(|_| unavailable())?;
        let stdin = child.stdin.take().ok_or_else(unavailable)?;
        let stdout = child.stdout.take().ok_or_else(unavailable)?;
        let (sender, responses) = mpsc::sync_channel(1);
        let reader = thread::spawn(move || read_engine_frames(stdout, sender));
        Ok(Self {
            child,
            stdin,
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
        self.stdin.write_all(&encoded).map_err(|_| unavailable())?;
        self.stdin.write_all(b"\n").map_err(|_| unavailable())?;
        self.stdin.flush().map_err(|_| unavailable())?;

        let line = receive_engine_frame(&self.responses, ENGINE_RESPONSE_TIMEOUT)?;
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

impl Drop for EngineProcess {
    fn drop(&mut self) {
        let _ = self.child.kill();
        let _ = self.child.wait();
        let (_replacement_sender, replacement_receiver) = mpsc::sync_channel(1);
        let responses = std::mem::replace(&mut self.responses, replacement_receiver);
        drop(responses);
        if let Some(reader) = self.reader.take() {
            let _ = reader.join();
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
    Ok(command)
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
    if !matches!(polled, Ok(EngineResponse { ok: true, .. })) {
        return;
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
                app.exit(0);
            }
            _ => {}
        })
        .build(app)?;

    let (stop_sender, stop_receiver) = mpsc::channel();
    app.manage(PollScheduler(Mutex::new(Some(stop_sender))));
    let handle = app.handle().clone();
    thread::spawn(move || {
        loop {
            match stop_receiver.recv_timeout(BACKGROUND_POLL_INTERVAL) {
                Ok(()) | Err(RecvTimeoutError::Disconnected) => break,
                Err(RecvTimeoutError::Timeout) => run_background_poll(&handle),
            }
        }
    });
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
    background_enabled: bool,
    aggregate_reporting_enabled: bool,
    decision_notifications_enabled: bool,
    launch_at_login_enabled: bool,
    expected_snapshot_digest: String,
    idempotency_key: String,
) -> Result<EngineResponse, PublicError> {
    let autostart = app.autolaunch();
    let was_enabled = autostart.is_enabled().map_err(|_| unavailable())?;
    let native_result = if launch_at_login_enabled {
        autostart.enable()
    } else {
        autostart.disable()
    };
    native_result.map_err(|_| unavailable())?;
    let response = call_engine(
        &state,
        "preferences.update",
        json!({
            "background_enabled": background_enabled,
            "aggregate_reporting_enabled": aggregate_reporting_enabled,
            "decision_notifications_enabled": decision_notifications_enabled,
            "launch_at_login_enabled": launch_at_login_enabled,
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
fn setup_existing_adopt(
    state: tauri::State<'_, EngineState>,
    preview_token: String,
    expected_snapshot_digest: String,
    idempotency_key: String,
) -> Result<EngineResponse, PublicError> {
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
fn setup_initialize(
    state: tauri::State<'_, EngineState>,
    preview_token: String,
    consent_confirmed: bool,
    expected_snapshot_digest: String,
    idempotency_key: String,
) -> Result<EngineResponse, PublicError> {
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
fn profile_export_preview(
    state: tauri::State<'_, EngineState>,
) -> Result<EngineResponse, PublicError> {
    call_engine(&state, "portability.export.preview", json!({}), None, None)
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

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_autostart::init(
            MacosLauncher::LaunchAgent,
            None,
        ))
        .plugin(tauri_plugin_notification::init())
        .manage(EngineState(Mutex::new(None)))
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
            setup_existing_preview,
            setup_existing_adopt,
            setup_project_preview,
            setup_initialize,
            project_registration_preview,
            project_register,
            profile_export_preview,
            profile_export,
            profile_import_preview,
            profile_import_stage,
            modes_list,
            mode_run_task,
            task_run,
            task_apply,
            task_discard,
            diagnostics_get
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
    }

    #[test]
    fn handshake_validation_rejects_version_or_schema_drift() {
        let response = EngineResponse {
            protocol_version: PROTOCOL_VERSION.to_owned(),
            request_id: "request-1".to_owned(),
            ok: true,
            result: Some(json!({
                "engine_version": "0.3.0a1",
                "snapshot_schema_digest": format!("sha256:{}", "a".repeat(64)),
            })),
            error: None,
            snapshot_digest: None,
        };

        assert!(
            validate_handshake(&response, "0.3.0a1", &format!("sha256:{}", "a".repeat(64)),)
                .is_ok()
        );
        assert!(validate_handshake(&response, "0.3.0a2", &"a".repeat(71)).is_err());
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
    fn notification_copy_does_not_expose_behavior_or_evidence() {
        assert_eq!(
            REVIEW_NOTIFICATION_BODY,
            "A possible adaptation is ready for review."
        );
        for forbidden in ["evidence", "behavior", "prompt", "transcript", "project"] {
            assert!(!REVIEW_NOTIFICATION_BODY.to_lowercase().contains(forbidden));
        }
    }
}
