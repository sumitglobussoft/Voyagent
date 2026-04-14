// Tauri command modules for the Voyagent desktop shell.
//
// Each submodule owns one or more `#[tauri::command]` functions. Keep the
// top-level `main.rs` wiring thin — add new commands here and register
// them in the `tauri::generate_handler!` macro call.

pub mod auth;
pub mod local_driver;
pub mod updater;
