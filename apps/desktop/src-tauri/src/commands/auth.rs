//! Secure local store for the Voyagent in-house cookie/JWT auth session.
//!
//! # Storage model
//!
//! Desktop is a native app with no HttpOnly cookies, so the access and
//! refresh tokens live in a JSON blob written to the app's local data
//! directory under `auth/session.json` with mode 0600 on POSIX. On
//! Windows, the file lives under the user's AppData\Local tree, which
//! already excludes other users by default ACL.
//!
//! The TS side (`src/auth/VoyagentAuthClient.ts`) drives token refresh
//! via the in-house `/api/auth/refresh` endpoint and rewrites this blob
//! whenever it rotates. On sign-out we delete the file.
//!
//! Stronghold remains registered as a plugin at startup for future
//! high-value secrets (local driver credentials etc.); it is not used
//! for session tokens here to keep the first-launch ceremony minimal.
//!
//! # Security posture
//!
//! Access tokens are short-lived JWTs; refresh tokens are long-lived but
//! rotated on every refresh. A compromised file read on the user's own
//! machine is not materially worse than reading any cookie store — we
//! rely on the OS file permission model. We never log token contents.

use std::fs;
use std::path::PathBuf;

use serde::{Deserialize, Serialize};
use serde_json::Value;
use tauri::{AppHandle, Manager};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct StoredSession {
    pub access_token: String,
    pub refresh_token: String,
    /// Cached public-user payload from `/api/auth/me`. May be null if
    /// the session was stored before /me completed.
    #[serde(default)]
    pub user: Option<Value>,
}

fn session_file(app: &AppHandle) -> Result<PathBuf, String> {
    let dir = app
        .path()
        .app_local_data_dir()
        .map_err(|e| format!("resolving app local data dir: {e}"))?;
    let auth = dir.join("auth");
    fs::create_dir_all(&auth).map_err(|e| format!("creating auth dir: {e}"))?;
    Ok(auth.join("session.json"))
}

#[cfg(unix)]
fn tighten_perms(path: &std::path::Path) -> Result<(), String> {
    use std::os::unix::fs::PermissionsExt;
    let mut perms = fs::metadata(path)
        .map_err(|e| format!("stat session file: {e}"))?
        .permissions();
    perms.set_mode(0o600);
    fs::set_permissions(path, perms).map_err(|e| format!("chmod session file: {e}"))
}

#[cfg(not(unix))]
fn tighten_perms(_: &std::path::Path) -> Result<(), String> {
    Ok(())
}

/// Log a neutral marker when the session is touched. We deliberately
/// never print token contents — auditors should be able to grep for
/// "voyagent auth" in the binary and confirm no token value ever hits
/// stdout.
fn log_note(op: &str) {
    eprintln!("[voyagent auth] {op}");
}

#[tauri::command]
pub async fn voyagent_store_session(
    app: AppHandle,
    session: StoredSession,
) -> Result<(), String> {
    let payload = serde_json::to_vec(&session).map_err(|e| format!("serialize: {e}"))?;
    let path = session_file(&app)?;
    fs::write(&path, payload).map_err(|e| format!("write session file: {e}"))?;
    tighten_perms(&path)?;
    log_note("store");
    Ok(())
}

#[tauri::command]
pub async fn voyagent_load_session(app: AppHandle) -> Result<Option<StoredSession>, String> {
    let path = session_file(&app)?;
    if !path.exists() {
        return Ok(None);
    }
    let bytes = fs::read(&path).map_err(|e| format!("read session file: {e}"))?;
    let blob: StoredSession =
        serde_json::from_slice(&bytes).map_err(|e| format!("parse session file: {e}"))?;
    log_note("load");
    Ok(Some(blob))
}

#[tauri::command]
pub async fn voyagent_clear_session(app: AppHandle) -> Result<(), String> {
    let path = session_file(&app)?;
    if path.exists() {
        fs::remove_file(&path).map_err(|e| format!("remove session file: {e}"))?;
    }
    log_note("clear");
    Ok(())
}
