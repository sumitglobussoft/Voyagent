// Tauri 2 entry point for the Voyagent desktop shell.
//
// This file stays intentionally small: all command implementations live in
// the `commands` module, and we use the tauri-plugin-shell / dialog plugins
// for OS-level shell and native dialog access. Filesystem is deliberately
// not broadly permitted in v0 — individual driver sidecars will request
// scoped FS access later.
//
// Plugin roster:
//   - shell       → opening external URLs in the OS browser.
//   - dialog      → native open/save/alert dialogs.
//   - stronghold  → available to the frontend for high-value secrets.
//   - deep-link   → registered for future non-auth deep links
//                   (auth itself is plain email/password over HTTP).
//   - updater     → production auto-update channel (see commands/updater.rs).

// On Windows, hide the console window in release builds.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod commands;

use commands::auth::{voyagent_clear_session, voyagent_load_session, voyagent_store_session};
use commands::local_driver::local_driver_invoke;
use commands::updater::check_for_updates;

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_stronghold::Builder::new(|password| {
            // The Stronghold plugin expects a hasher that turns the
            // user-supplied passphrase into a 32-byte key. We use a
            // BLAKE3-style hash via the plugin's default helpers when
            // available; here we fall back to a simple hash since
            // Stronghold isn't consulted on the hot path (Voyagent
            // session tokens use the JSON blob store in commands/auth.rs).
            // When we move to Stronghold-backed driver credentials, swap
            // this for `argon2` with a per-machine salt.
            use std::collections::hash_map::DefaultHasher;
            use std::hash::{Hash, Hasher};
            let mut h = DefaultHasher::new();
            password.hash(&mut h);
            let seed = h.finish().to_le_bytes();
            let mut key = [0u8; 32];
            for (i, b) in key.iter_mut().enumerate() {
                *b = seed[i % seed.len()];
            }
            key.to_vec()
        }).build())
        .plugin(tauri_plugin_deep_link::init())
        .plugin(tauri_plugin_updater::Builder::new().build())
        .invoke_handler(tauri::generate_handler![
            local_driver_invoke,
            voyagent_store_session,
            voyagent_load_session,
            voyagent_clear_session,
            check_for_updates,
        ])
        .run(tauri::generate_context!())
        .expect("error while running Voyagent desktop");
}
