use std::sync::{Mutex, OnceLock};
use windows::{
    core::*,
    Win32::{
        Foundation::*,
        Graphics::Gdi::*,
        System::LibraryLoader::GetModuleHandleW,
        UI::{Input::KeyboardAndMouse::*, Shell::*, WindowsAndMessaging::*},
    },
};

use crate::{config, launcher};

const DOT: i32 = 48;
const ROW_H: i32 = 40;
const MAX_W: i32 = 220;
const HIDE_TIMER: usize = 1;
const FULLSCREEN_TIMER: usize = 2;

struct State {
    hwnd: HWND,
    expanded: bool,
    ctx: usize, // row under the last right-click
    cfg: config::AppConfig,
    icons: Vec<HICON>,
    hotkey_hidden: bool,
    fs_hidden: bool,
}

static STATE: OnceLock<Mutex<State>> = OnceLock::new();
fn state() -> &'static Mutex<State> {
    STATE.get_or_init(|| {
        Mutex::new(State {
            hwnd: HWND(0),
            expanded: false,
            ctx: 0,
            cfg: config::load(),
            icons: vec![],
            hotkey_hidden: false,
            fs_hidden: false,
        })
    })
}

fn load_icons() {
    let mut st = state().lock().unwrap();
    for i in &st.icons {
        unsafe { let _ = DestroyIcon(*i) };
    }
    st.icons.clear();
    for s in &st.cfg.shortcut {
        let mut shfi: SHFILEINFOW = unsafe { std::mem::zeroed() };
        let wpath = HSTRING::from(s.path.as_str());
        unsafe {
            SHGetFileInfoW(
                PCWSTR::from_raw(wpath.as_ptr()),
                Default::default(),
                Some(&mut shfi as *mut _),
                std::mem::size_of::<SHFILEINFOW>() as u32,
                SHGFI_ICON | SHGFI_SMALLICON,
            )
        };
        st.icons.push(shfi.hIcon);
    }
}

fn apply_alpha(hwnd: HWND, alpha: u8) {
    unsafe { let _ = SetLayeredWindowAttributes(hwnd, COLORREF(0), alpha, LWA_ALPHA) };
}

fn resize(hwnd: HWND, expanded: bool) {
    let n = state().lock().unwrap().cfg.shortcut.len().max(1).min(5) as i32;
    let (w, h) = if expanded {
        (MAX_W, DOT + n * ROW_H)
    } else {
        (DOT, DOT)
    };
    unsafe {
        let _ = SetWindowPos(hwnd, Some(HWND_TOPMOST), 0, 0, w, h, SWP_NOMOVE | SWP_NOACTIVATE);
        let _ = InvalidateRect(Some(hwnd), None, TRUE);
    }
}

fn set_expanded(hwnd: HWND, on: bool) {
    state().lock().unwrap().expanded = on;
    apply_alpha(hwnd, if on { 255 } else { 51 }); // ~20% at rest, 100% on hover
    resize(hwnd, on);
    unsafe {
        if on {
            let _ = KillTimer(Some(hwnd), HIDE_TIMER);
        } else {
            let _ = SetTimer(Some(hwnd), HIDE_TIMER, 3000, None);
        }
    }
}

fn launch(i: usize) {
    let path = state().lock().unwrap().cfg.shortcut.get(i).map(|s| s.path.clone());
    if let Some(p) = path {
        launcher::open(&p);
        // most-used first: bump counter, re-sort, persist.
        let mut st = state().lock().unwrap();
        if let Some(s) = st.cfg.shortcut.get_mut(i) {
            s.uses += 1;
        }
        st.cfg.shortcut.sort_by(|a, b| b.uses.cmp(&a.uses));
        config::save(&st.cfg);
        drop(st);
        load_icons();
        unsafe { let _ = InvalidateRect(Some(state().lock().unwrap().hwnd), None, TRUE) };
    }
}

fn delete_at(i: usize) {
    let hwnd;
    {
        let mut st = state().lock().unwrap();
        if i < st.cfg.shortcut.len() {
            st.cfg.shortcut.remove(i);
            config::save(&st.cfg);
        }
        hwnd = st.hwnd;
    }
    load_icons();
    resize(hwnd, true);
}

fn move_at(i: usize, dir: i32) {
    let hwnd;
    {
        let mut st = state().lock().unwrap();
        let j = (i as i32 + dir).clamp(0, st.cfg.shortcut.len() as i32 - 1) as usize;
        if i < st.cfg.shortcut.len() {
            st.cfg.shortcut.swap(i, j);
            config::save(&st.cfg);
        }
        hwnd = st.hwnd;
    }
    load_icons();
    unsafe { let _ = InvalidateRect(Some(hwnd), None, TRUE) };
}

// Right-click menu posts WM_COMMAND back; keeps one call shape only.
fn show_popup(hwnd: HWND, idx: usize, x: i32, y: i32) {
    state().lock().unwrap().ctx = idx;
    unsafe {
        let Ok(menu) = CreatePopupMenu() else { return };
        let _ = AppendMenuW(menu, MF_STRING, 101, w!("Open"));
        let _ = AppendMenuW(menu, MF_STRING, 102, w!("Move up"));
        let _ = AppendMenuW(menu, MF_STRING, 103, w!("Move down"));
        let _ = AppendMenuW(menu, MF_STRING, 104, w!("Delete"));
        let _ = SetForegroundWindow(hwnd);
        let _ = TrackPopupMenu(menu, TPM_LEFTALIGN, x, y, 0, hwnd, None);
        let _ = DestroyMenu(menu);
    }
}

fn x_of(lp: LPARAM) -> i32 {
    ((lp.0 as i32) & 0xffff) as i16 as i32
}
fn y_of(lp: LPARAM) -> i32 {
    (((lp.0 as i32) >> 16) & 0xffff) as i16 as i32
}

extern "system" fn wndproc(hwnd: HWND, msg: u32, wp: WPARAM, lp: LPARAM) -> LRESULT {
    unsafe {
        match msg {
            WM_CREATE => {
                DragAcceptFiles(hwnd, TRUE);
                let _ = RegisterHotKey(Some(hwnd), 1, MOD_WIN, 0xC0); // Win + `
                let _ = SetTimer(Some(hwnd), FULLSCREEN_TIMER, 2000, None);
                LRESULT(0)
            }
            WM_MOUSEMOVE => {
                if !state().lock().unwrap().expanded {
                    let mut tme = TRACKMOUSEEVENT {
                        cbSize: std::mem::size_of::<TRACKMOUSEEVENT>() as u32,
                        dwFlags: TME_LEAVE,
                        hwndTrack: hwnd,
                        dwHoverTime: 0,
                    };
                    let _ = TrackMouseEvent(&mut tme as *mut _);
                    set_expanded(hwnd, true); // hover -> 100% in the same frame (<150ms)
                }
                LRESULT(0)
            }
            WM_MOUSELEAVE => {
                // collapse happens on HIDE_TIMER (3s) so quick mouse-outs don't flicker
                let _ = SetTimer(Some(hwnd), HIDE_TIMER, 3000, None);
                LRESULT(0)
            }
            WM_TIMER => {
                let id = wp.0;
                if id == HIDE_TIMER {
                    let _ = KillTimer(Some(hwnd), HIDE_TIMER);
                    set_expanded(hwnd, false);
                } else if id == FULLSCREEN_TIMER {
                    // hide while a fullscreen app/game is presenting
                    let mut q = QUERY_USER_NOTIFICATION_STATE(0);
                    if SHQueryUserNotificationState(&mut q as *mut _).is_ok() {
                        let fs = q == QUNS_BUSY
                            || q == QUNS_RUNNING_D3D_FULL_SCREEN
                            || q == QUNS_PRESENTATION_MODE;
                        let mut st = state().lock().unwrap();
                        if fs != st.fs_hidden {
                            st.fs_hidden = fs;
                            let _ = ShowWindow(hwnd, if fs { SW_HIDE } else { SW_SHOWNA });
                        }
                    }
                }
                LRESULT(0)
            }
            WM_LBUTTONUP => {
                let (expanded, n) = {
                    let st = state().lock().unwrap();
                    (st.expanded, st.cfg.shortcut.len())
                };
                if expanded {
                    let idx = (y_of(lp) - DOT) / ROW_H;
                    if idx >= 0 && (idx as usize) < n {
                        launch(idx as usize);
                        set_expanded(hwnd, false);
                    }
                }
                LRESULT(0)
            }
            WM_RBUTTONUP => {
                let (expanded, n) = {
                    let st = state().lock().unwrap();
                    (st.expanded, st.cfg.shortcut.len())
                };
                if expanded {
                    let idx = ((y_of(lp) - DOT) / ROW_H).max(0) as usize;
                    if idx < n {
                        let mut pt = POINT {
                            x: x_of(lp),
                            y: y_of(lp),
                        };
                        let _ = ClientToScreen(hwnd, &mut pt as *mut _);
                        show_popup(hwnd, idx, pt.x, pt.y);
                    }
                }
                LRESULT(0)
            }
            WM_COMMAND => {
                let cmd = (wp.0 & 0xffff) as u32;
                let idx = state().lock().unwrap().ctx;
                match cmd {
                    101 => launch(idx),
                    102 => move_at(idx, -1),
                    103 => move_at(idx, 1),
                    104 => delete_at(idx),
                    _ => {}
                }
                LRESULT(0)
            }
            WM_DROPFILES => {
                let h = HDROP(wp.0 as _);
                let count = DragQueryFileW(h, 0xFFFFFFFF, None, 0);
                let room = 5u32.saturating_sub(state().lock().unwrap().cfg.shortcut.len() as u32);
                let mut st = state().lock().unwrap();
                for k in 0..count.min(room) {
                    let len = DragQueryFileW(h, k, None, 0) as usize;
                    let mut buf = vec![0u16; len + 1];
                    DragQueryFileW(h, k, Some(PWSTR(buf.as_mut_ptr())), len as u32 + 1);
                    let path = String::from_utf16_lossy(&buf[..len]);
                    let name = std::path::Path::new(&path)
                        .file_stem()
                        .map(|s| s.to_string_lossy().into_owned())
                        .unwrap_or_else(|| path.clone());
                    st.cfg.shortcut.push(crate::config::Shortcut {
                        name,
                        path,
                        uses: 0,
                    });
                }
                config::save(&st.cfg);
                drop(st);
                DragFinish(h);
                load_icons();
                resize(hwnd, true);
                LRESULT(0)
            }
            WM_HOTKEY => {
                let mut st = state().lock().unwrap();
                st.hotkey_hidden = !st.hotkey_hidden;
                let _ = ShowWindow(hwnd, if st.hotkey_hidden { SW_HIDE } else { SW_SHOWNA });
                LRESULT(0)
            }
            WM_PAINT => {
                let mut ps = PAINTSTRUCT::default();
                let hdc = BeginPaint(hwnd, &mut ps as *mut _);
                let brush = CreateSolidBrush(COLORREF(0x303030));
                let old = SelectObject(hdc, HGDIOBJ(brush.0));
                let _ = Ellipse(hdc, 0, 0, DOT, DOT);
                let st = state().lock().unwrap();
                if st.expanded {
                    for (i, s) in st.cfg.shortcut.iter().enumerate().take(5) {
                        let y = DOT + i as i32 * ROW_H;
                        if let Some(ic) = st.icons.get(i) {
                            let _ = DrawIconEx(hdc, 8, y + 4, *ic, 32, 32, 0, None, DI_NORMAL);
                        }
                        let name: Vec<u16> = s.name.encode_utf16().collect();
                        let mut rc = RECT {
                            left: 48,
                            top: y,
                            right: MAX_W,
                            bottom: y + ROW_H,
                        };
                        let _ = DrawTextW(hdc, &name, &mut rc as *mut _, DT_SINGLELINE | DT_VCENTER | DT_LEFT);
                    }
                }
                let _ = SelectObject(hdc, old);
                let _ = DeleteObject(HGDIOBJ(brush.0));
                let _ = EndPaint(hwnd, &ps as *const _);
                LRESULT(0)
            }
            // draggable dot, clickable rows when expanded
            WM_NCHITTEST => {
                if state().lock().unwrap().expanded {
                    LRESULT(HTCLIENT as isize)
                } else {
                    LRESULT(HTCAPTION as isize)
                }
            }
            WM_MOVE => {
                let mut rc = RECT::default();
                if GetWindowRect(hwnd, &mut rc as *mut _).is_ok() {
                    let mut st = state().lock().unwrap();
                    st.cfg.pos = Some((rc.left, rc.top));
                    config::save(&st.cfg);
                }
                LRESULT(0)
            }
            WM_DESTROY => {
                let _ = UnregisterHotKey(Some(hwnd), 1);
                PostQuitMessage(0);
                LRESULT(0)
            }
            _ => DefWindowProcW(hwnd, msg, wp, lp),
        }
    }
}

pub fn run() -> Result<()> {
    load_icons();
    unsafe {
        let inst = GetModuleHandleW(None)?;
        let cls = w!("FloatShortcut");
        let wc = WNDCLASSW {
            lpfnWndProc: Some(wndproc),
            hInstance: HINSTANCE(inst.0),
            lpszClassName: cls,
            hCursor: Some(LoadCursorW(None, IDC_ARROW)?),
            ..Default::default()
        };
        RegisterClassW(&wc as *const _);

        let (x, y) = state().lock().unwrap().cfg.pos.unwrap_or((1500, 800));
        let hwnd = CreateWindowExW(
            WS_EX_LAYERED | WS_EX_TOPMOST | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE,
            cls,
            w!(""),
            WS_POPUP,
            x,
            y,
            DOT,
            DOT,
            None,
            None,
            Some(HINSTANCE(inst.0)),
            None,
        )?;
        state().lock().unwrap().hwnd = hwnd;
        apply_alpha(hwnd, 51);
        let _ = ShowWindow(hwnd, SW_SHOWNA);

        let mut msg = MSG::default();
        while GetMessageW(&mut msg as *mut _, None, 0, 0).as_bool() {
            let _ = TranslateMessage(&msg as *const _);
            DispatchMessageW(&msg as *const _);
        }
    }
    Ok(())
}
