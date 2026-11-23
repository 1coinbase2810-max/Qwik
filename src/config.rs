use serde::{Deserialize, Serialize};
use std::{fs, path::PathBuf};

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct Shortcut {
    pub name: String,
    pub path: String,
    #[serde(default)]
    pub uses: u32,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct AppConfig {
    #[serde(default)]
    pub shortcut: Vec<Shortcut>,
    #[serde(default)]
    pub pos: Option<(i32, i32)>,
}

fn config_path() -> PathBuf {
    std::env::current_exe()
        .ok()
        .and_then(|p| p.parent().map(|p| p.to_path_buf()))
        .unwrap_or_else(|| PathBuf::from("."))
        .join("shortcuts.toml")
}

pub fn load() -> AppConfig {
    fs::read_to_string(config_path())
        .ok()
        .and_then(|s| toml::from_str(&s).ok())
        .unwrap_or_default()
}

pub fn save(cfg: &AppConfig) {
    if let Ok(s) = toml::to_string(cfg) {
        let _ = fs::write(config_path(), s);
    }
}
