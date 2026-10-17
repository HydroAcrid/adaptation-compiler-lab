//! Windows engine entry point: one cache, serialized initialization, owned children.
#[cfg(windows)]
mod windows {
    use sha2::{Digest, Sha256};
    use std::collections::hash_map::DefaultHasher;
    use std::hash::{Hash, Hasher};
    use std::io::Read;
    use std::os::windows::fs::MetadataExt;
    use std::os::windows::process::CommandExt;
    use std::process::{Command, Stdio};
    use std::time::{Duration, Instant};
    use windows_sys::Win32::Foundation::{CloseHandle, HANDLE, WAIT_ABANDONED, WAIT_OBJECT_0};
    use windows_sys::Win32::System::JobObjects::*;
    use windows_sys::Win32::System::Threading::*;

    struct CacheLock(HANDLE);
    impl Drop for CacheLock {
        fn drop(&mut self) {
            unsafe {
                ReleaseMutex(self.0);
                CloseHandle(self.0);
            }
        }
    }

    fn validate_cache(root: &std::path::Path) -> Result<(), &'static str> {
        let mut pending = vec![root.to_owned()];
        let mut bytes = 0u64;
        while let Some(path) = pending.pop() {
            let info = match std::fs::symlink_metadata(&path) {
                Ok(info) => info,
                Err(error) if error.kind() == std::io::ErrorKind::NotFound => continue,
                Err(_) => return Err("Cannot inspect engine cache."),
            };
            if info.file_attributes() & 0x400 != 0 {
                return Err("Engine cache is redirected. Reinstall Temper.");
            }
            if info.is_dir() {
                for entry in std::fs::read_dir(path).map_err(|_| "Cannot inspect engine cache.")? {
                    pending.push(entry.map_err(|_| "Cannot inspect engine cache.")?.path());
                }
            } else {
                bytes = bytes
                    .checked_add(info.len())
                    .ok_or("Engine cache size is invalid.")?;
                if bytes > 256 * 1024 * 1024 {
                    return Err("Engine cache exceeds 256 MB. Reinstall Temper.");
                }
            }
        }
        Ok(())
    }

    pub fn run() -> Result<i32, &'static str> {
        let current = std::env::current_exe().map_err(|_| "Engine install path is unavailable.")?;
        let directory = current
            .parent()
            .ok_or("Engine install path is unavailable.")?;
        for ancestor in directory.ancestors() {
            let info = std::fs::symlink_metadata(ancestor)
                .map_err(|_| "Cannot inspect engine install path.")?;
            if info.file_attributes() & 0x400 != 0 {
                return Err("Engine install path is redirected.");
            }
        }
        let generic = directory.join("temper-engine-payload.exe");
        let payload = if generic.is_file() {
            generic
        } else {
            directory.join("temper-engine-payload-x86_64-pc-windows-msvc.exe")
        };
        let expected = option_env!("TEMPER_ENGINE_PAYLOAD_SHA256").unwrap_or("");
        let mut source =
            std::fs::File::open(&payload).map_err(|_| "Engine payload is unavailable.")?;
        let mut hash = Sha256::new();
        let mut buffer = [0u8; 65536];
        loop {
            let count = source
                .read(&mut buffer)
                .map_err(|_| "Cannot verify engine payload.")?;
            if count == 0 {
                break;
            }
            hash.update(&buffer[..count]);
        }
        if expected.len() != 64 || format!("{:x}", hash.finalize()) != expected {
            return Err("Engine payload does not match the installed launcher.");
        }
        drop(source);

        // The OS closes this handle on process exit, including forced termination.
        // Owning the launcher and all descendants prevents orphaned inner workers.
        // Do not close it early: KILL_ON_JOB_CLOSE also covers this process.
        unsafe {
            let job = CreateJobObjectW(std::ptr::null(), std::ptr::null());
            if job.is_null() {
                return Err("Cannot contain engine processes.");
            }
            let mut limits: JOBOBJECT_EXTENDED_LIMIT_INFORMATION = std::mem::zeroed();
            limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
            if SetInformationJobObject(
                job,
                JobObjectExtendedLimitInformation,
                &limits as *const _ as _,
                std::mem::size_of_val(&limits) as u32,
            ) == 0
                || AssignProcessToJobObject(job, GetCurrentProcess()) == 0
            {
                CloseHandle(job);
                return Err("Cannot contain engine processes.");
            }
            // Intentionally retained until OS process teardown, not a per-call leak.
        }

        let mut identity = DefaultHasher::new();
        directory
            .to_string_lossy()
            .to_lowercase()
            .hash(&mut identity);
        let name: Vec<u16> = format!("Local\\TemperEngineCache-{:016x}", identity.finish())
            .encode_utf16()
            .chain(Some(0))
            .collect();
        let lock = unsafe { CreateMutexW(std::ptr::null(), 0, name.as_ptr()) };
        if lock.is_null() {
            return Err("Cannot lock engine cache.");
        }
        match unsafe { WaitForSingleObject(lock, 30_000) } {
            WAIT_OBJECT_0 | WAIT_ABANDONED => {}
            _ => {
                unsafe {
                    CloseHandle(lock);
                }
                return Err("Engine cache initialization is busy. Retry shortly.");
            }
        }
        let lock = CacheLock(lock);
        validate_cache(&directory.join(".temper-engine-cache"))?;
        // --help exits at argument parsing, before loading runtime state or auth.
        let mut warm = Command::new(&payload)
            .arg("--help")
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(Stdio::inherit())
            .creation_flags(CREATE_NO_WINDOW)
            .spawn()
            .map_err(|_| "Cannot initialize engine cache.")?;
        let deadline = Instant::now() + Duration::from_secs(15);
        loop {
            match warm.try_wait() {
                Ok(Some(status)) if status.success() => break,
                Ok(Some(_)) | Err(_) => {
                    return Err(
                        "Cannot initialize engine cache. Close old engine sessions before upgrading.",
                    );
                }
                Ok(None) if Instant::now() < deadline => {
                    std::thread::sleep(Duration::from_millis(10))
                }
                Ok(None) => {
                    let _ = warm.kill();
                    let _ = warm.wait();
                    return Err("Engine cache initialization timed out.");
                }
            }
        }
        validate_cache(&directory.join(".temper-engine-cache"))?;
        drop(lock);
        let status = Command::new(&payload)
            .args(std::env::args_os().skip(1))
            .stdin(Stdio::inherit())
            .stdout(Stdio::inherit())
            .stderr(Stdio::inherit())
            .creation_flags(CREATE_NO_WINDOW)
            .status()
            .map_err(|_| "Cannot start engine payload.")?;
        Ok(status.code().unwrap_or(1))
    }
}

fn main() {
    #[cfg(windows)]
    match windows::run() {
        Ok(code) => std::process::exit(code),
        Err(message) => {
            eprintln!("{message}");
            std::process::exit(1);
        }
    }
    #[cfg(not(windows))]
    panic!("The cache launcher is Windows-only.");
}
