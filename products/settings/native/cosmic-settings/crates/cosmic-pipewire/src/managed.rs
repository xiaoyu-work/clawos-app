use crate::*;
use cosmic_settings_provider_client::{call, refused};
use serde_json::Value;
use std::collections::{BTreeMap, BTreeSet};

#[derive(Default)]
struct Graph {
    nodes: BTreeMap<u32, (Node, NodeProps)>,
    devices: BTreeSet<u32>,
    routes: BTreeMap<u32, Vec<Route>>,
}

pub(super) fn run(mut event: impl FnMut(Event) + Send + 'static) -> Sender {
    let (tx, rx) = std::sync::mpsc::channel();
    std::thread::spawn(move || {
        let mut graph = Graph::default();
        loop {
            match call("audio", "status", vec![]) {
                Ok(value) => {
                    if let Err(error) = refresh(&mut graph, &value, &mut event) {
                        event(Event::Error(refused(error)));
                    }
                }
                Err(error) => event(Event::Error(error)),
            }
            match rx.recv_timeout(std::time::Duration::from_secs(2)) {
                Ok(Request::Quit) | Err(std::sync::mpsc::RecvTimeoutError::Disconnected) => return,
                Err(std::sync::mpsc::RecvTimeoutError::Timeout) => {}
                Ok(request) => {
                    if let Err(error) = apply(&graph, request) {
                        event(Event::Error(refused(error)));
                    }
                }
            }
        }
    });
    Sender(tx)
}

fn id(value: &Value) -> Result<u32, String> {
    value
        .as_u64()
        .and_then(|value| u32::try_from(value).ok())
        .filter(|value| *value != 0)
        .ok_or_else(|| "invalid OS audio object id".into())
}

fn number(value: &Value) -> Option<i32> {
    value.as_i64().and_then(|value| i32::try_from(value).ok())
}

fn profile(value: &Value) -> Result<Profile, String> {
    Ok(Profile {
        index: number(&value["index"]).ok_or("invalid OS audio profile")?,
        priority: number(&value["priority"]).unwrap_or(0),
        available: availability(&value["available"]),
        name: value["name"].as_str().unwrap_or_default().into(),
        description: value["description"].as_str().unwrap_or_default().into(),
    })
}

fn availability(value: &Value) -> Availability {
    match value.as_str() {
        Some("yes" | "Yes") => Availability::Yes,
        Some("no" | "No") => Availability::No,
        _ => Availability::Unknown,
    }
}

fn props(value: &Value) -> NodeProps {
    NodeProps {
        mute: value["mute"].as_bool(),
        monitor_mute: value["monitorMute"].as_bool(),
        channel_map: serde_json::from_value(value["channelMap"].clone()).ok(),
        channel_volumes: value["channelVolumes"]
            .as_array()
            .filter(|values| values.len() <= 32)
            .and_then(|values| {
                values
                    .iter()
                    .map(|value| {
                        value
                            .as_f64()
                            .filter(|value| value.is_finite())
                            .map(|value| value as f32)
                    })
                    .collect()
            }),
    }
}

fn route(value: &Value) -> Result<Route, String> {
    Ok(Route {
        index: number(&value["index"]).ok_or("invalid OS audio route")?,
        priority: number(&value["priority"]).unwrap_or(0),
        device: number(&value["device"]).unwrap_or(0),
        available: availability(&value["available"]),
        direction: match value["direction"].as_str() {
            Some("Input" | "input") => Direction::Input,
            Some("Output" | "output") => Direction::Output,
            _ => return Err("invalid OS audio route direction".into()),
        },
        name: value["name"].as_str().unwrap_or_default().into(),
        description: value["description"].as_str().unwrap_or_default().into(),
        devices: value["devices"]
            .as_array()
            .map(|values| values.iter().filter_map(number).collect())
            .unwrap_or_default(),
        props: value
            .get("props")
            .filter(|value| value.is_object())
            .map(|value| {
                let props = props(value);
                RouteProps {
                    mute: props.mute,
                    monitor_mute: props.monitor_mute,
                    channel_map: props.channel_map,
                    channel_volumes: props.channel_volumes,
                }
            }),
        ..Route::default()
    })
}

fn array<'a>(value: &'a Value, key: &str) -> Result<&'a [Value], String> {
    match value.get(key) {
        Some(Value::Array(values)) if values.len() <= 256 => Ok(values),
        Some(Value::Null) | None => Ok(&[]),
        _ => Err("OS audio collection exceeds its bound".into()),
    }
}

fn refresh(graph: &mut Graph, value: &Value, event: &mut impl FnMut(Event)) -> Result<(), String> {
    if value["provider"].as_str() != Some("wireplumber") {
        return Err("OS audio provider is unavailable".into());
    }
    let mut next = Graph::default();
    let mut pending = Vec::new();
    for device in array(value, "devices")? {
        let id = id(&device["id"])?;
        next.devices.insert(id);
        pending.push(Event::AddDevice(Device {
            id,
            name: device["description"]
                .as_str()
                .or_else(|| device["name"].as_str())
                .unwrap_or_default()
                .into(),
        }));
        let parameters = &device["parameters"];
        for (index, item) in array(parameters, "EnumProfile")?.iter().enumerate() {
            pending.push(Event::AddProfile(
                id,
                u32::try_from(index).map_err(|_| "audio profile bound")?,
                profile(item)?,
            ));
        }
        for item in array(parameters, "Profile")? {
            pending.push(Event::ActiveProfile(id, profile(item)?));
        }
        for (index, item) in array(parameters, "EnumRoute")?.iter().enumerate() {
            let route = route(item)?;
            next.routes.entry(id).or_default().push(route.clone());
            pending.push(Event::AddRoute(
                id,
                u32::try_from(index).map_err(|_| "audio route bound")?,
                route,
            ));
        }
        for (index, item) in array(parameters, "Route")?.iter().enumerate() {
            pending.push(Event::ActiveRoute(
                id,
                u32::try_from(index).map_err(|_| "audio route bound")?,
                route(item)?,
            ));
        }
    }
    for (key, class) in [("sinks", MediaClass::Sink), ("sources", MediaClass::Source)] {
        for object in array(value, key)? {
            let object_id = id(&object["id"])?;
            let parameters = &object["parameters"];
            let properties = &object["properties"];
            let node = Node {
                object_id,
                audio_channels: properties["audio_channels"]
                    .as_u64()
                    .and_then(|value| u32::try_from(value).ok())
                    .unwrap_or(0),
                audio_position: properties["audio_position"]
                    .as_str()
                    .unwrap_or_default()
                    .into(),
                card_profile_device: properties["card_profile_device"]
                    .as_u64()
                    .and_then(|value| u32::try_from(value).ok()),
                description: object["description"]
                    .as_str()
                    .or_else(|| object["name"].as_str())
                    .unwrap_or_default()
                    .into(),
                device_id: properties["device_id"]
                    .as_u64()
                    .and_then(|value| u32::try_from(value).ok()),
                device_profile_description: properties["profile_description"]
                    .as_str()
                    .unwrap_or_default()
                    .into(),
                device_profile_pro: properties["profile_pro"].as_str() == Some("true"),
                icon_name: properties["icon_name"].as_str().unwrap_or_default().into(),
                media_class: class.clone(),
                node_name: object["name"]
                    .as_str()
                    .ok_or("OS audio node has no name")?
                    .into(),
                state: match object["state"].as_str() {
                    Some("running") => node::State::Running,
                    Some("suspended") => node::State::Suspended,
                    _ => node::State::Idle,
                },
            };
            let node_props = array(parameters, "Props")?
                .first()
                .map(props)
                .unwrap_or_default();
            next.nodes.insert(object_id, (node.clone(), node_props));
            pending.push(Event::AddNode(node));
        }
    }
    for (&id, (old, _)) in &graph.nodes {
        if next.nodes.get(&id).is_none_or(|(new, _)| {
            old.node_name != new.node_name || old.media_class != new.media_class
        }) {
            event(Event::RemoveNode(id));
        }
    }
    for id in graph.devices.difference(&next.devices) {
        event(Event::RemoveDevice(*id));
    }
    for update in pending {
        event(update);
    }
    for (direction, sink) in [("output", true), ("input", false)] {
        if let Some(name) = value["defaults"][direction]["properties"]["node.name"].as_str() {
            event(if sink {
                Event::DefaultSink(name.into())
            } else {
                Event::DefaultSource(name.into())
            });
        }
    }
    for (&id, (_, props)) in &next.nodes {
        event(Event::NodeProperties(id, props.clone()));
    }
    *graph = next;
    Ok(())
}

fn apply(graph: &Graph, request: Request) -> Result<(), String> {
    let (action, target, value) = match request {
        Request::EnumerateDevice(_) => return Ok(()),
        Request::Quit => return Ok(()),
        Request::SetProfile(id, index, _) => ("profile", id.to_string(), index.to_string()),
        Request::SetRoute(device, card, route) => {
            let route_info = graph
                .routes
                .get(&device)
                .and_then(|routes| {
                    routes
                        .iter()
                        .find(|candidate| u32::try_from(candidate.index).ok() == Some(route))
                })
                .ok_or("audio route changed; refresh before retrying")?;
            let output = matches!(route_info.direction, Direction::Output);
            let node = graph
                .nodes
                .values()
                .map(|(node, _)| node)
                .find(|node| {
                    node.device_id == Some(device)
                        && node.card_profile_device == Some(card)
                        && matches!(
                            (&node.media_class, output),
                            (MediaClass::Sink, true) | (MediaClass::Source, false)
                        )
                })
                .ok_or("audio route node changed; refresh before retrying")?;
            (
                if output {
                    "output-route"
                } else {
                    "input-route"
                },
                node.object_id.to_string(),
                route.to_string(),
            )
        }
        Request::SetNodeMute(id, muted) => {
            let (node, _) = graph
                .nodes
                .get(&id)
                .ok_or("audio node changed; refresh before retrying")?;
            (
                if node.media_class == MediaClass::Sink {
                    "output-mute"
                } else {
                    "input-mute"
                },
                id.to_string(),
                if muted { "on" } else { "off" }.into(),
            )
        }
        Request::SetNodeVolume(id, volume, balance) => {
            let (node, props) = graph
                .nodes
                .get(&id)
                .ok_or("audio node changed; refresh before retrying")?;
            if !volume.is_finite() || !(0.0..=1.5).contains(&volume) {
                return Err("invalid audio volume".into());
            }
            if node.media_class == MediaClass::Sink && balance.is_some() {
                let map = props
                    .channel_map
                    .as_ref()
                    .filter(|map| !map.is_empty() && map.len() <= 32)
                    .ok_or("OS audio channel map is unavailable; balance was not changed")?;
                let channels = volume::to_channel_volumes(map, volume, balance);
                (
                    "output-channel-volumes",
                    id.to_string(),
                    channels
                        .iter()
                        .map(|value| format!("{value:.4}"))
                        .collect::<Vec<_>>()
                        .join(":"),
                )
            } else {
                (
                    if node.media_class == MediaClass::Sink {
                        "output-volume"
                    } else {
                        "input-volume"
                    },
                    id.to_string(),
                    format!("{:.0}", volume * 100.0),
                )
            }
        }
    };
    call(
        "audio",
        action,
        vec!["--target".into(), target, "--value".into(), value],
    )?;
    Ok(())
}
