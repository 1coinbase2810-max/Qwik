#![windows_subsystem = "windows"] // no console window behind the widget

mod config;
mod launcher;
mod window;

fn main() {
    if let Err(e) = window::run() {
        eprintln!("float-shortcut: {e:?}");
    }
}
