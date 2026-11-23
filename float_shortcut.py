"""Qwik - floating shortcut dot (Tkinter build, stdlib + Pillow for logo).
Half-circle fan: hub dot with up to 5 black shortcut circles fanned
to the side with room (auto-flips left/right at screen edges).
Transparent everywhere except hub, circles and label pills.
Hover expands, collapses 3s after mouse leaves.
Ctrl+Q (global) toggles the panel without the mouse.
Position + use-count persist in shortcuts.toml next to this file.
Layout rules (fixed 2026-11-23, see the fan bugs they correct):
- the hub never moves when the fan opens/closes: the fan window is
  anchored so the hub centre stays exactly where the dot was, and
  the saved position is always the dot (collapsed) position;
- captions sit beside their circle, vertically centred, never below
  it, so a caption can never overlap the next circle in the fan;
- every caption pill is sized to its own text instead of a fixed
  76 px, so long names ("Screenshots") fit and short ones ("Add")
  do not get a wide empty pill;
- icons are extracted at their native large size and centred on a
  transparent canvas, so the glyph sits in the middle of its circle.
Run:  python float_shortcut.py
"""
import ctypes
import math
import os
import sys
import threading
import tomllib

DOT = 48
CIRC = 64  # black shortcut circle diameter (dark so icons read easily)
R = 150  # fan radius from hub center (was 112: circles were only 72 px
# apart with 5 tiles, so captions overlapped the next circle)
ARC_HALF = 60  # fan spans -60..+60 deg (was 75: same crowding problem)
ICON = 32
COLLAPSE_MS = 3000  # panel hides 3s after mouse leaves
ALPHA_IDLE = 0.2
APP_NAME = "Qwik"
CIRCLE_FILL = "#161616"
CIRCLE_EDGE = "#3d3d3d"
HUB_FILL = "#0c0c0c"
HUB_RING = "#3a3a3a"
PILL_FILL = "#161616"
PILL_EDGE = "#3d3d3d"
FONT_TITLE = ("Segoe UI", 11, "bold")
FONT_CAP = ("Segoe UI", 10, "bold")
FG_TEXT = "#ffffff"
RED = "#e10600"  # logo fallback ring only, never used for text
KEY = "magenta"  # transparentcolor: anything painted KEY vanishes
PAD = 12
CAP_GAP = 6  # gap between a circle's edge and its caption pill
CAP_H = 18  # caption pill height
CAP_PAD_X = 8  # horizontal padding inside a caption pill

try:
    import tkinter as tk
    from tkinter import filedialog
except ImportError:
    sys.exit("tkinter missing - reinstall Python with 'tcl/tk' checked")
try:
    from PIL import Image, ImageTk
except ImportError:
    Image = ImageTk = None  # logo-less fallback: drawn circle only

# Frozen (PyInstaller one-dir): data files live in _MEIPASS, but the user config
# must stay next to the exe so it survives updates.
if getattr(sys, "frozen", False):
    RES_DIR = sys._MEIPASS  # logo lives inside the bundle
    BASE = os.path.dirname(sys.executable)
else:
    RES_DIR = BASE = os.path.dirname(os.path.abspath(__file__))
TOML_PATH = os.path.join(BASE, "shortcuts.toml")


def load_cfg():
    try:
        with open(TOML_PATH, "rb") as f:
            d = tomllib.load(f)
    except (FileNotFoundError, tomllib.TOMLDecodeError):
        d = {}
    shortcuts = d.get("shortcut", [])[:5]
    pos = d.get("pos")  # [x, y] or None
    return shortcuts, pos


def save_cfg(shortcuts, pos):
    lines = []
    for s in shortcuts[:5]:
        name = s.get("name", "?").replace('"', "'")
        path = s.get("path", "").replace("\\", "\\\\").replace('"', "'")
        lines.append('[[shortcut]]\nname = "%s"\npath = "%s"\nuses = %d\n' % (
            name, path, s.get("uses", 0)))
    if pos:
        lines.append("pos = [%d, %d]\n" % (pos[0], pos[1]))
    with open(TOML_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) if lines else "")


def is_fullscreen():
    # SHQueryUserNotificationState: 2/3/4 = fullscreen-ish states. Any failure = not fullscreen.
    try:
        q = ctypes.c_int(0)
        if ctypes.windll.shell32.SHQueryUserNotificationState(ctypes.byref(q)) == 0:
            return q.value in (2, 3, 4)
    except Exception:
        pass
    return False


class _SHFILEINFOW(ctypes.Structure):
    _fields_ = [("hIcon", ctypes.c_void_p),
                ("iIcon", ctypes.c_int),
                ("dwAttributes", ctypes.c_uint32),
                ("szDisplayName", ctypes.c_wchar * 260),
                ("szTypeName", ctypes.c_wchar * 80)]


class _ICONINFO(ctypes.Structure):
    _fields_ = [("fIcon", ctypes.c_bool),
                ("xHotspot", ctypes.c_uint32),
                ("yHotspot", ctypes.c_uint32),
                ("hbmMask", ctypes.c_void_p),
                ("hbmColor", ctypes.c_void_p)]


_icon_cache = {}

def file_icon(path, size=24):
    """Real Windows icon as PhotoImage - folder icon for dirs, app icon for exes. Cached."""
    if ImageTk is None or not path:
        return None
    norm = os.path.normpath(path)
    key = (norm.lower(), size)
    if key not in _icon_cache:
        img = _extract_icon(norm, size)
        _icon_cache[key] = ImageTk.PhotoImage(img) if img is not None else None
    return _icon_cache[key]


def _centred_icon(img, size):
    """Centre a native icon on a transparent size x size canvas.

    Windows icons are not always size x size and their glyph is not
    always centred in the bitmap (a 16 px small icon in a 32 px
    bitmap used to sit in the top-left corner, so every glyph in the
    fan looked shifted up-left). Trim the transparent border, shrink
    only if the glyph is larger than the canvas, then paste it dead
    centre. Returns a PIL image, never a PhotoImage (the caller wraps
    it, so this also works for the --check-icons path).
    """
    if img is None:
        return None
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    alpha = img.split()[3]
    bbox = alpha.getbbox()
    if bbox:
        img = img.crop(bbox)
    if img.width > size or img.height > size:
        img.thumbnail((size, size), Image.LANCZOS)
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    canvas.paste(img, ((size - img.width) // 2, (size - img.height) // 2), img)
    return canvas


def _extract_icon(path, size):
    # Real icon via SHGetFileInfo + GetDIBits. ctypes defaults truncate 64-bit
    # handles, so every signature is pinned explicitly (this was the FAIL bug).
    import struct
    try:
        user32, gdi32, shell32 = ctypes.windll.user32, ctypes.windll.gdi32, ctypes.windll.shell32
        if not getattr(_extract_icon, "wired", False):
            user32.GetIconInfo.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
            user32.GetIconInfo.restype = ctypes.c_int
            user32.GetDC.argtypes = [ctypes.c_void_p]
            user32.GetDC.restype = ctypes.c_void_p
            user32.ReleaseDC.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
            user32.ReleaseDC.restype = ctypes.c_int
            user32.DestroyIcon.argtypes = [ctypes.c_void_p]
            user32.DestroyIcon.restype = ctypes.c_int
            gdi32.GetDIBits.argtypes = [ctypes.c_void_p] * 7
            gdi32.GetDIBits.restype = ctypes.c_int
            gdi32.DeleteObject.argtypes = [ctypes.c_void_p]
            gdi32.DeleteObject.restype = ctypes.c_int
            shell32.SHGetFileInfoW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32,
                                               ctypes.c_void_p, ctypes.c_uint,
                                               ctypes.c_uint]
            shell32.SHGetFileInfoW.restype = ctypes.c_ulonglong
            _extract_icon.wired = True
        shfi = _SHFILEINFOW()
        # SHGFI_ICON alone (0x100) = the LARGE icon, 32 px on a standard
        # display, which matches ICON. The old 0x101 also set
        # SHGFI_SMALLICON, so Windows handed back a 16 px icon that was
        # then stretched into a 32 px bitmap with the glyph stuck in the
        # top-left corner.
        if not shell32.SHGetFileInfoW(path, 0, ctypes.byref(shfi),
                                      ctypes.sizeof(shfi), 0x100):  # SHGFI_ICON
            return None
        try:
            ii = _ICONINFO()
            if not user32.GetIconInfo(shfi.hIcon, ctypes.byref(ii)):
                return None
            try:
                fmt = "<IiiHHIIiiII"
                hdr = struct.pack(fmt, 40, size, -size, 1, 32, 0, 0, 0, 0, 0, 0)
                buf = ctypes.create_string_buffer(size * size * 4)
                hdc = user32.GetDC(None)
                try:
                    if not gdi32.GetDIBits(hdc, ii.hbmColor, 0, size, buf, hdr, 0):
                        return None
                finally:
                    user32.ReleaseDC(None, hdc)
                raw = bytearray(buf.raw)
                if not any(raw[3::4]):  # legacy icon: alpha lives in the mask
                    hdr1 = struct.pack(fmt, 40, size, -size, 1, 1, 0, 0, 0, 0, 0, 0)
                    bmi1 = ctypes.create_string_buffer(hdr1 + b"\x00\x00\x00\x00\xff\xff\xff\x00")
                    stride = ((size + 31) // 32) * 4
                    mbuf = ctypes.create_string_buffer(stride * size)
                    hdc = user32.GetDC(None)
                    try:
                        gdi32.GetDIBits(hdc, ii.hbmMask, 0, size, mbuf, bmi1, 0)
                    finally:
                        user32.ReleaseDC(None, hdc)
                    for y in range(size):
                        for x in range(size):
                            clear = (mbuf[y * stride + x // 8] >> (7 - x % 8)) & 1
                            raw[(y * size + x) * 4 + 3] = 0 if clear else 255
                img = Image.frombytes("RGBA", (size, size), bytes(raw), "raw", "BGRA")
            finally:
                gdi32.DeleteObject(ii.hbmColor)
                gdi32.DeleteObject(ii.hbmMask)
        finally:
            user32.DestroyIcon(shfi.hIcon)
        return _centred_icon(img, size)
    except Exception:
        return None


shortcuts, saved_pos = load_cfg()
root = tk.Tk()
root.overrideredirect(True)
root.attributes("-topmost", True)
root.attributes("-alpha", ALPHA_IDLE)
root.configure(bg=KEY)
root.attributes("-transparentcolor", KEY)  # square corners vanish -> shaped panel
root.update_idletasks()
SW, SH = root.winfo_screenwidth(), root.winfo_screenheight()


def _short_name(name):
    name = (name or "?").strip() or "?"
    return name if len(name) <= 14 else name[:13] + "..."


def _tile_count():
    """Tiles in the fan: one per shortcut plus an Add tile, max 5."""
    return len(shortcuts[:5]) + (1 if len(shortcuts) < 5 else 0) or 1


_cap_font = None


def _text_w(text):
    """Pixel width of a caption in FONT_CAP (fallback: 8 px/char)."""
    global _cap_font
    try:
        from tkinter import font as _tkfont
        if _cap_font is None:
            _cap_font = _tkfont.Font(font=FONT_CAP)
        return _cap_font.measure(text)
    except Exception:
        return len(text) * 8


def _label_w(text):
    """Full caption-pill width for a label (text + padding)."""
    return _text_w(text) + 2 * CAP_PAD_X


def _max_label_w():
    labels = [_short_name(s.get("name", "?")) for s in shortcuts[:5]]
    if len(shortcuts) < 5:
        labels.append("Add")
    return max((_label_w(t) for t in labels), default=_label_w("Add"))


def pick_side(hub_cx, need):
    """Fan opens to the side with room for the whole fan (never off-screen).

    hub_cx is the hub centre on screen; need is the distance from the
    hub centre to the far edge of the fan window (the same either way,
    the layout is symmetric). The old version was handed the dot's
    top-left corner and the window width, which did not describe the
    anchored fan at all.
    """
    if hub_cx + need <= SW:
        return 1  # open right (normal: hub at left edge)
    if hub_cx - need >= 0:
        return -1  # open left (hub sticks at right edge)
    return 1 if SW - hub_cx >= hub_cx else -1


def fan_size(n_tiles):
    """Bounding box of the transparent fan window for n tiles (hub + circles + pills).

    Height is exactly the fan span plus one circle plus padding: the
    old formula added two caption heights on top of that, so the
    window was ~70 px taller than its contents and the hub sat
    175 px below the dot it replaced. Width fits the widest caption
    pill beside its circle (see _max_label_w).
    """
    n = max(int(n_tiles), 1)
    span = R * math.sin(math.radians(ARC_HALF))
    h = int(2 * PAD + 2 * span + CIRC)
    w = int(2 * PAD + DOT // 2 + R + CIRC // 2 + CAP_GAP + _max_label_w())
    h = max(h, PAD * 2 + DOT)
    return w, h


def hub_xy(n_tiles, side):
    """Hub centre inside the fan window (depends on the opening side)."""
    w, h = fan_size(n_tiles)
    hx = PAD + DOT // 2 if side > 0 else w - PAD - DOT // 2
    return hx, h // 2


def fan_boxes(n_tiles, side):
    """Precompute boxes: (cx, cy, is_add, index). +x to the opening side."""
    items = shortcuts[:5]
    n = max(int(n_tiles), 1)
    angles = arc_angles(n)
    hx, hy = hub_xy(n, side)
    boxes = []
    for k, ang in enumerate(angles):
        rad = math.radians(ang)
        cx = hx + side * R * math.cos(rad)
        cy = hy + R * math.sin(rad)
        boxes.append((cx, cy, k >= len(items), k))
    return boxes, hx, hy


def arc_angles(n):
    n = max(int(n), 1)
    if n == 1:
        return [0.0]
    return [-ARC_HALF + i * (2 * ARC_HALF / (n - 1)) for i in range(n)]


assert fan_size(2)[1] == fan_size(1)[1]
assert fan_size(1)[0] > DOT
assert arc_angles(1) == [0.0]
assert len(arc_angles(5)) == 5


def clamp(x, y, w, h):
    # keep the whole window on-screen so the dot is always grabbable
    return [min(max(x, 0), max(SW - w, 0)), min(max(y, 0), max(SH - h, 0))]


if saved_pos:
    sx, sy = clamp(saved_pos[0], saved_pos[1], DOT, DOT)
else:
    sx, sy = clamp(SW - 100, SH // 2, DOT, DOT)  # visible default, not 1500x800
root.geometry(f"{DOT}x{DOT}+{sx}+{sy}")

expanded = False
hide_job = None
drag = {}
hidden_fs = False

dot = tk.Canvas(root, width=DOT, height=DOT, bg=KEY,
                highlightthickness=0, bd=0)
logo_img = None
logo_path = os.path.join(RES_DIR, "logo.png")
if ImageTk and os.path.exists(logo_path):
    logo_img = ImageTk.PhotoImage(Image.open(logo_path).resize((DOT, DOT)))
    dot.create_image(DOT // 2, DOT // 2, image=logo_img)
else:  # no Pillow/logo: drawn black disc with red ring
    dot.create_oval(2, 2, DOT - 2, DOT - 2, fill="#0c0c0c", outline=RED, width=3)
    dot.create_text(DOT // 2, DOT // 2 - 1, text="Q", fill=RED,
                    font=("Arial", 22, "bold"))
dot.pack()

# Half-circle fan: NO big dark disc. The window is fully transparent (KEY):
# only hub + black shortcut circles + small caption pills are painted.
# Black circles so light icons (white folders, docs) read easily.
# Caption = white text on a small dark pill BESIDE its circle
# (opening side, vertically centred), sized to the label text.
# Never below a circle and never overlapping the hub or the next tile.
# The fan auto-flips left/right at screen edges.
fan = tk.Canvas(root, bg=KEY, highlightthickness=0, bd=0)
fan._imgs = []
fan_hub_img = None
FAN_SIDE = 1  # +1 opens right, -1 opens left (set on expand)


def _fan_hub(hx, hy):
    """Draw the hub dot."""
    global fan_hub_img
    r = DOT // 2
    fan.create_oval(hx - r, hy - r, hx + r, hy + r,
                    fill=HUB_FILL, outline=HUB_RING, width=2)
    if logo_img is not None:
        fan_hub_img = logo_img  # bundled logo, already DOTxDOT
        fan.create_image(hx, hy, image=fan_hub_img, tags=("hub",))
    else:
        fan.create_text(hx, hy - 1, text="Q", fill="#ffffff",
                        font=("Arial", 20, "bold"), tags=("hub",))
    # "Qwik" on its own dark pill, not straight on the transparent
    # canvas: white text anti-aliased against the magenta
    # transparentcolor used to come out with a pink fringe (see the
    # screenshot). A pill gives the glyph a real background to blend
    # against, exactly like the caption pills.
    pw = _text_w(APP_NAME) + 20
    py1 = hy - r - 6
    fan.create_rectangle(hx - pw // 2, py1 - CAP_H, hx + pw // 2, py1,
                         fill=PILL_FILL, outline=PILL_EDGE, width=1,
                         tags=("hub",))
    fan.create_text(hx, py1 - CAP_H // 2, text=APP_NAME,
                    fill=FG_TEXT, font=FONT_TITLE, anchor="center",
                    tags=("hub",))


def draw_fan():
    fan.delete("all")
    fan._imgs = []
    items = shortcuts[:5]
    n = _tile_count()
    w, h = fan_size(n)
    fan.config(width=w, height=h)
    boxes, hx, hy = fan_boxes(n, FAN_SIDE)
    _fan_hub(hx, hy)
    for cx, cy, is_add, k in boxes:
        r = CIRC // 2
        tag = f"s{k}"
        fan.create_oval(cx - r, cy - r, cx + r, cy + r,
                        fill=CIRCLE_FILL, outline=CIRCLE_EDGE, width=2,
                        tags=(tag,))
        if not is_add:
            s = items[k]
            icon = file_icon(s.get("path", ""), ICON)
            if icon is not None:
                fan._imgs.append(icon)
                fan.create_image(cx, cy, image=icon, tags=(tag,))
            else:
                letter = (_short_name(s.get("name", "?"))[:1] or "?").upper()
                fan.create_text(cx, cy, text=letter, fill=FG_TEXT,
                                font=("Segoe UI", 18, "bold"), anchor="center",
                                tags=(tag,))
        else:
            fan.create_text(cx, cy, text="+", fill=FG_TEXT,
                            font=("Segoe UI", 20, "bold"), anchor="center",
                            tags=(tag,))
        # caption pill BESIDE the circle, vertically centred on it,
        # on the opening side. The old pill sat below the circle with
        # a fixed 76 px width: with 4 tiles its bottom overlapped the
        # next circle by 25 px (46 px with 5 tiles), and "Screenshots"
        # was wider than the pill itself. Beside the circle a pill can
        # never meet the next tile, and its width is measured per label.
        label = "Add" if is_add else _short_name(items[k].get("name", "?"))
        lw = _label_w(label)
        if FAN_SIDE > 0:
            px0, px1 = cx + r + CAP_GAP, cx + r + CAP_GAP + lw
        else:
            px1, px0 = cx - r - CAP_GAP, cx - r - CAP_GAP - lw
        py = cy - CAP_H // 2
        fan.create_rectangle(px0, py, px1, py + CAP_H,
                             fill=PILL_FILL, outline=PILL_EDGE, width=1,
                             tags=(tag,))
        fan.create_text((px0 + px1) // 2, cy, text=label,
                        fill=FG_TEXT, font=FONT_CAP, anchor="center",
                        tags=(tag,))
        if not is_add:
            fan.tag_bind(tag, "<ButtonRelease-1>", lambda e, i=k: launch(i))
            fan.tag_bind(tag, "<Button-3>", lambda e, i=k: ctx_menu(e, i))
        else:
            fan.tag_bind(tag, "<ButtonRelease-1>", lambda e: add_menu())


def refresh_rows():
    # Redraw the fan when visible so add/delete/reorder show immediately.
    if expanded:
        draw_fan()


# one-click system picks: only existing paths shown, folders and apps alike
def candidates():
    home = os.path.expanduser('~')
    sys32 = os.path.join(os.environ.get('SystemRoot', r'C:\Windows'), 'System32')
    picks = [
        ('Downloads', os.path.join(home, 'Downloads')),
        ('Pictures', os.path.join(home, 'Pictures')),
        ('Screenshots', os.path.join(home, 'Pictures', 'Screenshots')),
        ('Desktop', os.path.join(home, 'Desktop')),
        ('PowerShell', os.path.join(sys32, 'WindowsPowerShell', 'v1.0', 'powershell.exe')),
        ('Notepad', os.path.join(sys32, 'notepad.exe')),
        ('Calculator', os.path.join(sys32, 'calc.exe')),
        ('Media Player Legacy', r'C:\Program Files\Windows Media Player\wmplayer.exe'),
        ('Task Manager', os.path.join(sys32, 'Taskmgr.exe')),
    ]
    have = {s['path'].lower() for s in shortcuts}
    return [(n, p) for n, p in picks
            if p.lower() not in have and os.path.exists(p)]


def add_menu():
    m = tk.Menu(root, tearoff=0)
    for name, path in candidates():
        m.add_command(label=name, command=lambda n=name, p=path: add_path(p, n))
    m.add_separator()
    m.add_command(label='File...', command=pick_file)
    m.add_command(label='Folder...', command=pick_folder)
    m.tk_popup(root.winfo_pointerx(), root.winfo_pointery())


def add_path(p, name=None):
    if len(shortcuts) >= 5:
        return
    p = os.path.normpath(p)  # SHGetFileInfo needs backslashes, not / or //
    name = name or os.path.splitext(os.path.basename(p.rstrip(chr(92))))[0] or p
    shortcuts.append({'name': name, 'path': p, 'uses': 0})
    save_cfg(shortcuts, dot_pos())
    refresh_rows()
    set_expanded(True)


def pick_file():
    p = filedialog.askopenfilename(title='Pick app or file',
                                   filetypes=[('Programs', '*.exe *.lnk'), ('All', '*.*')])
    if p:
        add_path(p)


def pick_folder():
    p = filedialog.askdirectory(title='Pick a folder')
    if p:
        add_path(p)


def add_shortcut():
    add_menu()


def set_expanded(on):
    global expanded, hide_job, FAN_SIDE
    was_expanded = expanded
    expanded = on
    if on:
        if hide_job:
            root.after_cancel(hide_job)
            hide_job = None
        n = _tile_count()
        w, h = fan_size(n)
        # Anchor the hub: the fan window is positioned so the hub
        # centre lands exactly on the dot's centre. The old code put
        # the fan window's top-left corner where the dot was, so the
        # hub jumped ~175 px down on every expand, and after a
        # left-open the dot landed 174 px left on collapse.
        dot = geom_pos() or [sx, sy]
        hub_cx, hub_cy = dot[0] + DOT // 2, dot[1] + DOT // 2
        # if the fan would leave the screen, flip it open the other
        # way; if it still would not fit, clamp into view.
        FAN_SIDE = pick_side(hub_cx, w - (PAD + DOT // 2))
        hx, hy = hub_xy(n, FAN_SIDE)
        x, y = hub_cx - hx, hub_cy - hy
        x, y = clamp(x, y, w, h)
        dot.pack_forget()
        fan.pack(fill="both", expand=True)
        draw_fan()
        root.update_idletasks()  # overrideredirect ignores a size set before items exist
        w, h = max(w, root.winfo_reqwidth()), max(h, root.winfo_reqheight())
        x, y = clamp(x, y, w, h)  # expanded fan also stays on-screen
        root.geometry(f"{w}x{h}+{x}+{y}")
        root.attributes("-alpha", 1.0)
    else:
        fan.pack_forget()
        if not dot.winfo_ismapped():
            dot.pack()
        if was_expanded:
            # collapse back onto the hub, not onto the fan window's
            # top-left corner.
            hx, hy = hub_xy(_tile_count(), FAN_SIDE)
            win = geom_pos() or [sx, sy]
            x, y = win[0] + hx - DOT // 2, win[1] + hy - DOT // 2
        else:
            x, y = geom_pos() or [sx, sy]
        x, y = clamp(x, y, DOT, DOT)
        root.geometry(f"{DOT}x{DOT}+{x}+{y}")
        root.attributes("-alpha", ALPHA_IDLE)


def schedule_collapse():
    global hide_job
    if hide_job:
        root.after_cancel(hide_job)
    hide_job = root.after(COLLAPSE_MS, lambda: set_expanded(False))


def launch(i):
    try:
        os.startfile(shortcuts[i]["path"])  # exe and folder alike
    except Exception as e:
        print("open failed:", e)
        return
    shortcuts[i]["uses"] = shortcuts[i].get("uses", 0) + 1
    shortcuts.sort(key=lambda s: s.get("uses", 0), reverse=True)
    save_cfg(shortcuts, dot_pos())
    refresh_rows()
    set_expanded(False)


def geom_pos():
    try:
        parts = root.geometry().replace("x", "+").split("+")
        return [int(parts[-2]), int(parts[-1])]  # geometry is WxH+X+Y
    except Exception:
        return saved_pos


def dot_pos():
    """Collapsed dot position for the current window.

    shortcuts.toml stores one position, the dot's. While the fan is
    open geom_pos() is the fan window's top-left corner, which is not
    the dot's position at all, so saving it directly moved the dot
    every time the panel was dragged or a shortcut was used.
    """
    pos = geom_pos()
    if not pos:
        return saved_pos
    if expanded:
        hx, hy = hub_xy(_tile_count(), FAN_SIDE)
        return [pos[0] + hx - DOT // 2, pos[1] + hy - DOT // 2]
    return pos


def ctx_menu(e, i):
    m = tk.Menu(root, tearoff=0)
    m.add_command(label="Open", command=lambda: launch(i))
    m.add_command(label="Move up", command=lambda: move(i, -1))
    m.add_command(label="Move down", command=lambda: move(i, 1))
    m.add_command(label="Delete", command=lambda: delete(i))
    m.tk_popup(e.x_root, e.y_root)


def move(i, d):
    j = min(max(i + d, 0), len(shortcuts) - 1)
    shortcuts[i], shortcuts[j] = shortcuts[j], shortcuts[i]
    save_cfg(shortcuts, dot_pos())
    refresh_rows()


def delete(i):
    del shortcuts[i]
    save_cfg(shortcuts, dot_pos())
    refresh_rows()
    set_expanded(len(shortcuts) > 0)


def poll_fullscreen():
    # hide while a fullscreen app/game is presenting, like the Rust build
    global hidden_fs
    fs = is_fullscreen()
    if fs != hidden_fs:
        hidden_fs = fs
        root.withdraw() if fs else root.deiconify()
    root.after(2000, poll_fullscreen)


if len(sys.argv) > 1 and sys.argv[1] == "--check-icons":
    # self-check: extract every configured shortcut's icon without opening the GUI
    ok = True
    for s in shortcuts:
        raw = s.get("path", "")
        ic = _extract_icon(os.path.normpath(raw), 24)  # same normpath as file_icon
        print(("OK   " if ic else "FAIL"), s.get("name"), "->", raw)
        ok = ok and ic is not None
    sys.exit(0 if ok else 1)


def toggle_panel(_e=None):
    # Ctrl+Q: show the chosen apps without touching the mouse
    if expanded:
        set_expanded(False)
    else:
        if hidden_fs:
            return  # hidden by fullscreen guard
        try:
            root.deiconify()
            root.lift()
        except tk.TclError:
            pass
        set_expanded(True)


def _ctrl_q_watcher():
    # Global Ctrl+Q without extra deps: poll Ctrl+Q edge, toggle via after().
    import time
    try:
        u32 = ctypes.windll.user32
    except Exception:
        return
    VK_CTRL, VK_Q = 0x11, 0x51
    was_down = False
    while True:
        try:
            ctrl = (u32.GetAsyncKeyState(VK_CTRL) & 0x8000) != 0
            q = (u32.GetAsyncKeyState(VK_Q) & 0x8000) != 0
            down = ctrl and q
            if down and not was_down:
                try:
                    root.after(0, toggle_panel)
                except tk.TclError:
                    return
                time.sleep(0.4)  # debounce: one toggle per press
            was_down = down
            time.sleep(0.05)
        except Exception:
            return


root.bind("<Enter>", lambda e: set_expanded(True))
root.bind("<Leave>", lambda e: schedule_collapse())
root.bind_all("<Control-q>", toggle_panel)
root.bind_all("<Control-Q>", toggle_panel)
# drag from anywhere (dot or fan panel); position persists on release
for w in (root, dot, fan):
    w.bind("<ButtonPress-1>", lambda e: drag.update(x=e.x_root, y=e.y_root,
                                                    ox=root.winfo_x(), oy=root.winfo_y()))
    w.bind("<B1-Motion>", lambda e: root.geometry(
        f"+{drag['ox'] + e.x_root - drag['x']}+{drag['oy'] + e.y_root - drag['y']}"))
    w.bind("<ButtonRelease-1>", lambda e: save_cfg(shortcuts, dot_pos()))

refresh_rows()
poll_fullscreen()
threading.Thread(target=_ctrl_q_watcher, daemon=True).start()
root.mainloop()
