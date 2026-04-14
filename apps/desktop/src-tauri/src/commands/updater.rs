//! Auto-update command surface.
//!
//! Wraps `tauri-plugin-updater` with a tiny `check_for_updates` entrypoint
//! the frontend can call on launch. The plugin handles manifest fetching,
//! signature verification, and binary install; we only expose a typed
//! result the React layer can translate into a toast.

use serde::Serialize;
use tauri::AppHandle;
use tauri_plugin_updater::UpdaterExt;

#[derive(Debug, Clone, Serialize)]
pub struct UpdateStatus {
    /// Whether a newer version is available on the configured endpoint.
    pub available: bool,
    /// Version string reported by the updater manifest, if any.
    pub version: Option<String>,
    /// Release notes, if the manifest provided them.
    pub notes: Option<String>,
}

#[tauri::command]
pub async fn check_for_updates(app: AppHandle) -> Result<UpdateStatus, String> {
    let updater = app
        .updater()
        .map_err(|e| format!("constructing updater: {e}"))?;
    let result = updater
        .check()
        .await
        .map_err(|e| format!("checking for updates: {e}"))?;
    match result {
        Some(update) => Ok(UpdateStatus {
            available: true,
            version: Some(update.version.clone()),
            notes: update.body.clone(),
        }),
        None => Ok(UpdateStatus {
            available: false,
            version: None,
            notes: None,
        }),
    }
}
