use std::process::Command;

pub fn open(path: &str) {
    // std Command instead of ShellExecuteW: no HSTRING/PCWSTR juggling,
    // UTF-16 + spaces handled by std. Folders go through explorer.
    let is_dir = std::fs::metadata(path).map(|m| m.is_dir()).unwrap_or(false);
    if is_dir {
        let _ = Command::new("explorer.exe").arg(path).spawn();
    } else {
        let _ = Command::new(path).spawn();
    }
}
