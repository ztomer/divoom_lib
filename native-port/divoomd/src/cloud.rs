//! Divoom cloud API authentication and token caching.
//! Ported from `divoom_lib/divoom_auth.py`.

use std::path::PathBuf;
use std::sync::Mutex;
use std::time::{Duration, SystemTime, UNIX_EPOCH};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use hmac::{Hmac, Mac};
use md5::{Md5, Digest};

type HmacMd5 = Hmac<Md5>;

const BASE_URL: &str = "https://appin.divoom-gz.com";
const HMAC_KEY: &[u8] = b"DivoomBluetoothDevice<>?";
const TIMEOUT_SECS: u64 = 15;
const AUTH_FAIL_COOLDOWN_SECS: u64 = 120;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DivoomCredentials {
    pub token: i64,
    pub user_id: i64,
    pub email: String,
    pub utc: i64,
}

impl DivoomCredentials {
    pub fn is_valid(&self) -> bool {
        self.token != 0 && self.user_id != 0
    }
}

use std::sync::OnceLock;
static LAST_AUTH_FAIL_AT: OnceLock<Mutex<Option<SystemTime>>> = OnceLock::new();

fn last_auth_fail_at() -> &'static Mutex<Option<SystemTime>> {
    LAST_AUTH_FAIL_AT.get_or_init(|| Mutex::new(None))
}

pub(crate) fn config_dir() -> Option<PathBuf> {
    let home = std::env::var("HOME").ok()?;
    Some(PathBuf::from(home).join(".config").join("divoom-control"))
}

fn config_file_path() -> Option<PathBuf> {
    Some(config_dir()?.join("config.ini"))
}

fn cache_file_path() -> Option<PathBuf> {
    Some(config_dir()?.join("auth_token.json"))
}

fn md5_hex(s: &str) -> String {
    let mut hasher = Md5::new();
    hasher.update(s.as_bytes());
    let result = hasher.finalize();
    result.iter().map(|b| format!("{:02x}", b)).collect()
}

fn hmac_md5_hex(message: &str) -> String {
    let mut mac = HmacMd5::new_from_slice(HMAC_KEY).expect("HMAC can take key of any size");
    mac.update(message.as_bytes());
    let result = mac.finalize();
    result.into_bytes().iter().map(|b| format!("{:02x}", b)).collect()
}

fn load_config() -> (String, String) {
    let path = match config_file_path() {
        Some(p) => p,
        None => return (String::new(), String::new()),
    };
    if !path.exists() {
        return (String::new(), String::new());
    }
    let content = match std::fs::read_to_string(path) {
        Ok(c) => c,
        Err(_) => return (String::new(), String::new()),
    };
    let mut email = String::new();
    let mut password = String::new();
    let mut in_divoom_section = false;
    for line in content.lines() {
        let trimmed = line.trim();
        if trimmed.starts_with('[') && trimmed.ends_with(']') {
            let section = &trimmed[1..trimmed.len() - 1];
            in_divoom_section = section.eq_ignore_ascii_case("divoom");
        } else if in_divoom_section {
            if let Some(pos) = trimmed.find('=') {
                let key = trimmed[..pos].trim();
                let val = trimmed[pos + 1..].trim();
                if key.eq_ignore_ascii_case("email") {
                    email = val.to_string();
                } else if key.eq_ignore_ascii_case("password") {
                    password = val.to_string();
                }
            }
        }
    }
    (email, password)
}

fn save_cache(creds: &DivoomCredentials) -> Result<(), String> {
    let path = cache_file_path().ok_or("cannot find cache directory")?;
    if let Some(parent) = path.parent() {
        let _ = std::fs::create_dir_all(parent);
    }
    let now = SystemTime::now().duration_since(UNIX_EPOCH).unwrap_or_default().as_secs();
    let val = json!({
        "token": creds.token,
        "user_id": creds.user_id,
        "email": creds.email,
        "utc": creds.utc,
        "saved_at": now,
    });
    let data = serde_json::to_string_pretty(&val).map_err(|e| e.to_string())?;

    // Atomic write (simulate write + rename + 0o600 mode)
    let temp_path = path.with_extension("tmp");
    std::fs::write(&temp_path, data).map_err(|e| e.to_string())?;
    
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        let _ = std::fs::set_permissions(&temp_path, std::fs::Permissions::from_mode(0o600));
    }
    
    std::fs::rename(temp_path, path).map_err(|e| e.to_string())?;
    Ok(())
}

fn load_cache() -> Option<DivoomCredentials> {
    let path = cache_file_path()?;
    if !path.exists() {
        return None;
    }
    let content = std::fs::read_to_string(path).ok()?;
    let val: Value = serde_json::from_str(&content).ok()?;
    let saved_at = val.get("saved_at")?.as_u64()?;
    let now = SystemTime::now().duration_since(UNIX_EPOCH).unwrap_or_default().as_secs();
    
    // Cache for 23 hours (23 * 3600 seconds)
    if now > saved_at && now - saved_at > 23 * 3600 {
        return None;
    }

    let creds = DivoomCredentials {
        token: val.get("token")?.as_i64()?,
        user_id: val.get("user_id")?.as_i64()?,
        email: val.get("email").and_then(|v| v.as_str()).unwrap_or("").to_string(),
        utc: val.get("utc").and_then(|v| v.as_i64()).unwrap_or(0),
    };
    if creds.is_valid() {
        Some(creds)
    } else {
        None
    }
}

async fn post_cloud(path: &str, body: &Value) -> Result<Value, String> {
    let client = reqwest::Client::new();
    let url = format!("{}/{}", BASE_URL, path);
    let res = client.post(&url)
        .header("Content-Type", "application/json; charset=utf-8")
        .header("Connection", "close")
        .header("User-Agent", "okhttp/4.12.0")
        .json(body)
        .timeout(Duration::from_secs(TIMEOUT_SECS))
        .send()
        .await
        .map_err(|e| e.to_string())?;

    let text = res.text().await.map_err(|e| e.to_string())?;
    let val: Value = serde_json::from_str(&text).map_err(|e| e.to_string())?;
    Ok(val)
}

async fn login_email(email: &str, pwhash: &str) -> Result<DivoomCredentials, String> {
    let body = json!({
        "Email": email,
        "Password": pwhash,
        "TimeZone": "+0",
        "CountryISOCode": "US",
        "Language": "en",
        "Token": 0,
        "UserId": 0,
        "DeviceId": 0,
    });
    let data = post_cloud("UserLogin", &body).await?;
    let rc = data.get("ReturnCode").and_then(|v| v.as_i64()).unwrap_or(-1);
    if rc == 4 {
        return Err(format!("Email not registered: {email}"));
    }
    if rc == 5 {
        return Err("Password is incorrect".to_string());
    }
    if rc != 0 {
        return Err(format!("UserLogin failed: RC={rc} msg={:?}", data.get("ReturnMessage")));
    }
    let token = data.get("Token").and_then(|v| v.as_i64()).unwrap_or(0);
    let user_id = data.get("UserId").and_then(|v| v.as_i64()).unwrap_or(0);
    Ok(DivoomCredentials {
        token,
        user_id,
        email: email.to_string(),
        utc: 0,
    })
}

async fn get_server_utc() -> i64 {
    let body = json!({"Command": "APP/GetServerUTC"});
    if let Ok(data) = post_cloud("APP/GetServerUTC", &body).await {
        if let Some(utc) = data.get("UTC").and_then(|v| v.as_i64()) {
            return utc;
        }
    }
    SystemTime::now().duration_since(UNIX_EPOCH).unwrap_or_default().as_secs() as i64
}

async fn login_guest() -> Result<DivoomCredentials, String> {
    let utc = get_server_utc().await;
    let utc_str = utc.to_string();
    let utc_encrypt = hmac_md5_hex(&utc_str);
    let body = json!({
        "Command": "User/NewGuest",
        "UTC": utc_str,
        "UTCEncrypt": utc_encrypt,
        "Token": 0,
        "UserId": 0,
    });
    let data = post_cloud("User/NewGuest", &body).await?;
    let rc = data.get("ReturnCode").and_then(|v| v.as_i64()).unwrap_or(-1);
    if rc != 0 {
        return Err(format!("UserNewGuest failed: RC={rc} msg={:?}", data.get("ReturnMessage")));
    }
    let token = data.get("Token").and_then(|v| v.as_i64()).unwrap_or(0);
    let user_id = data.get("UserId").and_then(|v| v.as_i64()).unwrap_or(0);
    Ok(DivoomCredentials {
        token,
        user_id,
        email: String::new(),
        utc,
    })
}

pub fn get_cached_credentials() -> Option<DivoomCredentials> {
    load_cache()
}

pub async fn get_credentials(force_refresh: bool) -> Result<DivoomCredentials, String> {
    if !force_refresh {
        if let Some(cached) = load_cache() {
            return Ok(cached);
        }
    }

    let (email, password) = load_config();
    let cooldown_expired = {
        let guard = last_auth_fail_at().lock().unwrap();
        if let Some(t) = *guard {
            t.elapsed().unwrap_or_default() > Duration::from_secs(AUTH_FAIL_COOLDOWN_SECS)
        } else {
            true
        }
    };

    if !email.is_empty() && !password.is_empty() && (force_refresh || cooldown_expired) {
        let pwhash = md5_hex(&password);
        match login_email(&email, &pwhash).await {
            Ok(creds) => {
                let _ = save_cache(&creds);
                return Ok(creds);
            }
            Err(e) => {
                // fall back to guest
                eprintln!("[Wrn] Email login failed: {} — falling back to guest", e);
            }
        }
    }

    if !cooldown_expired {
        let remaining = {
            let guard = last_auth_fail_at().lock().unwrap();
            let elapsed = guard.unwrap().elapsed().unwrap_or_default().as_secs();
            AUTH_FAIL_COOLDOWN_SECS.saturating_sub(elapsed)
        };
        return Err(format!("Divoom cloud auth unavailable (retry in {remaining}s)"));
    }

    match login_guest().await {
        Ok(creds) => {
            let _ = save_cache(&creds);
            Ok(creds)
        }
        Err(e) => {
            *last_auth_fail_at().lock().unwrap() = Some(SystemTime::now());
            Err(e)
        }
    }
}

fn load_virtual_device() -> (i64, String) {
    let mut device_id = 0i64;
    let mut device_pw = String::new();
    if let Some(mut path) = config_dir() {
        path.push("virtual_device.json");
        if path.exists() {
            if let Ok(content) = std::fs::read_to_string(&path) {
                if let Ok(val) = serde_json::from_str::<Value>(&content) {
                    device_id = val.get("BluetoothDeviceId").and_then(|v| v.as_i64()).unwrap_or(0);
                    device_pw = val.get("DevicePassword").and_then(|v| v.as_str()).unwrap_or("").to_string();
                }
            }
        }
    }
    (device_id, device_pw)
}

pub async fn fetch_gallery(
    classify: i64,
    limit: i64,
    file_sort: i64,
    file_size: i64,
) -> Result<Value, String> {
    let mut creds = get_credentials(false).await?;
    let (device_id, device_pw) = load_virtual_device();

    let client = reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(TIMEOUT_SECS))
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
        if !device_pw.is_empty() {
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

#[allow(dead_code)]
pub(crate) static TEST_MUTEX: OnceLock<Mutex<()>> = OnceLock::new();

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
    use tempfile::TempDir;

    fn lock_test() -> std::sync::MutexGuard<'static, ()> {
        TEST_MUTEX.get_or_init(|| Mutex::new(())).lock().unwrap()
    }

    #[test]
    fn test_md5_hex_hash() {
        let hash = md5_hex("hello_world");
        assert_eq!(hash, "99b1ff8f11781541f7f89f9bd41c4a17");
    }

    #[test]
    fn test_hmac_md5_hex() {
        let hash = hmac_md5_hex("1719561234");
        assert_eq!(hash, "480343a678a9a150b8ca44580404392c");
    }

    #[test]
    fn test_load_config() {
        let _lock = lock_test();
        let temp = TempDir::new().unwrap();
        std::env::set_var("HOME", temp.path());

        let conf_dir = temp.path().join(".config").join("divoom-control");
        fs::create_dir_all(&conf_dir).unwrap();
        
        let config_ini = "[divoom]\nemail = test_user@divoom.com\npassword = test_password_123\n";
        fs::write(conf_dir.join("config.ini"), config_ini).unwrap();

        let (email, password) = load_config();
        assert_eq!(email, "test_user@divoom.com");
        assert_eq!(password, "test_password_123");
    }

    #[test]
    fn test_cache_lifecycle() {
        let _lock = lock_test();
        let temp = TempDir::new().unwrap();
        std::env::set_var("HOME", temp.path());

        assert!(get_cached_credentials().is_none());

        let creds = DivoomCredentials {
            token: 98765,
            user_id: 4321,
            email: "test_cache@divoom.com".to_string(),
            utc: 1234567,
        };

        assert!(save_cache(&creds).is_ok());

        let cached = get_cached_credentials().unwrap();
        assert_eq!(cached.token, 98765);
        assert_eq!(cached.user_id, 4321);
        assert_eq!(cached.email, "test_cache@divoom.com");
        assert_eq!(cached.utc, 1234567);

        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            let cache_file = temp.path().join(".config").join("divoom-control").join("auth_token.json");
            let metadata = fs::metadata(cache_file).unwrap();
            let mode = metadata.permissions().mode();
            assert_eq!(mode & 0o777, 0o600);
        }

        let cache_file = temp.path().join(".config").join("divoom-control").join("auth_token.json");
        let content = fs::read_to_string(&cache_file).unwrap();
        let mut val: serde_json::Value = serde_json::from_str(&content).unwrap();
        
        let now = SystemTime::now().duration_since(UNIX_EPOCH).unwrap_or_default().as_secs();
        val["saved_at"] = serde_json::Value::Number((now - 24 * 3600).into());
        fs::write(&cache_file, serde_json::to_string(&val).unwrap()).unwrap();

        assert!(get_cached_credentials().is_none());
    }

    #[tokio::test]
    async fn test_auth_failure_cooldown() {
        let _lock = lock_test();
        let temp = TempDir::new().unwrap();
        std::env::set_var("HOME", temp.path());

        *last_auth_fail_at().lock().unwrap() = None;

        *last_auth_fail_at().lock().unwrap() = Some(SystemTime::now());

        let res = get_credentials(false).await;
        assert!(res.is_err());
        let err = res.unwrap_err();
        assert!(err.contains("Divoom cloud auth unavailable"));
        
        let long_ago = SystemTime::now() - Duration::from_secs(130);
        *last_auth_fail_at().lock().unwrap() = Some(long_ago);

        let res = get_credentials(false).await;
        let err = res.unwrap_err();
        assert!(!err.contains("Divoom cloud auth unavailable"));
    }
}

