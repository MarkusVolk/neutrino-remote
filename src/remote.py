"""Shared helpers of the neutrino-remote frontends: settings and the web interface."""

import json
import os
import re
import shutil
import urllib.parse

DEFAULT_HOST = "192.168.0.1"

AREA_RE = re.compile(r"<area\b([^>]*)>", re.I)
ATTR_RE = re.compile(r"""(\w+)\s*=\s*("([^"]*)"|'([^']*)')""")
IMG_RE = re.compile(r"""<img\b[^>]*\bsrc\s*=\s*["']([^"']+)["'][^>]*\busemap\b""", re.I)
KEY_RE = re.compile(r"rcsim\(\s*['\"](KEY_\w+)['\"]\s*\)")


def config_file():
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return os.path.join(base, "neutrino-remote", "host")


def load_host():
    try:
        with open(config_file(), encoding="utf-8") as handle:
            host = handle.read().strip()
    except OSError:
        host = ""
    return host or DEFAULT_HOST


def save_host(host):
    path = config_file()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(host.strip() + "\n")


def side_file():
    return os.path.join(os.path.dirname(config_file()), "list")


def load_side():
    try:
        with open(side_file(), encoding="utf-8") as handle:
            side = handle.read().strip()
    except OSError:
        side = ""
    return side if side in ("left", "right") else "left"


def save_side(side):
    path = side_file()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(side + "\n")


LOCAL_PORT = 8080
LOCAL_RE = re.compile(r"^(localhost|127(\.\d+){3}|\[::1\])$", re.I)
LOCAL_PROGRAM = "neutrino-desktop"


def is_local(host):
    return bool(LOCAL_RE.match(host.strip().rstrip("/")))


def local_start_command():
    """How to start Neutrino on this machine so that it outlives the remote:
    neutrino-desktop runs bwrap with --die-with-parent."""
    if not shutil.which(LOCAL_PROGRAM):
        return None
    if shutil.which("systemd-run"):
        return ["systemd-run", "--user", "--quiet", "--collect", LOCAL_PROGRAM]
    if shutil.which("setsid"):
        return ["setsid", "-f", LOCAL_PROGRAM]
    return [LOCAL_PROGRAM]


def base_url(host):
    """The box's web interface; a Neutrino on this machine runs without root
    and cannot use port 80, its nhttpd listens on 8080."""
    host = host.strip().rstrip("/")
    if LOCAL_RE.match(host):
        host = f"{host}:{LOCAL_PORT}"
    if not re.match(r"^https?://", host):
        host = "http://" + host
    return host + "/"


def cache_dir(host):
    base = os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache")
    name = re.sub(r"[^\w.-]", "_", host.strip().rstrip("/"))
    return os.path.join(base, "neutrino-remote", name)


def save_cache(host, areas, image):
    """Keep the remote of a box, so it can be shown while the box is off."""
    path = cache_dir(host)
    os.makedirs(path, exist_ok=True)
    with open(os.path.join(path, "remote.json"), "w", encoding="utf-8") as handle:
        json.dump(areas, handle)
    with open(os.path.join(path, "remote.img"), "wb") as handle:
        handle.write(image)


def load_cache(host):
    path = cache_dir(host)
    try:
        with open(os.path.join(path, "remote.json"), encoding="utf-8") as handle:
            areas = json.load(handle)
        with open(os.path.join(path, "remote.img"), "rb") as handle:
            image = handle.read()
    except (OSError, ValueError):
        return None
    return areas, image


def parse_remote(html, base):
    """The remote control picture and its key areas from Y_Tools_Rcsim.yhtm."""
    img = IMG_RE.search(html)
    if not img:
        return None
    areas = []
    for match in AREA_RE.finditer(html):
        attrs = {m.group(1).lower(): m.group(3) if m.group(3) is not None else m.group(4)
                 for m in ATTR_RE.finditer(match.group(1))}
        key = KEY_RE.search(attrs.get("href", ""))
        try:
            coords = [int(float(c)) for c in attrs.get("coords", "").split(",") if c.strip()]
        except ValueError:
            continue
        shape = attrs.get("shape", "rect").lower()
        if not key or (shape == "circle" and len(coords) != 3) or (shape != "circle" and len(coords) < 4):
            continue
        title = attrs.get("title") or attrs.get("alt") or key.group(1)[4:].replace("_", " ").title()
        areas.append({"key": key.group(1), "shape": shape, "coords": coords, "title": title})
    return {"image": urllib.parse.urljoin(base, img.group(1)), "areas": areas}


def area_contains(area, x, y):
    c = area["coords"]
    if area["shape"] == "circle":
        return (x - c[0]) ** 2 + (y - c[1]) ** 2 <= c[2] ** 2
    if area["shape"] in ("poly", "polygon"):
        pts = list(zip(c[0::2], c[1::2]))
        inside = False
        for (x1, y1), (x2, y2) in zip(pts, pts[1:] + pts[:1]):
            if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
                inside = not inside
        return inside
    return min(c[0], c[2]) <= x <= max(c[0], c[2]) and min(c[1], c[3]) <= y <= max(c[1], c[3])


def area_bounds(area):
    c = area["coords"]
    if area["shape"] == "circle":
        return c[0] - c[2], c[1] - c[2], 2 * c[2], 2 * c[2]
    xs, ys = c[0::2], c[1::2]
    return min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)


def parse_bouquets(text):
    data = json.loads(text).get("data", {})
    return [(b["number"], b["name"]) for b in data.get("bouquets", [])]


def parse_channels(text):
    data = json.loads(text).get("data", {})
    return [(c["number"], c["id"], c["name"]) for c in data.get("channels", [])]


KEYBOARD = {
    "Up": "KEY_UP", "Down": "KEY_DOWN", "Left": "KEY_LEFT", "Right": "KEY_RIGHT",
    "Return": "KEY_OK", "KP_Enter": "KEY_OK", "space": "KEY_OK",
    "Escape": "KEY_HOME", "BackSpace": "KEY_HOME",
    "m": "KEY_SETUP", "i": "KEY_INFO", "e": "KEY_EPG", "f": "KEY_FAVORITES",
    "plus": "KEY_VOLUMEUP", "KP_Add": "KEY_VOLUMEUP",
    "minus": "KEY_VOLUMEDOWN", "KP_Subtract": "KEY_VOLUMEDOWN",
    "Page_Up": "KEY_PAGEUP", "Page_Down": "KEY_PAGEDOWN",
    "F1": "KEY_RED", "F2": "KEY_GREEN", "F3": "KEY_YELLOW", "F4": "KEY_BLUE",
    "t": "KEY_TEXT", "a": "KEY_AUDIO", "h": "KEY_HELP", "r": "KEY_RADIO", "v": "KEY_TV",
}
for _n in range(10):
    KEYBOARD[str(_n)] = f"KEY_{_n}"
    KEYBOARD[f"KP_{_n}"] = f"KEY_{_n}"
