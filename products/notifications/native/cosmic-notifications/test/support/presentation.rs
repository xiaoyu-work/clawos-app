use std::{
    ffi::OsString,
    fs,
    path::PathBuf,
    sync::atomic::{AtomicU64, Ordering},
};

static NEXT: AtomicU64 = AtomicU64::new(0);

pub struct Fixture {
    pub root: PathBuf,
    pub config: cosmic::cosmic_config::Config,
    original: Vec<(&'static str, Option<OsString>)>,
}

impl Fixture {
    pub fn new() -> Self {
        let root = std::env::current_exe()
            .unwrap()
            .parent()
            .unwrap()
            .join("notification-presentation-fixtures")
            .join(format!(
                "{}-{}",
                std::process::id(),
                NEXT.fetch_add(1, Ordering::Relaxed)
            ));
        fs::create_dir_all(&root).unwrap();
        let config = cosmic::cosmic_config::Config::with_custom_path(
            cosmic_notifications_config::ID,
            1,
            root.clone(),
        )
        .unwrap();
        let original = [
            "XDG_CURRENT_DESKTOP",
            "XDG_CONFIG_HOME",
            "XDG_DATA_HOME",
            "XDG_DATA_DIRS",
            claw_notification_presentation::PRESENTER_FD_ENV,
        ]
        .into_iter()
        .map(|key| (key, std::env::var_os(key)))
        .collect();
        unsafe {
            std::env::set_var("XDG_CURRENT_DESKTOP", "fixture");
            std::env::set_var("XDG_CONFIG_HOME", &root);
            std::env::set_var("XDG_DATA_HOME", &root);
            std::env::set_var("XDG_DATA_DIRS", &root);
        }
        Self {
            root,
            config,
            original,
        }
    }

    pub fn config_file(&self, key: &str) -> PathBuf {
        self.root
            .join("cosmic/com.clawos.Notifications/v1")
            .join(key)
    }
}

impl Drop for Fixture {
    fn drop(&mut self) {
        for (key, value) in &self.original {
            unsafe {
                match value {
                    Some(value) => std::env::set_var(key, value),
                    None => std::env::remove_var(key),
                }
            }
        }
        fs::remove_dir_all(&self.root).unwrap();
    }
}
