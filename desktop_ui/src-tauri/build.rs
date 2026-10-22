use serde::Deserialize;
use sha2::{Digest, Sha256};
use std::env;
use std::fs::{self, File};
use std::io::Read;
use std::path::PathBuf;

#[derive(Deserialize)]
struct EngineBuildManifest {
    manifest_version: String,
    engine_version: String,
    snapshot_schema_digest: String,
    target_triple: String,
    binary_filename: String,
    binary_sha256: String,
    payload_filename: Option<String>,
    payload_sha256: Option<String>,
}

#[derive(Deserialize)]
struct HookBuildManifest {
    manifest_version: String,
    protocol_version: String,
    target_triple: String,
    binary_filename: String,
    binary_sha256: String,
}

fn require_exact_digest(path: &PathBuf, expected: &str, label: &str) {
    assert!(expected.len() == 64, "{label} digest is invalid");
    let mut source = File::open(path).unwrap_or_else(|_| panic!("{label} is unavailable"));
    let mut hasher = Sha256::new();
    let mut buffer = [0_u8; 64 * 1024];
    loop {
        let read = source
            .read(&mut buffer)
            .unwrap_or_else(|_| panic!("{label} cannot be read"));
        if read == 0 {
            break;
        }
        hasher.update(&buffer[..read]);
    }
    assert_eq!(
        format!("{:x}", hasher.finalize()),
        expected,
        "{label} digest does not match its build manifest"
    );
}

fn bind_release_engine() {
    if env::var("PROFILE").as_deref() != Ok("release") {
        return;
    }
    let target = env::var("TARGET").expect("release target triple is unavailable");
    let manifest_dir =
        PathBuf::from(env::var("CARGO_MANIFEST_DIR").expect("manifest directory is unavailable"));
    let manifest_path = manifest_dir
        .join("binaries")
        .join(format!("temper-engine-{target}.manifest.json"));
    println!("cargo:rerun-if-changed={}", manifest_path.display());
    let encoded =
        fs::read_to_string(&manifest_path).expect("release engine build manifest is unavailable");
    let manifest: EngineBuildManifest =
        serde_json::from_str(&encoded).expect("release engine build manifest is invalid");
    assert_eq!(manifest.manifest_version, "1.0.0");
    assert_eq!(manifest.target_triple, target);
    assert!(
        manifest
            .engine_version
            .as_bytes()
            .first()
            .is_some_and(u8::is_ascii_digit)
    );
    assert!(
        manifest.snapshot_schema_digest.starts_with("sha256:")
            && manifest.snapshot_schema_digest.len() == 71
    );
    let binary_path = manifest_dir
        .join("binaries")
        .join(&manifest.binary_filename);
    assert!(
        binary_path.is_file(),
        "release engine sidecar is unavailable"
    );
    require_exact_digest(
        &binary_path,
        &manifest.binary_sha256,
        "release engine sidecar",
    );
    if target == "x86_64-pc-windows-msvc" {
        let filename = manifest
            .payload_filename
            .as_ref()
            .expect("release engine payload is unavailable");
        assert_eq!(filename, &format!("temper-engine-payload-{target}.exe"));
        let path = manifest_dir.join("binaries").join(filename);
        println!("cargo:rerun-if-changed={}", path.display());
        require_exact_digest(
            &path,
            manifest.payload_sha256.as_deref().unwrap_or(""),
            "release engine payload",
        );
    }

    let hook_manifest_path = manifest_dir
        .join("binaries")
        .join(format!("temper-hook-{target}.manifest.json"));
    println!("cargo:rerun-if-changed={}", hook_manifest_path.display());
    let hook_encoded = fs::read_to_string(&hook_manifest_path)
        .expect("release hook helper build manifest is unavailable");
    let hook: HookBuildManifest =
        serde_json::from_str(&hook_encoded).expect("release hook helper build manifest is invalid");
    assert_eq!(hook.manifest_version, "1.0.0");
    assert_eq!(hook.protocol_version, "temper-hook-ipc/v1");
    assert_eq!(hook.target_triple, target);
    let hook_binary_path = manifest_dir.join("binaries").join(&hook.binary_filename);
    assert!(
        hook_binary_path.is_file(),
        "release hook helper is unavailable"
    );
    require_exact_digest(
        &hook_binary_path,
        &hook.binary_sha256,
        "release hook helper",
    );
    println!(
        "cargo:rustc-env=TEMPER_EXPECTED_ENGINE_VERSION={}",
        manifest.engine_version
    );
    println!(
        "cargo:rustc-env=TEMPER_EXPECTED_SCHEMA_DIGEST={}",
        manifest.snapshot_schema_digest
    );
    println!(
        "cargo:rustc-env=TEMPER_EXPECTED_ENGINE_SHA256={}",
        manifest.binary_sha256
    );
}

fn main() {
    // Unit-test executables link the same native dialog imports as the app, but
    // Tauri only embeds its window manifest in the app binary. Activate v6 for
    // every linked Windows target so TaskDialogIndirect is available in tests.
    if env::var("CARGO_CFG_TARGET_OS").as_deref() == Ok("windows")
        && env::var("CARGO_CFG_TARGET_ENV").as_deref() == Ok("msvc")
    {
        println!("cargo:rustc-link-arg=/MANIFEST:EMBED");
        println!(
            "cargo:rustc-link-arg=/MANIFESTDEPENDENCY:type='win32' name='Microsoft.Windows.Common-Controls' version='6.0.0.0' processorArchitecture='*' publicKeyToken='6595b64144ccf1df' language='*'"
        );
    }
    bind_release_engine();
    tauri_build::try_build(tauri_build::Attributes::new().app_manifest(
        tauri_build::AppManifest::new().commands(&[
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
            "copilot_connection_preview",
            "copilot_connection_apply",
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
            "hub_catalog_get",
            "hub_mode_get",
            "modes_list",
            "mode_activation_preview",
            "mode_run_task",
            "task_run",
            "task_apply",
            "task_discard",
            "diagnostics_get",
            "autonomy_status",
            "autonomy_grant_preview",
            "autonomy_grant_enable",
            "autonomy_control",
            "autonomy_habit_explain",
            "autonomy_applicability_preview",
            "notification_permission",
        ]),
    ))
    .expect("failed to build Temper desktop metadata");
}
