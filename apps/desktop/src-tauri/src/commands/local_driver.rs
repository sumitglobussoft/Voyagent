//! Local-driver seam.
//!
//! This is the single Tauri command through which the web layer reaches
//! into OS-resident drivers (Tally ODBC, GDS terminals, smart-card readers,
//! thermal printers). In v0 we return a stub response so the full call
//! path is exercisable end-to-end from the Vite side. In v1 this command
//! will dispatch on `driver` and delegate to a per-driver module that
//! implements the real protocol — for Tally, that's XML-over-HTTP to the
//! local Tally service.
//!
//! Wire protocol (TypeScript -> Rust):
//!   - driver: string     (e.g. "tally", "gds.amadeus")
//!   - method: string     (e.g. "list_ledgers", "fetch_pnr")
//!   - args:   JSON value (driver-specific)
//!
//! Response shape: a JSON object whose `status` field is one of
//!   - "ok"             — call succeeded; other fields carry payload
//!   - "not_wired_yet"  — v0 stub marker (no driver implemented yet)
//!   - "error"          — call reached the driver but failed
//!
//! Future work: swap `serde_json::Value` for a typed enum per driver, and
//! move error conversion through `thiserror` once we have real drivers.

use serde_json::{json, Value};

#[tauri::command]
pub async fn local_driver_invoke(
    driver: String,
    method: String,
    args: Value,
) -> Result<Value, String> {
    // v0: acknowledge the call so the TS bridge can verify the seam works,
    // but make it obvious that nothing is wired yet.
    Ok(json!({
        "status": "not_wired_yet",
        "driver": driver,
        "method": method,
        "args": args,
        "message": "local_driver_invoke is a v0 stub; real drivers land in v1"
    }))
}
