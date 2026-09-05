//! Private local transport used by Claude Code's Temper hook helper and desktop shell.

use interprocess::local_socket::{
    GenericFilePath, GenericNamespaced, Listener, ListenerNonblockingMode, ListenerOptions, Stream,
    prelude::*,
};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::fs::{self, OpenOptions};
use std::io::{self, Read, Write};
use std::path::{Path, PathBuf};
use std::sync::Arc;
use std::sync::mpsc::{self, Receiver, RecvTimeoutError, Sender};
use std::thread::{self, JoinHandle};
use std::time::{Duration, Instant};
use uuid::Uuid;

const IPC_PROTOCOL_VERSION: &str = "temper-hook-ipc/v1";
const MAX_DESCRIPTOR_BYTES: u64 = 16 * 1024;
const MAX_HOOK_FRAME_BYTES: usize = 1_048_576;
const SOCKET_TIMEOUT: Duration = Duration::from_millis(125);
const ACCEPT_POLL_INTERVAL: Duration = Duration::from_millis(5);

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct HookEndpointDescriptorV1 {
    pub protocol_version: String,
    pub transport: HookTransport,
    pub endpoint: String,
    pub auth_token: String,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum HookTransport {
    WindowsNamedPipe,
    UnixDomainSocket,
}

#[derive(Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct HookIpcRequestV1 {
    protocol_version: String,
    auth_token: String,
    payload: Value,
}

#[derive(Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct HookIpcResponseV1 {
    protocol_version: String,
    output: Option<Value>,
}

type HookHandler = dyn Fn(Value) -> Option<Value> + Send + Sync + 'static;

/// Owns one randomized local endpoint and removes its descriptor on shutdown.
pub struct HookIpcServer {
    stop: Option<Sender<()>>,
    thread: Option<JoinHandle<()>>,
    descriptor_path: PathBuf,
    descriptor: HookEndpointDescriptorV1,
}

impl HookIpcServer {
    pub fn start(
        descriptor_path: PathBuf,
        handler: impl Fn(Value) -> Option<Value> + Send + Sync + 'static,
    ) -> io::Result<Self> {
        let descriptor = new_descriptor(&descriptor_path)?;
        let listener = create_listener(&descriptor)?;
        listener.set_nonblocking(ListenerNonblockingMode::Accept)?;
        persist_descriptor(&descriptor_path, &descriptor)?;
        let (stop_sender, stop_receiver) = mpsc::channel();
        let handler = Arc::new(handler);
        let thread_descriptor_path = descriptor_path.clone();
        let thread_descriptor = descriptor.clone();
        let server_descriptor = descriptor.clone();
        let thread = thread::spawn(move || {
            serve(listener, descriptor, handler, stop_receiver);
            remove_owned_descriptor(&thread_descriptor_path, &thread_descriptor);
        });
        Ok(Self {
            stop: Some(stop_sender),
            thread: Some(thread),
            descriptor_path,
            descriptor: server_descriptor,
        })
    }

    pub fn descriptor_path(&self) -> &Path {
        &self.descriptor_path
    }
}

impl Drop for HookIpcServer {
    fn drop(&mut self) {
        if let Some(stop) = self.stop.take() {
            let _ = stop.send(());
        }
        if let Some(thread) = self.thread.take() {
            let _ = thread.join();
        }
        remove_owned_descriptor(&self.descriptor_path, &self.descriptor);
    }
}

/// Compute the product-owned descriptor path without accepting an arbitrary CLI path.
pub fn default_descriptor_path() -> io::Result<PathBuf> {
    #[cfg(target_os = "windows")]
    let root =
        PathBuf::from(std::env::var_os("LOCALAPPDATA").ok_or_else(|| {
            io::Error::new(io::ErrorKind::NotFound, "local app data unavailable")
        })?)
        .join("Temper");
    #[cfg(target_os = "macos")]
    let root = PathBuf::from(
        std::env::var_os("HOME")
            .ok_or_else(|| io::Error::new(io::ErrorKind::NotFound, "home unavailable"))?,
    )
    .join("Library")
    .join("Application Support")
    .join("Temper");
    #[cfg(all(unix, not(target_os = "macos")))]
    let root = std::env::var_os("XDG_RUNTIME_DIR")
        .map(PathBuf::from)
        .unwrap_or_else(std::env::temp_dir)
        .join("temper");
    Ok(root.join("hook-endpoint-v1.json"))
}

/// Invoke the local server. Every failure is represented as no target-visible output.
pub fn invoke_from_descriptor(descriptor_path: &Path, payload: Value) -> Option<Value> {
    invoke_inner(descriptor_path, payload).ok().flatten()
}

fn invoke_inner(descriptor_path: &Path, payload: Value) -> io::Result<Option<Value>> {
    let descriptor = read_descriptor(descriptor_path)?;
    let name = endpoint_name(&descriptor)?;
    let mut stream = Stream::connect(name)?;
    stream.set_nonblocking(true)?;
    let request = HookIpcRequestV1 {
        protocol_version: IPC_PROTOCOL_VERSION.to_owned(),
        auth_token: descriptor.auth_token,
        payload,
    };
    write_frame(&mut stream, &request)?;
    let response: HookIpcResponseV1 = read_frame(&mut stream)?;
    if response.protocol_version != IPC_PROTOCOL_VERSION {
        return Ok(None);
    }
    Ok(response.output)
}

fn serve(
    listener: Listener,
    descriptor: HookEndpointDescriptorV1,
    handler: Arc<HookHandler>,
    stop: Receiver<()>,
) {
    loop {
        match stop.try_recv() {
            Ok(()) | Err(mpsc::TryRecvError::Disconnected) => break,
            Err(mpsc::TryRecvError::Empty) => {}
        }
        match listener.accept() {
            Ok(stream) => {
                let _ = serve_connection(stream, &descriptor, &handler);
            }
            Err(error) if error.kind() == io::ErrorKind::WouldBlock => {
                match stop.recv_timeout(ACCEPT_POLL_INTERVAL) {
                    Ok(()) | Err(RecvTimeoutError::Disconnected) => break,
                    Err(RecvTimeoutError::Timeout) => {}
                }
            }
            Err(_) => break,
        }
    }
}

fn serve_connection(
    mut stream: Stream,
    descriptor: &HookEndpointDescriptorV1,
    handler: &Arc<HookHandler>,
) -> io::Result<()> {
    stream.set_nonblocking(true)?;
    if !peer_is_current_user(&stream) {
        return write_response(&mut stream, None);
    }
    let request: HookIpcRequestV1 = match read_frame(&mut stream) {
        Ok(value) => value,
        Err(_) => return write_response(&mut stream, None),
    };
    if request.protocol_version != IPC_PROTOCOL_VERSION
        || request.auth_token != descriptor.auth_token
    {
        return write_response(&mut stream, None);
    }
    let output =
        std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| handler(request.payload)))
            .ok()
            .flatten();
    write_response(&mut stream, output)
}

fn write_response(stream: &mut Stream, output: Option<Value>) -> io::Result<()> {
    write_frame(
        stream,
        &HookIpcResponseV1 {
            protocol_version: IPC_PROTOCOL_VERSION.to_owned(),
            output,
        },
    )
}

fn write_frame<T: Serialize>(stream: &mut Stream, value: &T) -> io::Result<()> {
    let mut encoded = serde_json::to_vec(value).map_err(io::Error::other)?;
    if encoded.len() > MAX_HOOK_FRAME_BYTES {
        return Err(io::Error::new(
            io::ErrorKind::InvalidData,
            "hook frame is oversized",
        ));
    }
    encoded.push(b'\n');
    let deadline = Instant::now() + SOCKET_TIMEOUT;
    let mut written = 0;
    while written < encoded.len() {
        match stream.write(&encoded[written..]) {
            Ok(0) => {
                return Err(io::Error::new(
                    io::ErrorKind::WriteZero,
                    "hook transport closed",
                ));
            }
            Ok(count) => written += count,
            Err(error) if error.kind() == io::ErrorKind::WouldBlock => {
                wait_for_io(deadline)?;
            }
            Err(error) => return Err(error),
        }
    }
    loop {
        match stream.flush() {
            Ok(()) => return Ok(()),
            Err(error) if error.kind() == io::ErrorKind::WouldBlock => wait_for_io(deadline)?,
            Err(error) => return Err(error),
        }
    }
}

fn read_frame<T: for<'de> Deserialize<'de>>(stream: &mut Stream) -> io::Result<T> {
    let mut encoded = Vec::new();
    let deadline = Instant::now() + SOCKET_TIMEOUT;
    let mut buffer = [0_u8; 8 * 1024];
    loop {
        match stream.read(&mut buffer) {
            Ok(0) => wait_for_io(deadline)?,
            Ok(count) => {
                encoded.extend_from_slice(&buffer[..count]);
                if encoded.len() > MAX_HOOK_FRAME_BYTES {
                    return Err(io::Error::new(
                        io::ErrorKind::InvalidData,
                        "hook frame is oversized",
                    ));
                }
                if encoded.contains(&b'\n') {
                    break;
                }
            }
            Err(error) if error.kind() == io::ErrorKind::WouldBlock => wait_for_io(deadline)?,
            Err(error) => return Err(error),
        }
    }
    let Some(newline) = encoded.iter().position(|value| *value == b'\n') else {
        return Err(io::Error::new(
            io::ErrorKind::InvalidData,
            "invalid hook frame",
        ));
    };
    if newline == 0 || newline + 1 != encoded.len() {
        return Err(io::Error::new(
            io::ErrorKind::InvalidData,
            "invalid hook frame",
        ));
    }
    encoded.truncate(newline);
    serde_json::from_slice(&encoded).map_err(io::Error::other)
}

fn wait_for_io(deadline: Instant) -> io::Result<()> {
    if Instant::now() >= deadline {
        return Err(io::Error::new(
            io::ErrorKind::TimedOut,
            "hook transport timed out",
        ));
    }
    thread::sleep(Duration::from_millis(1));
    Ok(())
}

fn new_descriptor(_path: &Path) -> io::Result<HookEndpointDescriptorV1> {
    let endpoint_nonce = Uuid::new_v4().simple().to_string();
    let auth_token = format!("{}{}", Uuid::new_v4().simple(), Uuid::new_v4().simple());
    #[cfg(target_os = "windows")]
    let (transport, endpoint) = (
        HookTransport::WindowsNamedPipe,
        format!("temper-hook-{endpoint_nonce}"),
    );
    #[cfg(unix)]
    let (transport, endpoint) = (
        HookTransport::UnixDomainSocket,
        _path
            .parent()
            .ok_or_else(|| io::Error::new(io::ErrorKind::InvalidInput, "descriptor root missing"))?
            .join(format!(".temper-hook-{endpoint_nonce}.sock"))
            .to_string_lossy()
            .into_owned(),
    );
    Ok(HookEndpointDescriptorV1 {
        protocol_version: IPC_PROTOCOL_VERSION.to_owned(),
        transport,
        endpoint,
        auth_token,
    })
}

fn endpoint_name(
    descriptor: &HookEndpointDescriptorV1,
) -> io::Result<interprocess::local_socket::Name<'_>> {
    if descriptor.protocol_version != IPC_PROTOCOL_VERSION
        || descriptor.auth_token.len() != 64
        || !descriptor
            .auth_token
            .bytes()
            .all(|value| value.is_ascii_hexdigit())
    {
        return Err(io::Error::new(
            io::ErrorKind::InvalidData,
            "invalid hook descriptor",
        ));
    }
    #[cfg(target_os = "windows")]
    if !matches!(descriptor.transport, HookTransport::WindowsNamedPipe) {
        return Err(io::Error::new(
            io::ErrorKind::InvalidData,
            "invalid hook transport",
        ));
    }
    #[cfg(unix)]
    if !matches!(descriptor.transport, HookTransport::UnixDomainSocket) {
        return Err(io::Error::new(
            io::ErrorKind::InvalidData,
            "invalid hook transport",
        ));
    }
    match descriptor.transport {
        HookTransport::WindowsNamedPipe => descriptor
            .endpoint
            .clone()
            .to_ns_name::<GenericNamespaced>(),
        HookTransport::UnixDomainSocket => {
            descriptor.endpoint.clone().to_fs_name::<GenericFilePath>()
        }
    }
}

fn create_listener(descriptor: &HookEndpointDescriptorV1) -> io::Result<Listener> {
    let name = endpoint_name(descriptor)?;
    let options = ListenerOptions::new().name(name);
    #[cfg(unix)]
    let options = {
        use interprocess::os::unix::local_socket::ListenerOptionsExt;
        options.mode(0o600)
    };
    #[cfg(target_os = "windows")]
    let options = {
        use interprocess::os::windows::local_socket::ListenerOptionsExt;
        use interprocess::os::windows::security_descriptor::SecurityDescriptor;
        use widestring::U16CString;

        let sddl = U16CString::from_str("D:P(A;;GA;;;OW)")
            .map_err(|_| io::Error::new(io::ErrorKind::InvalidData, "invalid pipe policy"))?;
        let descriptor = SecurityDescriptor::deserialize(sddl.as_ucstr())?;
        options.security_descriptor(descriptor)
    };
    options.create_sync()
}

fn persist_descriptor(path: &Path, descriptor: &HookEndpointDescriptorV1) -> io::Result<()> {
    let parent = path
        .parent()
        .ok_or_else(|| io::Error::new(io::ErrorKind::InvalidInput, "descriptor root missing"))?;
    fs::create_dir_all(parent)?;
    set_private_directory(parent)?;
    let temporary = parent.join(format!(".hook-endpoint-{}.tmp", Uuid::new_v4().simple()));
    let encoded = serde_json::to_vec(descriptor).map_err(io::Error::other)?;
    let mut options = OpenOptions::new();
    options.write(true).create_new(true);
    #[cfg(unix)]
    {
        use std::os::unix::fs::OpenOptionsExt;
        options.mode(0o600);
    }
    let mut file = options.open(&temporary)?;
    file.write_all(&encoded)?;
    file.write_all(b"\n")?;
    file.flush()?;
    file.sync_all()?;
    drop(file);
    atomic_replace(&temporary, path).inspect_err(|_| {
        let _ = fs::remove_file(&temporary);
    })?;
    Ok(())
}

#[cfg(unix)]
fn atomic_replace(source: &Path, destination: &Path) -> io::Result<()> {
    fs::rename(source, destination)
}

#[cfg(target_os = "windows")]
fn atomic_replace(source: &Path, destination: &Path) -> io::Result<()> {
    use std::os::windows::ffi::OsStrExt;
    use windows_sys::Win32::Storage::FileSystem::{
        MOVEFILE_REPLACE_EXISTING, MOVEFILE_WRITE_THROUGH, MoveFileExW,
    };

    let source_wide = source
        .as_os_str()
        .encode_wide()
        .chain(std::iter::once(0))
        .collect::<Vec<_>>();
    let destination_wide = destination
        .as_os_str()
        .encode_wide()
        .chain(std::iter::once(0))
        .collect::<Vec<_>>();
    let replaced = unsafe {
        MoveFileExW(
            source_wide.as_ptr(),
            destination_wide.as_ptr(),
            MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH,
        )
    };
    if replaced == 0 {
        Err(io::Error::last_os_error())
    } else {
        Ok(())
    }
}

fn read_descriptor(path: &Path) -> io::Result<HookEndpointDescriptorV1> {
    let file = OpenOptions::new().read(true).open(path)?;
    let metadata = file.metadata()?;
    if !metadata.is_file() || metadata.len() > MAX_DESCRIPTOR_BYTES {
        return Err(io::Error::new(
            io::ErrorKind::InvalidData,
            "invalid hook descriptor",
        ));
    }
    #[cfg(unix)]
    {
        use std::os::unix::fs::MetadataExt;
        if metadata.uid() != unsafe { libc::geteuid() } || metadata.mode() & 0o077 != 0 {
            return Err(io::Error::new(
                io::ErrorKind::PermissionDenied,
                "unsafe hook descriptor",
            ));
        }
    }
    let mut encoded = String::new();
    file.take(MAX_DESCRIPTOR_BYTES + 1)
        .read_to_string(&mut encoded)?;
    let descriptor: HookEndpointDescriptorV1 =
        serde_json::from_str(&encoded).map_err(io::Error::other)?;
    endpoint_name(&descriptor)?;
    Ok(descriptor)
}

fn remove_owned_descriptor(path: &Path, expected: &HookEndpointDescriptorV1) {
    if read_descriptor(path).is_ok_and(|actual| actual == *expected) {
        let _ = fs::remove_file(path);
    }
}

#[cfg(unix)]
fn set_private_directory(path: &Path) -> io::Result<()> {
    use std::os::unix::fs::PermissionsExt;
    fs::set_permissions(path, fs::Permissions::from_mode(0o700))
}

#[cfg(target_os = "windows")]
fn set_private_directory(_path: &Path) -> io::Result<()> {
    Ok(())
}

#[cfg(unix)]
fn peer_is_current_user(stream: &Stream) -> bool {
    stream.peer_creds().ok().and_then(|value| value.euid()) == Some(unsafe { libc::geteuid() })
}

#[cfg(target_os = "windows")]
fn peer_is_current_user(_stream: &Stream) -> bool {
    // The owner-only DACL is applied before the named-pipe listener is created.
    true
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;
    use std::time::Instant;

    #[test]
    fn local_round_trip_is_bounded_and_returns_only_handler_output() {
        let root = tempfile::tempdir().expect("temporary directory");
        let descriptor = root.path().join("hook.json");
        let server = HookIpcServer::start(descriptor.clone(), |payload| {
            assert_eq!(payload["hook_event_name"], "UserPromptSubmit");
            Some(json!({
                "hookSpecificOutput": {
                    "hookEventName": "UserPromptSubmit",
                    "additionalContext": "Use the exact approved projection."
                }
            }))
        })
        .expect("start hook server");
        let started = Instant::now();
        let output = invoke_inner(
            server.descriptor_path(),
            json!({"hook_event_name": "UserPromptSubmit"}),
        )
        .expect("hook transport")
        .expect("hook output");

        assert_eq!(
            output["hookSpecificOutput"]["additionalContext"],
            "Use the exact approved projection."
        );
        assert!(started.elapsed() < Duration::from_millis(150));
    }

    #[test]
    fn unavailable_or_tampered_descriptor_is_a_silent_noop() {
        let root = tempfile::tempdir().expect("temporary directory");
        let missing = root.path().join("missing.json");
        assert!(invoke_from_descriptor(&missing, json!({})).is_none());

        let descriptor = root.path().join("hook.json");
        let _server = HookIpcServer::start(descriptor.clone(), |_| Some(json!({"bad": true})))
            .expect("start hook server");
        let mut value: Value =
            serde_json::from_str(&fs::read_to_string(&descriptor).expect("read descriptor"))
                .expect("parse descriptor");
        value["auth_token"] = Value::String("0".repeat(64));
        fs::write(
            &descriptor,
            serde_json::to_vec(&value).expect("encode descriptor"),
        )
        .expect("tamper descriptor");
        #[cfg(unix)]
        fs::set_permissions(
            &descriptor,
            std::os::unix::fs::PermissionsExt::from_mode(0o600),
        )
        .expect("restore fixture mode");

        assert!(invoke_from_descriptor(&descriptor, json!({})).is_none());
    }

    #[test]
    fn server_shutdown_removes_the_sensitive_descriptor() {
        let root = tempfile::tempdir().expect("temporary directory");
        let descriptor = root.path().join("hook.json");
        let server = HookIpcServer::start(descriptor.clone(), |_| None).expect("start hook server");
        assert!(descriptor.exists());
        drop(server);
        assert!(!descriptor.exists());
    }

    #[test]
    fn newer_server_atomically_replaces_stale_descriptor_and_retains_ownership() {
        let root = tempfile::tempdir().expect("temporary directory");
        let descriptor = root.path().join("hook.json");
        fs::write(&descriptor, b"stale endpoint").expect("stale descriptor");

        let older = HookIpcServer::start(descriptor.clone(), |_| Some(json!({"server": "old"})))
            .expect("start older server");
        let newer = HookIpcServer::start(descriptor.clone(), |_| Some(json!({"server": "new"})))
            .expect("replace descriptor with newer server");
        drop(older);

        assert!(descriptor.exists());
        assert_eq!(
            invoke_inner(&descriptor, json!({}))
                .expect("newer endpoint")
                .expect("newer output"),
            json!({"server": "new"})
        );
        drop(newer);
        assert!(!descriptor.exists());
    }

    #[cfg(unix)]
    #[test]
    fn descriptor_permissions_are_owner_only() {
        use std::os::unix::fs::PermissionsExt;

        let root = tempfile::tempdir().expect("temporary directory");
        let descriptor = root.path().join("hook.json");
        let _server =
            HookIpcServer::start(descriptor.clone(), |_| None).expect("start hook server");
        assert_eq!(
            fs::metadata(descriptor)
                .expect("descriptor metadata")
                .permissions()
                .mode()
                & 0o777,
            0o600
        );
    }
}
