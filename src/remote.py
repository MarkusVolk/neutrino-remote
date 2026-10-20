"""Shared helpers of the neutrino-remote frontends: settings, the drawn remote and the REST API."""

import json
import os
import re
import shutil
import time
import urllib.parse

DEFAULT_HOST = "192.168.0.1"



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


def _box_name(host):
    return re.sub(r"[^\w.-]", "_", host.strip().rstrip("/"))


def token_file(host=None):
    name = "token-" + _box_name(host) if host else "token"
    return os.path.join(os.path.dirname(config_file()), name)


def load_token(host):
    """A bearer token of the box's REST API, for a box that asks for one: the one kept
    for this box, else one for every box; without one the box decides by the network
    the remote is in, or by a sign-in."""
    for path in (token_file(host), token_file()):
        try:
            with open(path, encoding="utf-8") as handle:
                token = handle.read().strip()
        except OSError:
            continue
        if token:
            return token
    return ""


def _write_private(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(text)


def save_token(host, token):
    _write_private(token_file(host), token.strip() + "\n")


def clear_token(host):
    try:
        os.remove(token_file(host))
    except OSError:
        pass


def new_token():
    """32 lower-case hex digits, the shortest token ni-neutrino takes."""
    return os.urandom(16).hex()


def token_lines(token):
    """What the box needs to know a token, for both kinds of box."""
    return (f"ni-neutrino, /var/tuxbox/config/ni-web.conf:\napi_tokens=write:{token}\n"
            f"Neutrino, nhttpd.conf:\napi.tokens=write:{token}")


LOGIN_PATH = "api/v1/login"
LOGIN_USER = "root"
SESSION_COOKIE = "ni-web-session"
CSRF_HEADER = "X-CSRF-Token"


def session_file(host):
    return os.path.join(os.path.dirname(config_file()), "session-" + _box_name(host))


def load_session(host):
    """The session a sign-in opened on a box: (cookie value, csrf token), or None."""
    try:
        with open(session_file(host), encoding="utf-8") as handle:
            data = json.load(handle)
        return data["cookie"], data["csrf"]
    except (OSError, ValueError, KeyError, TypeError):
        return None


def save_session(host, cookie, csrf):
    _write_private(session_file(host), json.dumps({"cookie": cookie, "csrf": csrf}))


def clear_session(host):
    try:
        os.remove(session_file(host))
    except OSError:
        pass


def session_cookie(set_cookie):
    """The value of the session cookie in a Set-Cookie header."""
    for part in (set_cookie or "").split(";"):
        name, _, value = part.strip().partition("=")
        if name == SESSION_COOKIE and value:
            return value
    return ""


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


def load_layout():
    """The drawn remote control: installed next to this file, or in data/ of the source tree."""
    here = os.path.dirname(os.path.realpath(__file__))
    for path in (os.path.join(here, "remote-layout.json"),
                 os.path.join(os.path.dirname(here), "data", "remote-layout.json")):
        try:
            with open(path, encoding="utf-8") as handle:
                return json.load(handle)
        except (OSError, ValueError):
            continue
    return None


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


OSD_AFTER_KEY = (250, 2000)
OSD_IDLE = 5
EPG_WINDOW = 6 * 3600

# The box speaks the REST API of /api/v1 (as ni-neutrino does), or only the old
# control API of nhttpd; which one is asked once on connecting.
API = "v1"
CONTROL = "control"
PROBE_PATH = "api/v1/system/info"
CONTROL_PROBE_PATH = "control/info"


def osd_shot_path(api):
    if api == API:
        return "api/v1/osd/screenshot?osd=true&video=false&format=png"
    return "control/screenshot?name=neutrino-remote&osd=1&video=0&format=png"


def osd_image_path(api):
    """Where the picture of a shot is read; the REST API answers the shot with it."""
    return None if api == API else "tmp/neutrino-remote.png"


def key_request(api, key):
    """(method, path, JSON body or None) that sends a key."""
    if api == API:
        return "POST", "api/v1/osd/remote/key", {"name": key}
    return "GET", "control/rcem?" + key, None


def standby_path(api):
    return "api/v1/system/standby" if api == API else "control/standby"


def standby_on(api, text):
    if api == API:
        return bool(json.loads(text).get("on"))
    return text.strip() == "on"


def bouquets_path(api):
    return "api/v1/bouquets" if api == API else "control/getbouquets?format=json"


def parse_bouquets(api, text):
    """The bouquets that hold television channels, as (number, name, web); the web
    channel lists come first, as in the web interface."""
    if api == API:
        items = [b for b in json.loads(text).get("items", [])
                 if not b.get("hidden") and b.get("tv_count", 0) > 0]
        items.sort(key=lambda b: b.get("kind", "dvb") == "dvb")
        return [(b["id"], b["name"], b.get("kind", "dvb") != "dvb") for b in items]
    data = json.loads(text).get("data", {})
    return [(b["number"], b["name"], False) for b in data.get("bouquets", [])]


def channels_path(bouquet, cursor=None):
    path = f"api/v1/channels?bouquet={bouquet}&limit=500"
    return path + f"&cursor={cursor}" if cursor else path


def grid_path(bouquet, cursor=None):
    now = int(time.time())
    path = f"api/v1/epg/grid?bouquet={bouquet}&from={now}&to={now + EPG_WINDOW}&limit=100"
    return path + f"&cursor={cursor}" if cursor else path


def control_channels_path(bouquet):
    return f"control/getbouquet?bouquet={bouquet}&format=json&epg=true&epginfo=false"


def current_path(api):
    return "api/v1/channels/current" if api == API else "control/zapto"


def current_id(api, text):
    if not text:
        return ""
    return json.loads(text).get("id", "") if api == API else text.strip()


def parse_page(text):
    """The items of one page of a list and the cursor of the next page, if any."""
    data = json.loads(text)
    return data.get("items", []), data.get("next_cursor")


def _event(event, now):
    if not event:
        return None
    start, duration = int(event["start"]), int(event["duration"])
    percent = max(0, min(100, (now - start) * 100 // duration)) if duration > 0 else -1
    return {"start": time.strftime("%H:%M", time.localtime(start)), "title": event["title"],
            "percent": percent, "end": start + duration, "id": event["id"], "begin": start}


def build_channels(channels, grid, epg_first=False):
    """The channels of a bouquet from the REST API, each with the programme that is
    on (now) and the next one, where the box knows them; with epg_first the channels
    with a programme come first, as the web interface lists the web channels."""
    now = int(time.time())
    events = {row["channel_id"]: sorted(row.get("events", []), key=lambda e: int(e["start"]))
              for row in grid}
    out = []
    for c in channels:
        evs = [e for e in events.get(c["id"], []) if int(e["start"]) + int(e["duration"]) > now]
        current = [e for e in evs if int(e["start"]) <= now]
        upcoming = [e for e in evs if int(e["start"]) > now]
        out.append({"number": str(c["number"]), "id": c["id"], "name": c["name"],
                    "now": _event(current[0] if current else None, now),
                    "next": _event(upcoming[0] if upcoming else None, now)})
    if epg_first:
        out.sort(key=lambda c: c["now"] is None and c["next"] is None)
    return out


def _control_event(epg):
    if not isinstance(epg, dict) or not epg.get("description"):
        return None
    try:
        percent = max(0, min(100, int(epg.get("percentage", -1))))
    except ValueError:
        percent = -1
    try:
        end = int(time.time()) + (int(epg["timeTotal"]) - int(epg["timeElapsed"])) * 60
    except (KeyError, ValueError):
        end = 0
    return {"start": epg.get("startTime", ""), "title": epg["description"], "percent": percent,
            "end": end, "id": "", "begin": 0}


def parse_control_channels(text):
    """The channels of a bouquet from getbouquet?format=json&epg=true of the control API."""
    data = json.loads(text).get("data", {})
    return [{"number": c["number"], "id": c["id"], "name": c["name"],
             "now": _control_event(c.get("firstEPG")), "next": _control_event(c.get("secondEPG"))}
            for c in data.get("channels", [])]


def zap_request(api, channel_id):
    if api == API:
        return "POST", "api/v1/zap", {"channel_id": channel_id}
    return "GET", "control/zapto?" + channel_id, None


def record_request(api, channel):
    """A record timer for the programme that is on, from now to its end; the box adds
    its own lead and follow-up time. None when nothing is on."""
    now = channel["now"]
    if not now or now["end"] <= time.time():
        return None
    if api == API:
        body = {"kind": "record", "channel_id": channel["id"], "start": int(time.time()),
                "stop": now["end"], "title": now["title"], "recording_safety": True}
        if now["id"]:
            body.update(epg_id=now["id"], epg_start=now["begin"])
        return "POST", "api/v1/timers", body
    query = urllib.parse.urlencode({"action": "new", "type": 5, "channel_id": channel["id"],
                                    "alarm": int(time.time()), "stop": now["end"], "rs": 1})
    return "GET", "control/timer?" + query, None


def stream_path(api, channel_id):
    return ("api/v1/stream/" if api == API else "control/streamurl?id=") + channel_id


def stream_url(api, text):
    if not text:
        return ""
    return json.loads(text).get("url", "") if api == API else text.strip()


PLAYERS = ("mpv", "celluloid", "vlc")


def player_command(url):
    for player in PLAYERS:
        if shutil.which(player):
            return [player, url]
    return None


def epg_tooltip(channel):
    lines = []
    for label, event in (("Now", channel["now"]), ("Next", channel["next"])):
        if event:
            lines.append(f"{label}: {event['start']}  {event['title']}")
    return "\n".join(lines) or None


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
