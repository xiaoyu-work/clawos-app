// SPDX-License-Identifier: GPL-3.0-only

use std::io::{BufRead, Read};
use std::os::fd::{AsRawFd, RawFd};
use std::process::{Child, Command, Stdio};
use std::time::Duration;

pub(crate) struct Output {
    child: Child,
}

impl Output {
    pub(crate) fn open() -> Result<Self, String> {
        let mut child = Command::new("/usr/local/bin/yu")
            .args(["__gui-audio", "--pcm-stdin"])
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::inherit())
            .spawn()
            .map_err(|error| format!("start OS audio transport: {error}"))?;
        let stdout = child.stdout.take().expect("piped audio acknowledgement");
        let (sender, receiver) = std::sync::mpsc::sync_channel(1);
        std::thread::spawn(move || {
            let mut reader = std::io::BufReader::new(stdout.take(1024));
            let mut line = String::new();
            let result = reader
                .read_line(&mut line)
                .map(|_| line)
                .map_err(|error| error.to_string());
            let _ = sender.send(result);
        });
        let ready = receiver
            .recv_timeout(Duration::from_secs(5))
            .map_err(|_| "OS audio transport did not acknowledge startup".to_string())
            .and_then(|result| result)
            .and_then(|line| {
                serde_json::from_str::<serde_json::Value>(&line).map_err(|error| error.to_string())
            });
        if !ready.is_ok_and(|ready| ready["version"] == 1 && ready["ready"] == true) {
            let _ = child.kill();
            let _ = child.wait();
            return Err("OS audio output was unavailable or not authorized".into());
        }
        Ok(Self { child })
    }

    pub(crate) fn descriptor(&self) -> RawFd {
        self.child
            .stdin
            .as_ref()
            .expect("live PCM transport")
            .as_raw_fd()
    }
}

impl Drop for Output {
    fn drop(&mut self) {
        self.child.stdin.take();
        if self.child.try_wait().is_ok_and(|status| status.is_some()) {
            return;
        }
        let _ = self.child.kill();
        let _ = self.child.wait();
    }
}
