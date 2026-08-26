use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::env;
use std::fs::File;
use std::io::{BufRead, BufReader, Read, Write};
use std::path::Path;
use std::process::{Child, ChildStdin, ChildStdout, Command, Stdio};
use std::sync::Mutex;
use uuid::Uuid;

const PROTOCOL_VERSION: &str = "temper-engine-protocol/v1";
const MAX_FRAME_BYTES: usize = 1_048_576;
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
    _child: Child,
    stdin: ChildStdin,
    stdout: BufReader<ChildStdout>,
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
        Ok(Self {
            _child: child,
            stdin,
            stdout: BufReader::new(stdout),
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

        let mut line = String::new();
        self.stdout
            .read_line(&mut line)
            .map_err(|_| unavailable())?;
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

#[tauri::command]
fn engine_handshake(state: tauri::State<'_, EngineState>) -> Result<EngineResponse, PublicError> {
    call_engine(&state, "system.handshake", json!({}), None, None)
}

#[tauri::command]
fn snapshot_get(state: tauri::State<'_, EngineState>) -> Result<EngineResponse, PublicError> {
    call_engine(&state, "snapshot.get", json!({}), None, None)
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

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .manage(EngineState(Mutex::new(None)))
        .invoke_handler(tauri::generate_handler![
            engine_handshake,
            snapshot_get,
            profile_export_preview,
            profile_export,
            profile_import_preview,
            profile_import_stage,
            modes_list,
            mode_run_task
        ])
        .run(tauri::generate_context!())
        .expect("error while running Temper");
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;

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
}
