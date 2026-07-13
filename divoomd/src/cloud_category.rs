//! Divoom cloud gallery / category / weather endpoints.
//! Split out of `cloud.rs` to keep it under the 500-line house limit.
//! Ported from `divoom_lib/cloud.py`.

use std::time::Duration;
use serde_json::{json, Value};

use crate::cloud::{get_credentials, load_virtual_device, BASE_URL, TIMEOUT_SECS, DivoomCredentials};

/// GetCategoryFileListV2 "Classify" for the clock-face store. VERIFY against the
/// APK — the gallery tab index the app uses for clock faces.
pub const CLOCK_FACE_CLASSIFY: i64 = 0;

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
