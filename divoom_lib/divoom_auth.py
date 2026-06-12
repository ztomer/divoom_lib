#!/usr/bin/env python3
"""
divoom_auth.py — Divoom cloud API authentication module.

Supports two authentication paths:
  1. Email/password login (UserLogin) — preferred, uses config.ini credentials
  2. Guest login (User/NewGuest) — fallback, no account needed

HMAC-MD5 UTC signing discovered via APK static analysis (P2/a.java):
  key = b"DivoomBluetoothDevice<>?"
  utc_encrypt = hmac_md5(key, str(utc))
"""

import configparser
import hashlib
import hmac
import json
import time
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from pathlib import Path


def print_info(message):
    print(f"[ ==> ] {message}")

def print_wrn(message):
    print(f"[ Wrn ] {message}")

def print_err(message):
    print(f"[ Err ] {message}")

def print_ok(message):
    print(f"[ Ok  ] {message}")


BASE_URL   = "https://appin.divoom-gz.com"
HMAC_KEY   = b"DivoomBluetoothDevice<>?"  # from P2/a.java
TIMEOUT    = 15
CONFIG_FILE = Path.home() / ".config" / "divoom-control" / "config.ini"
CACHE_FILE  = Path.home() / ".config" / "divoom-control" / "auth_token.json"


@dataclass
class DivoomCredentials:
    token:   int
    user_id: int
    email:   str = ""
    utc:     int = 0

    def is_valid(self) -> bool:
        return self.token != 0 and self.user_id != 0


def _load_config() -> tuple[str, str]:
    """Read email + password from config.ini."""
    cfg = configparser.ConfigParser()
    if not CONFIG_FILE.exists():
        return "", ""
    cfg.read(CONFIG_FILE)
    email    = cfg.get("divoom", "email",    fallback="")
    password = cfg.get("divoom", "password", fallback="")
    return email, password


def _hmac_md5(message: str) -> str:
    """Compute HMAC-MD5 as lowercase hex. From P2/a.java."""
    h = hmac.new(HMAC_KEY, message.encode("utf-8"), hashlib.md5)
    return h.hexdigest()


def _md5(s: str) -> str:
    return hashlib.md5(s.encode("utf-8")).hexdigest()


def _post(path: str, body: dict) -> dict:
    url     = f"{BASE_URL}/{path}"
    payload = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "Connection":   "close",
            "User-Agent":   "okhttp/4.12.0",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


# ── Auth path 1: Email / Password ─────────────────────────────────────────────

def _login_email(email: str, password: str) -> DivoomCredentials:
    """
    POST /UserLogin with MD5-hashed password.
    From LoginServer.java z() method + UserLoginRequest.java.
    """
    print_info(f"Logging in as {email!r} ...")
    body = {
        "Email":         email,
        "Password":      _md5(password),
        "TimeZone":      "+0",
        "CountryISOCode": "US",
        "Language":      "en",
        "Token":         0,
        "UserId":        0,
        "DeviceId":      0,
    }
    data = _post("UserLogin", body)
    rc   = data.get("ReturnCode", -1)

    if rc == 4:
        raise RuntimeError(f"Email not registered: {email!r}")
    if rc == 5:
        raise RuntimeError("Password is incorrect")
    if rc != 0:
        raise RuntimeError(f"UserLogin failed: RC={rc} msg={data.get('ReturnMessage')}")

    token   = data.get("Token",  0)
    user_id = data.get("UserId", 0)
    print_ok(f"Logged in: UserId={user_id} Token={token}")
    return DivoomCredentials(token=token, user_id=user_id, email=email)


# ── Auth path 2: Guest (HMAC-UTC) ─────────────────────────────────────────────

def _get_server_utc() -> int:
    try:
        data = _post("APP/GetServerUTC", {"Command": "APP/GetServerUTC"})
        utc  = data.get("UTC", 0)
        if utc:
            print_ok(f"Server UTC: {utc}")
            return utc
    except Exception as e:
        print_wrn(f"APP/GetServerUTC failed ({e}), using local time")
    return int(time.time())


def _login_guest() -> DivoomCredentials:
    """
    HMAC-UTC guest login. From LoginServer.java q() + P2/a.java.
    """
    print_info("Attempting guest authentication ...")
    utc         = _get_server_utc()
    utc_str     = str(utc)
    utc_encrypt = _hmac_md5(utc_str)
    print_info(f"UTC={utc_str}  UTCEncrypt={utc_encrypt}")

    body = {
        "Command":    "User/NewGuest",
        "UTC":        utc_str,
        "UTCEncrypt": utc_encrypt,
        "Token":      0,
        "UserId":     0,
    }
    data = _post("User/NewGuest", body)
    rc   = data.get("ReturnCode", -1)

    if rc != 0:
        raise RuntimeError(f"UserNewGuest failed: RC={rc} msg={data.get('ReturnMessage')}")

    token   = data.get("Token",  0)
    user_id = data.get("UserId", 0)
    print_ok(f"Guest credentials: UserId={user_id} Token={token}")
    return DivoomCredentials(token=token, user_id=user_id, utc=utc)


# ── Cache ─────────────────────────────────────────────────────────────────────

def _save_cache(creds: DivoomCredentials) -> None:
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(json.dumps({
        "token":    creds.token,
        "user_id":  creds.user_id,
        "email":    creds.email,
        "utc":      creds.utc,
        "saved_at": int(time.time()),
    }, indent=2), encoding="utf-8")
    print_info(f"Credentials cached to {CACHE_FILE}")


def _load_cache() -> DivoomCredentials | None:
    if not CACHE_FILE.exists():
        return None
    try:
        data = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        age  = int(time.time()) - data.get("saved_at", 0)
        # Email login tokens seem long-lived; cache for 23 hours
        if age > 23 * 3600:
            print_info("Cached token expired (>23h), re-authenticating")
            return None
        creds = DivoomCredentials(
            token=data["token"], user_id=data["user_id"],
            email=data.get("email", ""), utc=data.get("utc", 0),
        )
        if creds.is_valid():
            print_ok(f"Using cached credentials: UserId={creds.user_id} (email={creds.email or 'guest'})")
            return creds
    except Exception as e:
        print_wrn(f"Cache load failed: {e}")
    return None


# ── Public API ────────────────────────────────────────────────────────────────

# Negative cache: after a network auth attempt fails, don't hammer the Divoom
# cloud on every subsequent call (the GUI polls cloud-backed features). Within
# the cooldown, get_credentials() fails fast without touching the network.
_AUTH_FAIL_COOLDOWN = 120  # seconds
_last_auth_fail_at: float = 0.0


def get_cached_credentials() -> DivoomCredentials | None:
    """Return valid cached credentials if present, else None. **Never** performs
    a network login and **never** raises — safe for hot/polled paths such as the
    transport-status panel, which must not initiate (or block on) a cloud login.
    """
    try:
        return _load_cache()
    except Exception as e:  # pragma: no cover - cache read is already defensive
        print_wrn(f"Cached credential read failed: {e}")
        return None


def get_credentials(force_refresh: bool = False) -> DivoomCredentials:
    """
    Obtain valid Divoom credentials.
    Priority: cached → email/password login → guest fallback.

    Raises RuntimeError if no cached token is available and a network login
    fails (or was recently failing — see the cooldown). Callers that must not
    crash on a cloud outage should use get_cached_credentials() or wrap this.
    """
    global _last_auth_fail_at

    if not force_refresh:
        cached = _load_cache()
        if cached:
            return cached

    email, password = _load_config()
    since_fail = time.time() - _last_auth_fail_at
    in_cooldown = since_fail < _AUTH_FAIL_COOLDOWN

    # R45 #2: a configured account is ALWAYS allowed to re-submit its stored
    # email/password on a genuine token expiry (force_refresh) — the creds don't
    # change, only the token does. The cooldown below only protects the guest
    # fallback / polled callers from hammering a down/changed cloud.
    if email and password and (force_refresh or not in_cooldown):
        try:
            creds = _login_email(email, password)
            _save_cache(creds)
            return creds
        except Exception as e:
            print_wrn(f"Email login failed: {e} — falling back to guest")

    # Fail fast inside the cooldown window so a down cloud can't be hammered.
    if in_cooldown:
        raise RuntimeError(
            f"Divoom cloud auth unavailable (retry in "
            f"{int(_AUTH_FAIL_COOLDOWN - since_fail)}s)"
        )

    try:
        creds = _login_guest()
    except Exception:
        _last_auth_fail_at = time.time()
        raise
    _save_cache(creds)
    return creds


if __name__ == "__main__":
    import sys
    force = "--refresh" in sys.argv
    creds = get_credentials(force_refresh=force)
    print(f"\nToken:  {creds.token}")
    print(f"UserId: {creds.user_id}")
    print(f"Email:  {creds.email or '(guest)'}")
