//! Divoom cloud gallery / category / weather endpoints.
//! Split out of `cloud.rs` to keep it under the 500-line house limit.
//! Ported from `divoom_lib/cloud.py`.

use std::time::Duration;
use serde_json::{json, Value};

use crate::cloud::{get_credentials, load_virtual_device, BASE_URL, TIMEOUT_SECS, DivoomCredentials};

/// Default "Classify" for `GetCategoryFileListV2` (the pixel-art / monthly-best
/// gallery) — matches the app's own default tab (`divoom_gui/web_ui/gallery.js`
/// falls back to 18 when no tab is selected). NOT related to the clock-face
/// store, which is a different endpoint pair — see `get_clock_classify_list`/
/// `get_clock_list` below.
pub const DEFAULT_GALLERY_CLASSIFY: i64 = 18;

pub async fn fetch_gallery(
    classify: i64,
    limit: i64,
    file_sort: i64,
    file_size: i64,
) -> Result<Value, String> {
    let mut creds = get_credentials(false).await?;
    let (device_id, device_pw, _, _) = load_virtual_device();

    let client = reqwest::Client::builder()
        .timeout(Duration::from_secs(TIMEOUT_SECS))
        .user_agent("okhttp/4.12.0")
        .build()
        .map_err(|e| e.to_string())?;

    let make_request = |creds: &DivoomCredentials| -> Value {
        let mut body = json!({
            "Command": "GetCategoryFileListV2",
            "Token": creds.token,
            "UserId": creds.user_id,
            "DeviceId": device_id,
            "Classify": classify,
            "FileSort": file_sort,
            "FileType": 5,
            "FileSize": file_size,
            "Version": 19,
            "StartNum": 1,
            "EndNum": limit * 2,
            "RefreshIndex": 0
        });
        if device_pw != 0 {
            if let Some(obj) = body.as_object_mut() {
                obj.insert("DevicePassword".to_string(), json!(device_pw));
            }
        }
        body
    };

    let url = format!("{}/GetCategoryFileListV2", BASE_URL);
    let mut req_body = make_request(&creds);
    let mut resp = client.post(&url).json(&req_body).send().await
        .map_err(|e| e.to_string())?;

    let mut data: Value = resp.json().await.map_err(|e| e.to_string())?;
    let mut rc = data.get("ReturnCode").and_then(|v| v.as_i64()).unwrap_or(-1);

    if rc == 9 || rc == 10 || rc == 11 {
        creds = get_credentials(true).await?;
        req_body = make_request(&creds);
        resp = client.post(&url).json(&req_body).send().await
            .map_err(|e| e.to_string())?;
        data = resp.json().await.map_err(|e| e.to_string())?;
        rc = data.get("ReturnCode").and_then(|v| v.as_i64()).unwrap_or(-1);
    }

    if rc != 0 {
        let msg = data.get("ReturnMessage").and_then(|v| v.as_str()).unwrap_or("Unknown cloud error");
        return Err(format!("GetCategoryFileListV2 failed (RC={rc}): {msg}"));
    }

    Ok(data)
}

/// Browse a cloud gallery category (clock faces, animations, …). Returns the
/// file-list array from the response (mirrors `fetch_gallery` but returns the
/// raw list rather than the whole response).
pub async fn get_category_file_list(classify: i64, limit: i64) -> Result<Value, String> {
    let mut creds = get_credentials(false).await?;
    let (device_id, device_pw, _, _) = load_virtual_device();

    let client = reqwest::Client::builder()
        .timeout(Duration::from_secs(TIMEOUT_SECS))
        .user_agent("okhttp/4.12.0")
        .build()
        .map_err(|e| e.to_string())?;

    let make_request = |creds: &DivoomCredentials| -> Value {
        let mut body = json!({
            "Command": "GetCategoryFileListV2",
            "Token": creds.token,
            "UserId": creds.user_id,
            "DeviceId": device_id,
            "Classify": classify,
            "FileSort": 0,
            "FileType": 5,
            "FileSize": 0,
            "Version": 19,
            "StartNum": 1,
            "EndNum": limit * 2,
            "RefreshIndex": 0,
        });
        if device_pw != 0 {
            if let Some(obj) = body.as_object_mut() {
                obj.insert("DevicePassword".to_string(), json!(device_pw));
            }
        }
        body
    };

    let url = format!("{}/GetCategoryFileListV2", BASE_URL);
    let mut req_body = make_request(&creds);
    let mut resp = client.post(&url).json(&req_body).send().await
        .map_err(|e| e.to_string())?;
    let mut data: Value = resp.json().await.map_err(|e| e.to_string())?;
    let mut rc = data.get("ReturnCode").and_then(|v| v.as_i64()).unwrap_or(-1);

    if rc == 9 || rc == 10 || rc == 11 {
        creds = get_credentials(true).await?;
        req_body = make_request(&creds);
        resp = client.post(&url).json(&req_body).send().await
            .map_err(|e| e.to_string())?;
        data = resp.json().await.map_err(|e| e.to_string())?;
        rc = data.get("ReturnCode").and_then(|v| v.as_i64()).unwrap_or(-1);
    }

    if rc != 0 {
        let msg = data.get("ReturnMessage").and_then(|v| v.as_str()).unwrap_or("Unknown cloud error");
        return Err(format!("GetCategoryFileListV2 failed (RC={rc}): {msg}"));
    }
    let list = data.get("FileList").cloned()
        .or_else(|| data.get("List").cloned())
        .unwrap_or(Value::Array(vec![]));
    Ok(list)
}

/// Search weather cities (Weather/SearchCity) by keyword. Returns the city list.
pub async fn search_weather_city(keyword: &str) -> Result<Value, String> {
    let mut creds = get_credentials(false).await?;
    let (device_id, device_pw, _, _) = load_virtual_device();

    let client = reqwest::Client::builder()
        .timeout(Duration::from_secs(TIMEOUT_SECS))
        .user_agent("okhttp/4.12.0")
        .build()
        .map_err(|e| e.to_string())?;

    let make_request = |creds: &DivoomCredentials| -> Value {
        let mut body = json!({
            "Command": "Weather/SearchCity",
            "Token": creds.token,
            "UserId": creds.user_id,
            "DeviceId": device_id,
            "KeyWord": keyword,
        });
        if device_pw != 0 {
            if let Some(obj) = body.as_object_mut() {
                obj.insert("DevicePassword".to_string(), json!(device_pw));
            }
        }
        body
    };

    let url = format!("{}/Weather/SearchCity", BASE_URL);
    let mut req_body = make_request(&creds);
    let mut resp = client.post(&url).json(&req_body).send().await
        .map_err(|e| e.to_string())?;
    let mut data: Value = resp.json().await.map_err(|e| e.to_string())?;
    let mut rc = data.get("ReturnCode").and_then(|v| v.as_i64()).unwrap_or(-1);

    // Same expired-token family (RC 9/10/11) that fetch_gallery/get_category_file_list
    // already retry on — this endpoint was missing the self-heal.
    if rc == 9 || rc == 10 || rc == 11 {
        creds = get_credentials(true).await?;
        req_body = make_request(&creds);
        resp = client.post(&url).json(&req_body).send().await
            .map_err(|e| e.to_string())?;
        data = resp.json().await.map_err(|e| e.to_string())?;
        rc = data.get("ReturnCode").and_then(|v| v.as_i64()).unwrap_or(-1);
    }

    if rc != 0 {
        let msg = data.get("ReturnMessage").and_then(|v| v.as_str()).unwrap_or("Unknown cloud error");
        return Err(format!("Weather/SearchCity failed (RC={rc}): {msg}"));
    }
    let list = data.get("CityList").cloned()
        .or_else(|| data.get("List").cloned())
        .unwrap_or(Value::Array(vec![]));
    Ok(list)
}

// ── clock-face store (Channel/StoreClockGetClassify + …GetList) ────────────
//
// Confirmed against the decompiled APK 2026-07-13
// (references/apk/decompiled_src/sources/com/divoom/Divoom/view/fragment/
// channelWifi/model/WifiChannelModel.java, method R()): the clock-face store
// is NOT browsed via GetCategoryFileListV2 (that's the pixel-art/monthly-best
// gallery — confirmed by its own callers, all in CloudGalleriaFragment/
// CloudVerify*/FillGameModel, none clock-related). It's a dedicated two-call
// flow: fetch the classify (category) list, then fetch clocks for one
// classify id. The app's own default flow uses Flag=0 and the FIRST classify
// entry returned. Field names below are taken verbatim from the APK's
// MyClockStoreClockGet{Classify,List}{Request,Response}.java classes.
//
// STILL OPEN (see divoom_lib/cloud.py's mirror of this comment for the full
// writeup): a live round-trip against Channel/StoreClockGetClassify returns
// RC=12 (HTTP_REQUEST_EMPTY) — reproduced with both a real account and guest
// auth, so not a token problem (GetCategoryFileListV2/Weather::SearchCity
// both succeed with the same credentials). `BaseParams._postSync` — the
// method that builds the actual generic POST — wasn't decompilable (JADX
// stub), so the exact wire gap can't be confirmed from source; possibly the
// server requires a real bound-device DeviceId this env doesn't have. Code
// here is correct per the app's request/response CLASSES; end-to-end proof
// is unresolved.

/// Fetch the clock-face store's category list (`ClassifyId`/`ClassifyName`).
pub async fn get_clock_classify_list() -> Result<Value, String> {
    let mut creds = get_credentials(false).await?;
    let (device_id, device_pw, _, _) = load_virtual_device();

    let client = reqwest::Client::builder()
        .timeout(Duration::from_secs(TIMEOUT_SECS))
        .user_agent("okhttp/4.12.0")
        .build()
        .map_err(|e| e.to_string())?;

    let make_request = |creds: &DivoomCredentials| -> Value {
        let mut body = json!({
            "Command": "Channel/StoreClockGetClassify",
            "Token": creds.token,
            "UserId": creds.user_id,
            "DeviceId": device_id,
            "StartNum": 1,
            "EndNum": 30,
        });
        if device_pw != 0 {
            if let Some(obj) = body.as_object_mut() {
                obj.insert("DevicePassword".to_string(), json!(device_pw));
            }
        }
        body
    };

    let url = format!("{}/Channel/StoreClockGetClassify", BASE_URL);
    let mut req_body = make_request(&creds);
    let mut resp = client.post(&url).json(&req_body).send().await
        .map_err(|e| e.to_string())?;
    let mut data: Value = resp.json().await.map_err(|e| e.to_string())?;
    let mut rc = data.get("ReturnCode").and_then(|v| v.as_i64()).unwrap_or(-1);

    if rc == 9 || rc == 10 || rc == 11 {
        creds = get_credentials(true).await?;
        req_body = make_request(&creds);
        resp = client.post(&url).json(&req_body).send().await
            .map_err(|e| e.to_string())?;
        data = resp.json().await.map_err(|e| e.to_string())?;
        rc = data.get("ReturnCode").and_then(|v| v.as_i64()).unwrap_or(-1);
    }

    if rc != 0 {
        let msg = data.get("ReturnMessage").and_then(|v| v.as_str()).unwrap_or("Unknown cloud error");
        return Err(format!("Channel/StoreClockGetClassify failed (RC={rc}): {msg}"));
    }
    Ok(data.get("ClassifyList").cloned().unwrap_or(Value::Array(vec![])))
}

/// Fetch clock faces (`ClockId`/`ClockName`/`ImagePixelId`/…) for one classify id.
pub async fn get_clock_list(classify_id: i64, flag: i64, limit: i64) -> Result<Value, String> {
    let mut creds = get_credentials(false).await?;
    let (device_id, device_pw, _, _) = load_virtual_device();

    let client = reqwest::Client::builder()
        .timeout(Duration::from_secs(TIMEOUT_SECS))
        .user_agent("okhttp/4.12.0")
        .build()
        .map_err(|e| e.to_string())?;

    let make_request = |creds: &DivoomCredentials| -> Value {
        let mut body = json!({
            "Command": "Channel/StoreClockGetList",
            "Token": creds.token,
            "UserId": creds.user_id,
            "DeviceId": device_id,
            "ClassifyId": classify_id,
            "Flag": flag,
            "StartNum": 1,
            "EndNum": limit,
        });
        if device_pw != 0 {
            if let Some(obj) = body.as_object_mut() {
                obj.insert("DevicePassword".to_string(), json!(device_pw));
            }
        }
        body
    };

    let url = format!("{}/Channel/StoreClockGetList", BASE_URL);
    let mut req_body = make_request(&creds);
    let mut resp = client.post(&url).json(&req_body).send().await
        .map_err(|e| e.to_string())?;
    let mut data: Value = resp.json().await.map_err(|e| e.to_string())?;
    let mut rc = data.get("ReturnCode").and_then(|v| v.as_i64()).unwrap_or(-1);

    if rc == 9 || rc == 10 || rc == 11 {
        creds = get_credentials(true).await?;
        req_body = make_request(&creds);
        resp = client.post(&url).json(&req_body).send().await
            .map_err(|e| e.to_string())?;
        data = resp.json().await.map_err(|e| e.to_string())?;
        rc = data.get("ReturnCode").and_then(|v| v.as_i64()).unwrap_or(-1);
    }

    if rc != 0 {
        let msg = data.get("ReturnMessage").and_then(|v| v.as_str()).unwrap_or("Unknown cloud error");
        return Err(format!("Channel/StoreClockGetList failed (RC={rc}): {msg}"));
    }
    Ok(data.get("ClockList").cloned().unwrap_or(Value::Array(vec![])))
}

/// Browse the cloud clock-face store, mirroring the app's own default flow
/// (`WifiChannelModel.R()` in the decompiled APK): with no `classify_id`,
/// fetch the classify list and use its first entry.
pub async fn list_clock_faces(classify_id: Option<i64>, limit: i64) -> Result<Value, String> {
    let classify_id = match classify_id {
        Some(id) => id,
        None => {
            let classifies = get_clock_classify_list().await?;
            match classifies.as_array().and_then(|a| a.first()) {
                Some(first) => first.get("ClassifyId").and_then(|v| v.as_i64()).unwrap_or(0),
                None => return Ok(Value::Array(vec![])),
            }
        }
    };
    get_clock_list(classify_id, 0, limit).await
}
