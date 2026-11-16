// Copyright 2024 System76 <info@system76.com>
// SPDX-License-Identifier: MPL-2.0

use crate::Channel;

pub fn from_channel_volumes(channels: &[f32]) -> (f32, Option<f32>) {
    let left_volume = channels.first().cloned().unwrap_or_default();
    let right_volume = channels.last().cloned().unwrap_or_default();
    if (left_volume - right_volume).abs() < f32::EPSILON {
        return (left_volume.powf(1.0 / 3.0), None);
    }
    let (volume, balance) = if left_volume >= right_volume {
        (left_volume, right_volume / left_volume)
    } else {
        (right_volume, 2.0 - left_volume / right_volume)
    };
    (volume.powf(1.0 / 3.0), Some(balance))
}

pub fn to_channel_volumes(channel_map: &[Channel], volume: f32, balance: Option<f32>) -> Vec<f32> {
    let volume = volume * volume * volume;
    if let Some(balance) = balance {
        let (left, right) = if balance >= 1.0 {
            (volume * (balance - 2.0).abs(), volume)
        } else {
            (volume, volume * balance)
        };
        let center = (left + right) / 2.0;
        channel_map
            .iter()
            .map(|channel| match channel {
                Channel::FL
                | Channel::SL
                | Channel::FLC
                | Channel::RL
                | Channel::TFL
                | Channel::TFC
                | Channel::TRL
                | Channel::RLC
                | Channel::FLW
                | Channel::FLH
                | Channel::TFLC
                | Channel::TSL
                | Channel::LLFE
                | Channel::BLC => left,
                Channel::FR
                | Channel::SR
                | Channel::FRC
                | Channel::RR
                | Channel::TFR
                | Channel::TRC
                | Channel::TRR
                | Channel::RRC
                | Channel::FRW
                | Channel::FRH
                | Channel::TFRC
                | Channel::TSR
                | Channel::RLFE
                | Channel::BRC => right,
                _ => center,
            })
            .collect()
    } else {
        vec![volume; channel_map.len()]
    }
}

#[cfg(test)]
mod test {
    include!(concat!(env!("CARGO_MANIFEST_DIR"), "/test/unit/volume.rs"));
}
