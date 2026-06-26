//! divoomd — the native daemon binary. Owns a unix socket and serves the NDJSON
//! protocol. Runs in parallel to the Python daemon (default socket
//! `/tmp/divoomd.sock`, distinct from the Python `/tmp/divoom.sock`) so both can
//! coexist during the port. See docs/PLANNING_NATIVE_PORT.md.
//!
//!   divoomd [--socket /path/to.sock]

use std::sync::Arc;

use divoomd::daemon::Daemon;
use divoomd::socket_server::serve;
use tokio::net::UnixListener;

const DEFAULT_SOCKET: &str = "/tmp/divoomd.sock";

fn socket_path_from_args() -> String {
    let args: Vec<String> = std::env::args().collect();
    let mut i = 1;
    while i < args.len() {
        if let Some(p) = args[i].strip_prefix("--socket=") {
            return p.to_string();
        }
        if args[i] == "--socket" && i + 1 < args.len() {
            return args[i + 1].clone();
        }
        i += 1;
    }
    DEFAULT_SOCKET.to_string()
}

/// Single-instance + stale-socket handling: if the path exists and something is
/// actually listening, another instance owns it — exit. Otherwise remove the stale
/// socket and bind. (Mirrors the Python daemon's single-instance guard intent.)
fn bind(socket_path: &str) -> std::io::Result<UnixListener> {
    if std::path::Path::new(socket_path).exists() {
        if std::os::unix::net::UnixStream::connect(socket_path).is_ok() {
            eprintln!("divoomd: another instance already owns {socket_path}");
            std::process::exit(1);
        }
        let _ = std::fs::remove_file(socket_path);
    }
    UnixListener::bind(socket_path)
}

#[tokio::main]
async fn main() {
    let socket_path = socket_path_from_args();
    let listener = match bind(&socket_path) {
        Ok(l) => l,
        Err(e) => {
            eprintln!("divoomd: cannot bind {socket_path}: {e}");
            std::process::exit(1);
        }
    };
    eprintln!("divoomd listening on {socket_path}");

    let daemon = Arc::new(Daemon::new());
    daemon.initialize_self_weak(Arc::downgrade(&daemon));
    tokio::select! {
        _ = serve(listener, daemon) => {}
        sig = shutdown_signal() => {
            eprintln!("divoomd: {sig} — shutting down");
        }
    }
    let _ = std::fs::remove_file(&socket_path);
}

/// Resolve when SIGINT or SIGTERM arrives, so the socket is unlinked on a clean
/// `kill` as well as Ctrl-C (the Python daemon handles both).
async fn shutdown_signal() -> &'static str {
    use tokio::signal::unix::{signal, SignalKind};
    let mut term = signal(SignalKind::terminate()).expect("install SIGTERM handler");
    tokio::select! {
        _ = tokio::signal::ctrl_c() => "SIGINT",
        _ = term.recv() => "SIGTERM",
    }
}
