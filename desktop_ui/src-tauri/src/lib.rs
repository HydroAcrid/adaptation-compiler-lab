use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::env;
use std::io::{BufRead, BufReader, Write};
use std::process::{Child, ChildStdin, ChildStdout, Command, Stdio};
use std::sync::Mutex;
use uuid::Uuid;

const PROTOCOL_VERSION: &str = "temper-engine-protocol/v1";
const MAX_FRAME_BYTES: usize = 1_048_576;

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

    fn request(&mut self, method: &str) -> Result<EngineResponse, PublicError> {
        let request_id = Uuid::new_v4().to_string();
        let frame = json!({
            "protocol_version": PROTOCOL_VERSION,
            "request_id": request_id,
            "method": method,
            "params": {}
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
        Ok(response)
    }
}

fn engine_command() -> Result<Command, PublicError> {
    let mut command = if let Ok(binary) = env::var("TEMPER_ENGINE_BINARY") {
        Command::new(binary)
    } else if cfg!(debug_assertions) {
        let python = env::var("TEMPER_PYTHON").unwrap_or_else(|_| "python3".to_owned());
        let mut value = Command::new(python);
        value.args(["-m", "adaptation_compiler_lab.desktop.engine_main"]);
        value
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
        Command::new(current.with_file_name(name))
    };
    if let Ok(config) = env::var("TEMPER_RUNTIME_CONFIG") {
        command.arg("--config").arg(config);
    }
    if let Ok(predecessor) = env::var("TEMPER_PREDECESSOR_CONFIG") {
        command.arg("--predecessor-config").arg(predecessor);
    }
    Ok(command)
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

struct EngineState(Mutex<Option<EngineProcess>>);

fn call_engine(state: &EngineState, method: &str) -> Result<EngineResponse, PublicError> {
    let mut guard = state.0.lock().map_err(|_| unavailable())?;
    if guard.is_none() {
        *guard = Some(EngineProcess::spawn()?);
    }
    let response = guard.as_mut().ok_or_else(unavailable)?.request(method);
    if response.is_err() {
        *guard = None;
    }
    response
}

#[tauri::command]
fn engine_handshake(state: tauri::State<'_, EngineState>) -> Result<EngineResponse, PublicError> {
    call_engine(&state, "system.handshake")
}

#[tauri::command]
fn snapshot_get(state: tauri::State<'_, EngineState>) -> Result<EngineResponse, PublicError> {
    call_engine(&state, "snapshot.get")
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .manage(EngineState(Mutex::new(None)))
        .invoke_handler(tauri::generate_handler![engine_handshake, snapshot_get])
        .run(tauri::generate_context!())
        .expect("error while running Temper");
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn public_errors_do_not_include_process_or_path_details() {
        assert_eq!(unavailable().code, "engine_unavailable");
        assert_eq!(incompatible().code, "engine_incompatible");
        assert!(!unavailable().message.contains('/'));
        assert!(!unavailable().message.contains('\\'));
    }

    #[test]
    fn renderer_contract_has_no_generic_engine_command() {
        let source = include_str!("lib.rs");
        let generic_engine_command = ["fn engine_", "request("].concat();
        let generic_process_command = ["fn process_", "run("].concat();
        assert!(!source.contains(&generic_engine_command));
        assert!(!source.contains(&generic_process_command));
    }
}
