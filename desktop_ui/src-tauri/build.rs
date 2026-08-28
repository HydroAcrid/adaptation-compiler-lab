use serde::Deserialize;
use std::env;
use std::fs;
use std::path::PathBuf;

#[derive(Deserialize)]
struct EngineBuildManifest {
    manifest_version: String,
    engine_version: String,
    snapshot_schema_digest: String,
    target_triple: String,
    binary_filename: String,
    binary_sha256: String,
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
    assert!(manifest.binary_sha256.len() == 64);
    let binary_path = manifest_dir
        .join("binaries")
        .join(&manifest.binary_filename);
    assert!(
        binary_path.is_file(),
        "release engine sidecar is unavailable"
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
            "profile_export_preview",
            "profile_export",
            "profile_import_preview",
            "profile_import_stage",
            "modes_list",
            "mode_run_task",
            "task_run",
            "task_apply",
            "task_discard",
            "diagnostics_get",
            "notification_permission",
        ]),
    ))
    .expect("failed to build Temper desktop metadata");
}
