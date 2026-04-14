//! Token store for the Clerk-backed desktop auth flow.
//!
//! # Why two surfaces?
//!
//! We register the `tauri-plugin-stronghold` plugin at startup so the TS
//! side can use it directly for high-value secrets later (e.g. local driver
//! credentials, or eventually the Clerk refresh token once Clerk publishes
//! a refresh contract we can rely on for desktop clients). For the Clerk
//! session token itself we use the simpler path documented here:
//!
//! * A JSON blob is written to the app's local data directory under
//!   `auth/session.json` with mode 0600 on POSIX.
//! * The blob is read once on launch and handed to the Clerk JS SDK via
//!   `@clerk/clerk-js` which refreshes it against Clerk's Frontend API.
//! * On sign-out we delete the file.
//!
//! This keeps the plumbing inside a single Rust module with a well-typed
//! `Result<T, String>` surface (matching the repo's Tauri style rule) and
//! avoids the extra Stronghold initialisation / passphrase ceremony on
//! first launch. Stronghold stays available for future hardening.
//!
//! # Security posture
//!
//! Clerk session tokens are short-lived (~60s default). A compromised file
//! read on the user's own machine is not materially worse than reading
//! any cookie store — we rely on the OS file permission model. We never
//! log token contents; see `log_note`.

use std::fs;
use std::path::PathBuf;

use serde::{Deserialize, Serialize};
use tauri::{AppHandle, Manager};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct StoredToken {
    /// Clerk session token (a JWT). May be expired; the TS side refreshes
    /// it against Clerk's JWKS endpoint on load.
    pub token: String,
    /// Unix epoch millis when we captured the token — used by the TS side
    /// to decide whether a refresh is needed before the SDK's first call.
    pub captured_at_ms: i64,
}

fn token_file(app: &AppHandle) -> Result<PathBuf, String> {
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
        .map_err(|e| format!("stat token file: {e}"))?
        .permissions();
    perms.set_mode(0o600);
    fs::set_permissions(path, perms).map_err(|e| format!("chmod token file: {e}"))
}

#[cfg(not(unix))]
fn tighten_perms(_: &std::path::Path) -> Result<(), String> {
    // On Windows the file lives under the user's AppData\Local tree, which
    // already excludes other users by default ACL.
    Ok(())
}

/// Log a neutral marker when the token is touched. We deliberately never
/// print token contents — auditors should be able to grep for "voyagent auth"
/// in the binary and confirm no token value ever hits stdout.
fn log_note(op: &str) {
    eprintln!("[voyagent auth] {op}");
}

#[tauri::command]
pub async fn auth_store_token(app: AppHandle, token: String) -> Result<(), String> {
    let captured_at_ms = chrono_ish_now_ms();
    let blob = StoredToken {
        token,
        captured_at_ms,
    };
    let payload = serde_json::to_vec(&blob).map_err(|e| format!("serialize: {e}"))?;
    let path = token_file(&app)?;
    fs::write(&path, payload).map_err(|e| format!("write token file: {e}"))?;
    tighten_perms(&path)?;
    log_note("store");
    Ok(())
}

#[tauri::command]
pub async fn auth_load_token(app: AppHandle) -> Result<Option<StoredToken>, String> {
    let path = token_file(&app)?;
    if !path.exists() {
        return Ok(None);
    }
    let bytes = fs::read(&path).map_err(|e| format!("read token file: {e}"))?;
    let blob: StoredToken =
        serde_json::from_slice(&bytes).map_err(|e| format!("parse token file: {e}"))?;
    log_note("load");
    Ok(Some(blob))
}

#[tauri::command]
pub async fn auth_clear_token(app: AppHandle) -> Result<(), String> {
    let path = token_file(&app)?;
    if path.exists() {
        fs::remove_file(&path).map_err(|e| format!("remove token file: {e}"))?;
    }
    log_note("clear");
    Ok(())
}

/// `chrono` isn't in the dep set and we don't want to pull it in just for
/// a timestamp. Use `SystemTime` → millis since epoch.
fn chrono_ish_now_ms() -> i64 {
    use std::time::{SystemTime, UNIX_EPOCH};
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_millis() as i64)
        .unwrap_or(0)
}
