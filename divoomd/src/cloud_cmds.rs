//! Top-level daemon cloud commands (gallery + credentials). Split out of
//! `daemon.rs` to keep it under the 500-line house limit. These don't touch the
//! device — they call `crate::cloud` / `crate::cloud_store` directly.

use serde_json::{json, Value};

use crate::protocol::{err_reply, Request};

/// Handle a cloud command. The caller routes only the cloud command names here.
pub async fn handle(command: &str, req: &Request) -> Value {
    match command {
        "fetch_gallery" => {
            let classify = match req.args.get("classify").and_then(|v| v.as_i64()) {
                Some(c) => c,
                None => return err_reply("fetch_gallery requires 'classify'"),
            };
            let limit = req.args.get("limit").and_then(|v| v.as_i64()).unwrap_or(30);
            let file_sort = req.args.get("file_sort").and_then(|v| v.as_i64()).unwrap_or(1);
            let file_size = req.args.get("file_size").and_then(|v| v.as_i64()).unwrap_or(127);
            match crate::cloud::fetch_gallery(classify, limit, file_sort, file_size).await {
                Ok(res) => json!({ "success": true, "result": res }),
                Err(e) => err_reply(&e),
            }
        }

        "save_credentials" => {
            let email = req.args.get("email").and_then(|v| v.as_str()).unwrap_or("");
            let password = req.args.get("password").and_then(|v| v.as_str()).unwrap_or("");
            if email.is_empty() || password.is_empty() {
                return err_reply("save_credentials requires 'email' and 'password'");
            }
            match crate::cloud_store::save_config(email, password) {
                Ok(()) => match crate::cloud::get_credentials(true).await {
                    Ok(creds) => json!({ "success": true, "email": creds.email, "user_id": creds.user_id }),
                    Err(e) => err_reply(&format!("saved, but login failed: {e}")),
                },
                Err(e) => err_reply(&e),
            }
        }

        "get_credentials" => {
            let force = req.args.get("force_refresh").and_then(|v| v.as_bool()).unwrap_or(false);
            match crate::cloud::get_credentials(force).await {
                Ok(creds) => json!({
                    "success": true,
                    "token": creds.token,
                    "user_id": creds.user_id,
                    "email": creds.email,
                    "utc": creds.utc,
                }),
                Err(e) => err_reply(&e),
            }
        }

        "get_cached_credentials" => match crate::cloud::get_cached_credentials() {
            Some(creds) => json!({
                "success": true,
                "credentials": {
                    "token": creds.token,
                    "user_id": creds.user_id,
                    "email": creds.email,
                    "utc": creds.utc,
                }
            }),
            None => json!({ "success": true, "credentials": serde_json::Value::Null }),
        },

        other => err_reply(&format!("not a cloud command: {other}")),
    }
}
