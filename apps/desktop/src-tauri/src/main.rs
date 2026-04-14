// Tauri 2 entry point for the Voyagent desktop shell.
//
// This file stays intentionally small: all command implementations live in
// the `commands` module, and we use the tauri-plugin-shell / dialog plugins
// for OS-level shell and native dialog access. Filesystem is deliberately
// not broadly permitted in v0 — individual driver sidecars will request
// scoped FS access later.

// On Windows, hide the console window in release builds.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod commands;

use commands::local_driver::local_driver_invoke;

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_dialog::init())
        .invoke_handler(tauri::generate_handler![local_driver_invoke])
        .run(tauri::generate_context!())
        .expect("error while running Voyagent desktop");
}
