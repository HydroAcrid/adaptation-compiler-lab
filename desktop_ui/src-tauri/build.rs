fn main() {
    tauri_build::try_build(tauri_build::Attributes::new().app_manifest(
        tauri_build::AppManifest::new().commands(&["engine_handshake", "snapshot_get"]),
    ))
    .expect("failed to build Temper desktop metadata");
}
