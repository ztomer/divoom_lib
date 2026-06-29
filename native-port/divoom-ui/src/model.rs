//! UI model types (tabs, channel sub-tabs, alarm slot). Split out of `app.rs` to
//! keep that file under the 500-line house limit; re-exported from `app` so call
//! sites still use `crate::app::{Tab, Channel, ...}`.

/// Sidebar tabs. The visual reference is `divoom_gui/web_ui/index.html`.
#[derive(PartialEq, Eq, Clone, Copy)]
pub enum Tab {
    Channels,
    Widgets,
    PixelArt,
    Wall,
    Schedule,
    DeviceSettings,
    Settings,
}

impl Tab {
    /// Sidebar nav entries, in order (Settings is reached via the appbar gear).
    pub const NAV: [(Tab, &'static str); 6] = [
        (Tab::Channels, "Channels"),
        (Tab::Widgets, "Live Widgets"),
        (Tab::PixelArt, "Pixel Art"),
        (Tab::Wall, "Virtual Wall"),
        (Tab::Schedule, "Schedule"),
        (Tab::DeviceSettings, "Device Settings"),
    ];

    pub fn title(self) -> &'static str {
        match self {
            Tab::Channels => "Channels",
            Tab::Widgets => "Live Widgets",
            Tab::PixelArt => "Pixel Art",
            Tab::Wall => "Virtual Wall",
            Tab::Schedule => "Schedule",
            Tab::DeviceSettings => "Device Settings",
            Tab::Settings => "Settings",
        }
    }
}

/// Sub-tabs inside the Pixel Art tab (web: Custom Art + Gallery + Hot Channel).
#[derive(PartialEq, Eq, Clone, Copy)]
pub enum PixelSub {
    Paint,
    Gallery,
}

/// Channel sub-tabs inside the Channels tab (the control-panel row).
#[derive(PartialEq, Eq, Clone, Copy)]
pub enum Channel {
    Clock,
    Visualizer,
    Vj,
    Ambient,
    Scoreboard,
    Text,
    Sessions,
}

impl Channel {
    pub const ALL: [(Channel, &'static str); 7] = [
        (Channel::Clock, "Clock"),
        (Channel::Visualizer, "Visualizer"),
        (Channel::Vj, "VJ FX"),
        (Channel::Ambient, "Ambient"),
        (Channel::Scoreboard, "Scoreboard"),
        (Channel::Text, "Text"),
        (Channel::Sessions, "Sessions"),
    ];
}

/// One alarm slot, mirroring `tools.set_alarm(index, enabled, hour, minute, week,
/// mode, trigger_mode)`. `week` is a 7-bit day mask (bit0=Mon … bit6=Sun).
#[derive(Clone)]
pub struct Alarm {
    pub enabled: bool,
    pub hour: i64,
    pub minute: i64,
    pub week: u8,
}

impl Default for Alarm {
    fn default() -> Self {
        Alarm { enabled: false, hour: 8, minute: 0, week: 0 }
    }
}
