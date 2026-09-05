#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use serde_json::Value;
use std::io::{self, Read, Write};
use temper_hook_transport::{default_descriptor_path, invoke_from_descriptor};

const MAX_STDIN_BYTES: u64 = 1_048_576;

fn main() {
    // Claude hooks must never block the user's agent when Temper is unavailable.
    let Some(output) = run() else {
        return;
    };
    if let Ok(mut encoded) = serde_json::to_vec(&output) {
        encoded.push(b'\n');
        let _ = io::stdout().write_all(&encoded);
    }
}

fn run() -> Option<Value> {
    let descriptor = default_descriptor_path().ok()?;
    let mut encoded = Vec::new();
    io::stdin()
        .take(MAX_STDIN_BYTES + 1)
        .read_to_end(&mut encoded)
        .ok()?;
    if encoded.is_empty() || encoded.len() > MAX_STDIN_BYTES as usize {
        return None;
    }
    let payload: Value = serde_json::from_slice(&encoded).ok()?;
    if !payload.is_object() {
        return None;
    }
    invoke_from_descriptor(&descriptor, payload)
}
