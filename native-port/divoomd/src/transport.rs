#[cfg(feature = "ble")]
use crate::ble::BleTransport;

pub enum DeviceTransport {
    #[cfg(feature = "ble")]
    Ble(BleTransport),
    Lan(crate::lan::LanTransport),
}

impl DeviceTransport {
    pub fn device_name(&self) -> Option<String> {
        match self {
            #[cfg(feature = "ble")]
            DeviceTransport::Ble(b) => b.device_name(),
            DeviceTransport::Lan(_) => None,
        }
    }

    pub fn set_cached_device_name(&self, _name: String) {
        match self {
            #[cfg(feature = "ble")]
            DeviceTransport::Ble(b) => b.set_cached_device_name(_name),
            DeviceTransport::Lan(_) => {}
        }
    }

    #[cfg(feature = "ble")]
    pub async fn send_command(&self, command_id: u8, args: &[u8], write_with_response: bool) -> crate::ble::BleResult<()> {
        match self {
            DeviceTransport::Ble(b) => b.send_command(command_id, args, write_with_response).await,
            DeviceTransport::Lan(_) => Err("send_command not supported on LAN".into()),
        }
    }

    #[cfg(feature = "ble")]
    pub async fn wait_for_response(&self, command_id: u8, timeout: std::time::Duration) -> Option<Vec<u8>> {
        match self {
            DeviceTransport::Ble(b) => b.wait_for_response(command_id, timeout).await,
            DeviceTransport::Lan(_) => None,
        }
    }

    #[cfg(feature = "ble")]
    pub async fn send_command_and_wait(&self, command_id: u8, args: &[u8], timeout: std::time::Duration) -> Option<Vec<u8>> {
        match self {
            DeviceTransport::Ble(b) => b.send_command_and_wait(command_id, args, timeout).await,
            DeviceTransport::Lan(_) => None,
        }
    }

    #[cfg(feature = "ble")]
    pub async fn stream_animation_8b(&self, blob: &[u8]) -> crate::ble::BleResult<bool> {
        match self {
            DeviceTransport::Ble(b) => b.stream_animation_8b(blob).await,
            DeviceTransport::Lan(_) => Err("stream_animation_8b not supported on LAN".into()),
        }
    }

    pub fn lan(&self) -> Option<&crate::lan::LanTransport> {
        match self {
            #[cfg(feature = "ble")]
            DeviceTransport::Ble(_) => None,
            DeviceTransport::Lan(l) => Some(l),
        }
    }
}
