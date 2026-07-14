//! divoomd — native (Rust) port of the Divoom daemon.
//!
//! Built in parallel to the authoritative Python daemon (`divoom_daemon/`); the
//! Python implementation stays ground truth and this is switched in only at 100%
//! socket + hardware parity. See docs/ROADMAP.md.
//!
//! Phase 2 (protocol core) lands here first: wire framing, then models, the BLE
//! notify/response correlation, and the command queue — each pinned to the Python
//! behavior by parity tests.

pub mod autoprobe;
pub mod image_proc;
#[cfg(feature = "ble")]
pub mod ble;
#[cfg(feature = "ble")]
pub mod central;
pub mod command_queue;
pub mod commands;
pub mod daemon;
mod daemon_status;
#[cfg(feature = "ble")]
pub mod daemon_ble;
pub mod framing;
pub mod lan;
pub mod models;
pub mod native_encode;
pub mod protocol;
pub mod response;
pub mod socket_server;
pub mod device_call;
pub mod daemon_connect;
pub mod daemon_mock;
pub mod live_jobs;
pub mod wall;
pub mod art_codec;
pub mod art_hot;
pub mod art;
pub mod hot_state;
#[cfg(target_os = "macos")]
pub mod macos_notifications;
#[cfg(target_os = "macos")]
pub mod notification_db;
#[cfg(target_os = "macos")]
pub mod notification_routing;
pub mod transport;
pub mod spp;
pub mod cloud;
pub mod cloud_cmds;
pub mod cloud_store;
mod cloud_category;
pub mod mcp;
pub mod mcp_tools;
pub mod media;
pub mod monthly_best;
pub mod sync_artwork;
pub mod mock_transport;
pub mod mock_device_tests;
