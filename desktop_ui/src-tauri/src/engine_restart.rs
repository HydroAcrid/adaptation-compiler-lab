//! Bound failed starts independently of renderer polling frequency.
use std::collections::VecDeque;
use std::time::{Duration, Instant};

const WINDOW: Duration = Duration::from_secs(60 * 60);
const COOLDOWN: Duration = Duration::from_secs(60);
pub const MIN_FREE_BYTES: u64 = 1024 * 1024 * 1024;

#[derive(Default)]
pub struct RestartGuard {
    failures: VecDeque<Instant>,
}

impl RestartGuard {
    pub fn may_start(&mut self, now: Instant, free: Option<u64>) -> Result<(), &'static str> {
        if free.is_none_or(|bytes| bytes < MIN_FREE_BYTES) {
            return Err("Temper needs at least 1 GB of free disk space to start its engine.");
        }
        while self
            .failures
            .front()
            .is_some_and(|at| now.duration_since(*at) >= WINDOW)
        {
            self.failures.pop_front();
        }
        if self.failures.len() >= 3
            || self
                .failures
                .back()
                .is_some_and(|at| now.duration_since(*at) < COOLDOWN)
        {
            return Err(
                "The local engine could not start. Automatic retries are paused; reopen Temper after resolving the problem.",
            );
        }
        Ok(())
    }

    pub fn failed(&mut self, now: Instant) {
        self.failures.push_back(now);
    }

    pub fn responded(&mut self) {
        self.failures.clear();
    }
}

#[cfg(target_os = "windows")]
pub fn available_space() -> Option<u64> {
    use std::os::windows::ffi::OsStrExt;
    #[link(name = "kernel32")]
    unsafe extern "system" {
        fn GetDiskFreeSpaceExW(
            path: *const u16,
            available: *mut u64,
            total: *mut u64,
            free: *mut u64,
        ) -> i32;
    }
    let executable = std::env::current_exe().ok()?;
    let path: Vec<u16> = executable
        .parent()?
        .as_os_str()
        .encode_wide()
        .chain(Some(0))
        .collect();
    let mut available = 0;
    // A read-only volume query. The cache lives beside the executable.
    let ok = unsafe {
        GetDiskFreeSpaceExW(
            path.as_ptr(),
            &mut available,
            std::ptr::null_mut(),
            std::ptr::null_mut(),
        )
    };
    (ok != 0).then_some(available)
}

#[cfg(not(target_os = "windows"))]
pub fn available_space() -> Option<u64> {
    // This incident and the disk-space admission change are Windows-specific.
    Some(u64::MAX)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn repeated_polls_cannot_launch_an_unlimited_failing_engine() {
        let start = Instant::now();
        let mut guard = RestartGuard::default();
        let mut starts = 0;
        for seconds in (0..3600).step_by(30) {
            let now = start + Duration::from_secs(seconds);
            if guard.may_start(now, Some(MIN_FREE_BYTES)).is_ok() {
                starts += 1;
                guard.failed(now);
            }
        }
        assert_eq!(
            starts, 3,
            "failed engine starts must be capped at three per hour"
        );
        assert!(
            guard
                .may_start(start + WINDOW, Some(MIN_FREE_BYTES))
                .is_ok()
        );
    }

    #[test]
    fn low_or_unknown_space_never_starts_a_child() {
        let mut guard = RestartGuard::default();
        for free in [None, Some(0), Some(MIN_FREE_BYTES - 1)] {
            assert!(guard.may_start(Instant::now(), free).is_err());
        }
        assert!(
            guard
                .may_start(Instant::now(), Some(MIN_FREE_BYTES))
                .is_ok()
        );
    }

    #[test]
    fn a_valid_response_restores_normal_operation() {
        let start = Instant::now();
        let mut guard = RestartGuard::default();
        guard.failed(start);
        assert!(guard.may_start(start, Some(MIN_FREE_BYTES)).is_err());
        guard.responded();
        assert!(guard.may_start(start, Some(MIN_FREE_BYTES)).is_ok());
    }
}
