//! Daemon socket client. The UI is a pure client of `divoomd` over the same
//! NDJSON unix-socket protocol the Python GUI used (`{"command","args","token"?}`
//! + `\n`, one JSON reply per line). All socket I/O runs on a background worker
//! thread; the UI talks to it over channels and never blocks on the socket.
//!
//! Cross-platform: macOS/Linux use the unix socket. Windows uses the daemon's
//! TCP+token transport (R54) — wired in a later phase; this module is structured
//! so only `connect()` changes.

use std::io::{BufRead, BufReader, Write};
use std::sync::mpsc::{self, Receiver, RecvTimeoutError, Sender};
use std::time::Duration;

use serde_json::{json, Value};

pub const SOCKET_PATH: &str = "/tmp/divoom.sock";
const POLL_INTERVAL: Duration = Duration::from_secs(2);

/// Commands the UI sends to the worker.
pub enum Cmd {
    Refresh,
    Scan,
    Connect(String),
    SetBrightness(u8),
    SetVolume(u8),
    /// Escape hatch / future tabs: a raw device_call.
    DeviceCall { method: String, args: Value },
}

#[derive(Default, Clone, Debug)]
pub struct Device {
    pub name: String,
    pub address: String,
}

/// Snapshots the worker pushes back to the UI.
pub enum Update {
    Status { connected: bool, uptime_s: u64, detail: String },
    Devices(Vec<Device>),
    Error(String),
    Info(String),
}

pub struct DaemonHandle {
    pub tx: Sender<Cmd>,
    pub rx: Receiver<Update>,
}

impl DaemonHandle {
    pub fn send(&self, cmd: Cmd) {
        let _ = self.tx.send(cmd);
    }
}

/// Spawn the worker + subscriber threads and return the channel handle.
pub fn start() -> DaemonHandle {
    let (cmd_tx, cmd_rx) = mpsc::channel::<Cmd>();
    let (upd_tx, upd_rx) = mpsc::channel::<Update>();
    let sub_tx = upd_tx.clone();
    std::thread::Builder::new()
        .name("divoom-daemon-client".into())
        .spawn(move || worker(cmd_rx, upd_tx))
        .expect("spawn daemon client thread");
    std::thread::Builder::new()
        .name("divoom-daemon-events".into())
        .spawn(move || subscriber(sub_tx))
        .expect("spawn daemon event thread");
    DaemonHandle { tx: cmd_tx, rx: upd_rx }
}

/// Stream daemon events (status pushes) over a dedicated `subscribe` connection,
/// reconnecting on drop. Complements the worker's slower status poll.
fn subscriber(upd: Sender<Update>) {
    loop {
        let _ = subscribe_once(&upd);
        std::thread::sleep(Duration::from_secs(3)); // reconnect backoff
    }
}

fn subscribe_once(upd: &Sender<Update>) -> std::io::Result<()> {
    let (mut write, read) = <ConnStream as ConnConnect>::open()?;
    write.write_all(b"{\"command\":\"subscribe\",\"args\":{}}\n")?;
    write.flush()?;
    let mut reader = BufReader::new(read);
    let mut line = String::new();
    loop {
        line.clear();
        if reader.read_line(&mut line)? == 0 {
            return Ok(()); // daemon closed → caller reconnects
        }
        if let Ok(v) = serde_json::from_str::<Value>(&line) {
            if let Some(state) = v.get("state").and_then(|x| x.as_str()) {
                let _ = upd.send(Update::Status {
                    connected: true,
                    uptime_s: 0,
                    detail: state.to_string(),
                });
            }
        }
    }
}

fn worker(cmd_rx: Receiver<Cmd>, upd: Sender<Update>) {
    let mut conn: Option<Conn> = None;
    refresh(&mut conn, &upd);
    loop {
        match cmd_rx.recv_timeout(POLL_INTERVAL) {
            Ok(cmd) => handle(cmd, &mut conn, &upd),
            Err(RecvTimeoutError::Timeout) => refresh(&mut conn, &upd), // live status poll
            Err(RecvTimeoutError::Disconnected) => break,              // UI gone
        }
    }
}

fn handle(cmd: Cmd, conn: &mut Option<Conn>, upd: &Sender<Update>) {
    match cmd {
        Cmd::Refresh => refresh(conn, upd),
        Cmd::Scan => {
            match call(conn, "scan", json!({})) {
                Ok(v) => upd_devices(&v, upd),
                Err(e) => err(upd, format!("scan failed: {e}")),
            }
        }
        Cmd::Connect(mac) => match call(conn, "connect", json!({ "mac": mac })) {
            Ok(_) => {
                let _ = upd.send(Update::Info("connected".into()));
                refresh(conn, upd);
            }
            Err(e) => err(upd, format!("connect failed: {e}")),
        },
        Cmd::SetBrightness(n) => device_call(conn, upd, "device.set_brightness", json!([n])),
        Cmd::SetVolume(n) => device_call(conn, upd, "music.set_volume", json!([n])),
        Cmd::DeviceCall { method, args } => device_call(conn, upd, &method, args),
    }
}

fn device_call(conn: &mut Option<Conn>, upd: &Sender<Update>, method: &str, args: Value) {
    let req = json!({ "method": method, "args": args });
    if let Err(e) = call(conn, "device_call", req) {
        err(upd, format!("{method} failed: {e}"));
    }
}

fn refresh(conn: &mut Option<Conn>, upd: &Sender<Update>) {
    match call(conn, "get_status", json!({})) {
        Ok(v) => {
            let uptime_s = v.get("uptime_s").and_then(|x| x.as_u64()).unwrap_or(0);
            let state = v.get("state").and_then(|x| x.as_str()).unwrap_or("idle");
            let _ = upd.send(Update::Status {
                connected: true,
                uptime_s,
                detail: state.to_string(),
            });
        }
        Err(e) => {
            let _ = upd.send(Update::Status {
                connected: false,
                uptime_s: 0,
                detail: format!("daemon not reachable: {e}"),
            });
        }
    }
}

fn upd_devices(v: &Value, upd: &Sender<Update>) {
    let devs = v
        .get("devices")
        .and_then(|d| d.as_array())
        .map(|arr| {
            arr.iter()
                .map(|d| Device {
                    name: d.get("name").and_then(|x| x.as_str()).unwrap_or("").to_string(),
                    address: d
                        .get("address")
                        .or_else(|| d.get("mac"))
                        .and_then(|x| x.as_str())
                        .unwrap_or("")
                        .to_string(),
                })
                .collect()
        })
        .unwrap_or_default();
    let _ = upd.send(Update::Devices(devs));
}

fn err(upd: &Sender<Update>, msg: String) {
    let _ = upd.send(Update::Error(msg));
}

/// Send one request, reconnecting once if the cached connection is stale.
fn call(conn: &mut Option<Conn>, command: &str, args: Value) -> Result<Value, String> {
    if conn.is_none() {
        *conn = Some(Conn::connect().map_err(|e| e.to_string())?);
    }
    let c = conn.as_mut().unwrap();
    match c.request(command, &args) {
        Ok(v) => Ok(v),
        Err(_) => {
            // Drop + retry once (daemon may have restarted).
            *conn = Some(Conn::connect().map_err(|e| e.to_string())?);
            conn.as_mut()
                .unwrap()
                .request(command, &args)
                .map_err(|e| e.to_string())
        }
    }
}

struct Conn {
    write: ConnStream,
    reader: BufReader<ConnStream>,
}

impl Conn {
    fn connect() -> std::io::Result<Conn> {
        let (write, read) = <ConnStream as ConnConnect>::open()?;
        Ok(Conn { write, reader: BufReader::new(read) })
    }

    fn request(&mut self, command: &str, args: &Value) -> std::io::Result<Value> {
        let mut line = serde_json::to_vec(&json!({ "command": command, "args": args }))?;
        line.push(b'\n');
        self.write.write_all(&line)?;
        self.write.flush()?;
        let mut buf = String::new();
        let n = self.reader.read_line(&mut buf)?;
        if n == 0 {
            return Err(std::io::Error::new(std::io::ErrorKind::UnexpectedEof, "daemon closed"));
        }
        serde_json::from_str(&buf)
            .map_err(|e| std::io::Error::new(std::io::ErrorKind::InvalidData, e))
    }
}

// --- platform connection -----------------------------------------------------
// macOS/Linux: unix socket. (Windows TCP transport lands in a later phase.)

#[cfg(unix)]
use std::os::unix::net::UnixStream;

#[cfg(unix)]
type ConnStream = UnixStream;

#[cfg(unix)]
trait ConnConnect: Sized {
    /// Returns (write half, read half) of a fresh connection.
    fn open() -> std::io::Result<(Self, Self)>;
}

#[cfg(unix)]
impl ConnConnect for UnixStream {
    fn open() -> std::io::Result<(UnixStream, UnixStream)> {
        let path = socket_path();
        let s = match UnixStream::connect(&path) {
            Ok(s) => s,
            Err(_) => {
                // Daemon not up — spawn it (production path; in dev the user runs
                // a daemon manually so the socket already exists and we skip this).
                spawn_daemon(&path);
                poll_connect(&path)?
            }
        };
        let r = s.try_clone()?;
        Ok((s, r))
    }
}

#[cfg(unix)]
fn poll_connect(path: &str) -> std::io::Result<UnixStream> {
    let deadline = std::time::Instant::now() + Duration::from_secs(4);
    loop {
        match UnixStream::connect(path) {
            Ok(s) => return Ok(s),
            Err(e) if std::time::Instant::now() >= deadline => return Err(e),
            Err(_) => std::thread::sleep(Duration::from_millis(150)),
        }
    }
}

/// Spawn `divoomd` detached, pointed at `path`. Best-effort: errors are swallowed
/// (poll_connect reports the real failure). Binary resolution mirrors the Python
/// `daemon_client.spawn_daemon`: explicit env, then next to this executable
/// (bundle), then `PATH`.
#[cfg(unix)]
fn spawn_daemon(path: &str) {
    let bin = std::env::var("DIVOOMD_BIN").ok().unwrap_or_else(|| {
        std::env::current_exe()
            .ok()
            .and_then(|exe| exe.parent().map(|d| d.join("divoomd")))
            .filter(|p| p.exists())
            .map(|p| p.to_string_lossy().into_owned())
            .unwrap_or_else(|| "divoomd".to_string())
    });
    let _ = std::process::Command::new(bin)
        .arg("--socket")
        .arg(path)
        .stdin(std::process::Stdio::null())
        .stdout(std::process::Stdio::null())
        .stderr(std::process::Stdio::null())
        .spawn();
}

fn socket_path() -> String {
    std::env::var("DIVOOM_SOCKET").unwrap_or_else(|_| SOCKET_PATH.to_string())
}
