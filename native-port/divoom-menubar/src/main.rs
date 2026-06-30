//! divoom-menubar — the native (Rust) menubar agent. A windowless tray app that
//! polls divoomd over the NDJSON socket for status + active devices and launches
//! the Python pywebview dashboard. Replaces the pyobjc menubar (`divoom_menubar/`)
//! while the desktop UI stays Python and the daemon stays Rust.
//!
//! Built on tao (event loop) + tray-icon. tray-icon needs an event loop on the
//! main thread; tao gives the classic run() closure. We poll the daemon on a
//! WaitUntil timer and forward tray/menu events through the loop proxy.

mod daemon;
mod launch;
mod tray;

use std::time::{Duration, Instant};

use tao::event::{Event, StartCause};
use tao::event_loop::{ControlFlow, EventLoopBuilder};
use tray_icon::menu::MenuEvent;

use tray::{Tray, TrayAction};

/// Menu clicks forwarded into the loop so it wakes on interaction.
enum UserEvent {
    Menu(MenuEvent),
}

const POLL: Duration = Duration::from_secs(2);

fn main() {
    #[allow(unused_mut)]
    let mut event_loop = EventLoopBuilder::<UserEvent>::with_user_event().build();
    // macOS: run as a menubar agent (no Dock icon).
    #[cfg(target_os = "macos")]
    {
        use tao::platform::macos::{ActivationPolicy, EventLoopExtMacOS};
        event_loop.set_activation_policy(ActivationPolicy::Accessory);
    }

    // Forward menu events to the loop so it wakes on each click.
    let proxy = event_loop.create_proxy();
    MenuEvent::set_event_handler(Some(move |e| {
        let _ = proxy.send_event(UserEvent::Menu(e));
    }));

    let mut tray: Option<Tray> = None;

    event_loop.run(move |event, _target, control_flow| {
        match event {
            // Create the tray once the loop is actually running (tray-icon issue #90).
            Event::NewEvents(StartCause::Init) => {
                tray = Tray::build();
                if let Some(t) = tray.as_mut() {
                    t.poll_daemon();
                }
                macos_wake();
                *control_flow = ControlFlow::WaitUntil(Instant::now() + POLL);
            }
            // Timer tick → refresh status/devices.
            Event::NewEvents(StartCause::ResumeTimeReached { .. }) => {
                if let Some(t) = tray.as_mut() {
                    t.poll_daemon();
                }
                *control_flow = ControlFlow::WaitUntil(Instant::now() + POLL);
            }
            Event::UserEvent(UserEvent::Menu(ev)) => {
                let quit = tray
                    .as_mut()
                    .and_then(|t| t.on_menu(&ev))
                    .map(|a| matches!(a, TrayAction::Quit))
                    .unwrap_or(false);
                if quit {
                    tray.take(); // drop the status item before exiting
                    *control_flow = ControlFlow::Exit;
                } else {
                    *control_flow = ControlFlow::WaitUntil(Instant::now() + POLL);
                }
            }
            _ => {}
        }
    })
}

/// macOS: nudge the main run loop so the status item paints on first show.
#[cfg(target_os = "macos")]
fn macos_wake() {
    use objc2_core_foundation::CFRunLoop;
    if let Some(rl) = CFRunLoop::main() {
        rl.wake_up();
    }
}

#[cfg(not(target_os = "macos"))]
fn macos_wake() {}
