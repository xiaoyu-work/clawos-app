// Copyright 2024 System76 <info@system76.com>
// SPDX-License-Identifier: MPL-2.0

pub mod device;
pub use device::Device;
pub mod node;
pub use node::{MediaClass, Node, NodeProps};
mod profile;
pub use profile::Profile;
mod route;
#[cfg(feature = "route-port-type")]
pub use route::PortType;
pub use route::{Route, RouteProps};
mod spa_utils;
pub use spa_utils::Channel;
mod managed;
pub mod volume;

pub type NodeId = u32;
pub type RouteId = u32;
pub type DeviceId = u32;
pub type ProfileId = i32;
pub type PipewireId = u32;

pub fn run(on_event: impl FnMut(Event) + Send + 'static) -> Sender {
    managed::run(on_event)
}

#[derive(Clone, Debug)]
pub enum Event {
    ActiveProfile(DeviceId, Profile),
    ActiveRoute(DeviceId, u32, Route),
    AddDevice(Device),
    AddNode(Node),
    AddProfile(DeviceId, u32, Profile),
    AddRoute(DeviceId, u32, Route),
    DefaultSink(String),
    DefaultSource(String),
    NodeProperties(NodeId, NodeProps),
    RemoveDevice(DeviceId),
    RemoveNode(NodeId),
    Error(String),
}

#[derive(Clone, Debug)]
pub enum Request {
    EnumerateDevice(DeviceId),
    SetNodeMute(NodeId, bool),
    SetProfile(DeviceId, u32, bool),
    SetNodeVolume(DeviceId, f32, Option<f32>),
    SetRoute(DeviceId, u32, u32),
    Quit,
}

#[derive(Copy, Clone, Debug, Default, Hash, Eq, PartialEq)]
pub enum Availability {
    #[default]
    Unknown,
    No,
    Yes,
}

#[derive(Copy, Clone, Debug, Default, Hash, Eq, PartialEq)]
pub enum Direction {
    Input,
    #[default]
    Output,
}

pub struct Sender(std::sync::mpsc::Sender<Request>);

impl Sender {
    pub fn send(&self, request: Request) -> Result<(), Request> {
        self.0.send(request).map_err(|error| error.0)
    }
}

impl Drop for Sender {
    fn drop(&mut self) {
        let _ = self.0.send(Request::Quit);
    }
}
