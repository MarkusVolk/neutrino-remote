import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Controls.impl
import QtQuick.Layouts
import QtQuick.Window

ApplicationWindow {
    id: root

    readonly property color bg: "#191c22"
    readonly property color panel: "#21252d"
    readonly property color raised: "#272c36"
    readonly property color line: "#333a47"
    readonly property color fg: "#d7dce5"
    readonly property color dim: "#8b95a6"
    readonly property color accent: "#67aee8"
    readonly property color errorFg: "#e79a9a"

    property string host: ""
    property string configFile: ""
    property string listSide: "left"
    property string base: ""
    property var areas: []
    property var hot: null
    property var flash: null
    property string statusText: ""
    property bool statusError: false
    property var bouquetNumbers: []
    property string currentChannel: ""
    property real aspect: 188 / 762
    property int canvasW: 0
    property int canvasH: 0
    property bool osdBusy: false
    property bool osdAgain: false
    property int osdShown: 0
    property real lastKey: 0
    /* the box speaks the REST API of /api/v1 (as ni-neutrino does), or only the old
     * control API of nhttpd; which one is asked once on connecting */
    property bool legacy: false
    /* a session the box opened on signing in: its cookie lives in the engine's jar */
    property string csrf: ""
    property var waiting: []
    readonly property string sessionCookie: "ni-web-session"
    readonly property string osdShot: "api/v1/osd/screenshot?osd=true&video=false&format=png"
    readonly property string legacyShot: "control/screenshot?name=neutrino-remote&osd=1&video=0&format=png"
    readonly property string legacyImage: "tmp/neutrino-remote.png"
    readonly property int epgWindow: 6 * 3600

    title: "Neutrino Remote"
    color: bg
    visible: false

    function fitToScreen() {
        var header = 48
        var viewH = Math.round(Screen.height * 0.6) - header
        var w = Math.max(260, Math.round(viewH * aspect) + 24)
        if (sideBar.visible)
            w += Math.max(320, Math.round(Screen.width * 0.25))
        width = w
        height = viewH + header
    }

    function baseUrl(h) {
        h = h.trim().replace(/\/+$/, "")
        if (/^(localhost|127(\.\d+){3}|\[::1\])$/i.test(h))
            h += ":8080"
        if (!/^https?:\/\//.test(h))
            h = "http://" + h
        return h + "/"
    }

    function showStatus(text, error) {
        statusText = text
        statusError = !!error
    }

    function get(path, callback, quiet) {
        request("GET", path, null, callback, quiet)
    }

    function post(path, body, callback, quiet) {
        request("POST", path, body, callback, quiet)
    }

    /* a bearer token of the box's REST API, for a box that asks for one */
    /* the token kept for this box, else one for every box */
    function boxName() {
        return host.trim().replace(/\/+$/, "").replace(/[^\w.-]/g, "_")
    }

    function tokenFile() {
        return configFile.replace(/[^\/]*$/, "token-" + boxName())
    }

    function token() {
        if (!configFile)
            return ""
        var files = [tokenFile(), configFile.replace(/[^\/]*$/, "token")]
        for (var i = 0; i < files.length; i++) {
            var t = native.exists(files[i]) ? native.readText(files[i]).trim() : ""
            if (t)
                return t
        }
        return ""
    }

    function tokenLines(t) {
        return "ni-neutrino, /var/tuxbox/config/ni-web.conf:\napi_tokens=write:" + t
            + "\nNeutrino, nhttpd.conf:\napi.tokens=write:" + t
    }

    function useToken() {
        if (configFile)
            native.writePrivate(tokenFile(), tokenField.text.trim() + "\n")
        showStatus("Token kept for " + host)
        finishSignIn(true)
    }

    function request(method, path, body, callback, quiet, retried) {
        var xhr = new XMLHttpRequest()
        var url = /^https?:\/\//.test(path) ? path : base + path
        var t = token()
        xhr.onreadystatechange = function() {
            if (xhr.readyState !== XMLHttpRequest.DONE)
                return
            if (xhr.status === 403 && !legacy && !retried && path.indexOf("api/v1/") === 0) {
                if (t)
                    native.remove(tokenFile())
                else if (csrf)
                    clearSession()
                signIn(function(ok) {
                    if (ok)
                        request(method, path, body, callback, quiet, true)
                    else
                        callback(null)
                }, !!t)
                return
            }
            if (Math.floor(xhr.status / 100) !== 2) {
                if (!quiet)
                    showStatus(host + ": " + (xhr.status ? "HTTP " + xhr.status : "not reachable"), true)
                callback(null)
                return
            }
            callback(xhr.responseText)
        }
        xhr.timeout = 5000
        xhr.open(method, url)
        if (t)
            xhr.setRequestHeader("Authorization", "Bearer " + t)
        else if (csrf && method !== "GET")
            xhr.setRequestHeader("X-CSRF-Token", csrf)
        if (body !== null) {
            xhr.setRequestHeader("Content-Type", "application/json")
            xhr.send(JSON.stringify(body))
        } else {
            xhr.send()
        }
    }

    /* every page of a list, handed on as one list; null when a page failed */
    function getAll(pathOf, callback, quiet, items, cursor) {
        items = items || []
        get(pathOf(cursor), function(text) {
            if (text === null) {
                callback(null)
                return
            }
            var data
            try {
                data = JSON.parse(text)
            } catch (e) {
                callback(null)
                return
            }
            items = items.concat(data.items || [])
            if (data.next_cursor)
                getAll(pathOf, callback, quiet, items, data.next_cursor)
            else
                callback(items)
        }, quiet)
    }

    function sessionFile() {
        return configFile.replace(/[^\/]*$/, "session-" + host.trim().replace(/\/+$/, "").replace(/[^\w.-]/g, "_"))
    }

    function loadSession() {
        csrf = ""
        var file = sessionFile()
        if (!configFile || !native.exists(file))
            return
        try {
            var data = JSON.parse(native.readText(file))
            native.setCookie(base, sessionCookie, data.cookie)
            csrf = data.csrf || ""
        } catch (e) {
        }
    }

    function clearSession() {
        csrf = ""
        native.remove(sessionFile())
    }

    /* a box that wants a sign-in for this asks for a name and password; what it answers
     * with is kept, the password is not. Requests that come in meanwhile wait for it. */
    function signIn(then, tokenRefused) {
        var w = waiting
        w.push(then)
        waiting = w
        if (!loginDialog.visible) {
            loginNote.text = tokenRefused ? "The box did not take the token." : "The box asks for a sign-in to be controlled."
            loginNote.color = tokenRefused ? errorFg : dim
            passField.text = ""
            tokenField.text = ""
            loginDialog.open()
            passField.forceActiveFocus()
        }
    }

    function finishSignIn(ok) {
        var w = waiting
        waiting = []
        loginDialog.close()
        for (var i = 0; i < w.length; i++)
            w[i](ok)
    }

    function submitSignIn() {
        signInButton.enabled = false
        var xhr = new XMLHttpRequest()
        xhr.onreadystatechange = function() {
            if (xhr.readyState !== XMLHttpRequest.DONE)
                return
            signInButton.enabled = true
            if (xhr.status === 200) {
                var answer = {}
                try {
                    answer = JSON.parse(xhr.responseText)
                } catch (e) {
                }
                var cookie = native.cookie(base, sessionCookie)
                if (cookie && answer.csrf) {
                    csrf = answer.csrf
                    if (configFile)
                        native.writePrivate(sessionFile(), JSON.stringify({ cookie: cookie, csrf: csrf }))
                    showStatus("Signed in to " + host)
                    finishSignIn(true)
                    return
                }
            }
            loginNote.text = xhr.status === 401 ? "Name and password do not go together."
                           : xhr.status === 429 ? "Too many wrong attempts, wait a moment."
                           : "Sign-in failed" + (xhr.status ? " (HTTP " + xhr.status + ")" : "") + "."
            loginNote.color = errorFg
        }
        xhr.timeout = 5000
        xhr.open("POST", base + "api/v1/login")
        xhr.setRequestHeader("Content-Type", "application/json")
        xhr.send(JSON.stringify({ user: userField.text, password: passField.text }))
    }

    function saveHost(h) {
        if (!configFile)
            return
        var xhr = new XMLHttpRequest()
        xhr.open("PUT", "file://" + configFile)
        xhr.send(h + "\n")
    }

    function contains(area, x, y) {
        var c = area.coords
        if (area.shape === "circle")
            return (x - c[0]) * (x - c[0]) + (y - c[1]) * (y - c[1]) <= c[2] * c[2]
        if (area.shape === "poly" || area.shape === "polygon") {
            var inside = false
            for (var i = 0, j = c.length - 2; i < c.length; j = i, i += 2) {
                if ((c[i + 1] > y) !== (c[j + 1] > y)
                        && x < (c[j] - c[i]) * (y - c[i + 1]) / (c[j + 1] - c[i + 1]) + c[i])
                    inside = !inside
            }
            return inside
        }
        return Math.min(c[0], c[2]) <= x && x <= Math.max(c[0], c[2])
            && Math.min(c[1], c[3]) <= y && y <= Math.max(c[1], c[3])
    }

    function bounds(area) {
        var c = area.coords
        if (area.shape === "circle")
            return { x: c[0] - c[2], y: c[1] - c[2], w: 2 * c[2], h: 2 * c[2] }
        var xs = [], ys = []
        for (var i = 0; i + 1 < c.length; i += 2) {
            xs.push(c[i])
            ys.push(c[i + 1])
        }
        var x0 = Math.min.apply(null, xs), y0 = Math.min.apply(null, ys)
        return { x: x0, y: y0, w: Math.max.apply(null, xs) - x0, h: Math.max.apply(null, ys) - y0 }
    }

    function areaAt(x, y) {
        if (keysView.s <= 0)
            return null
        var px = (x - keysView.ox) / keysView.s
        var py = (y - keysView.oy) / keysView.s
        for (var i = 0; i < areas.length; i++)
            if (contains(areas[i], px, py))
                return areas[i]
        return null
    }

    function connectTo(h) {
        h = h.trim()
        if (!h)
            return
        host = h
        base = baseUrl(h)
        saveHost(h)
        loadSession()
        showStatus("Connecting to " + h + " ...")
        showDrawn()
    }

    property bool connected: false

    /* the drawn remote control, installed next to this file or in data/ of the source tree */
    function loadLayout() {
        var names = ["remote-layout.json", "../data/remote-layout.json"]
        for (var i = 0; i < names.length; i++) {
            var path = Qt.resolvedUrl(names[i]).toString().replace(/^file:\/\//, "")
            if (!native.exists(path))
                continue
            try {
                return JSON.parse(native.readText(path))
            } catch (e) {
            }
        }
        return null
    }

    /* the drawn remote control; whether the box is there, and which API it speaks, is asked of it */
    function showDrawn() {
        var layout = loadLayout()
        if (!layout) {
            showStatus("remote-layout.json not found", true)
            return
        }
        areas = layout.keys
        canvasW = layout.width
        canvasH = layout.height
        aspect = canvasW / canvasH
        fitToScreen()
        remoteArea.forceActiveFocus()
        var answered = function(old) {
            legacy = old
            connected = true
            showStatus("Connected to " + host + (old ? " (control API)" : ""))
            if (sideBar.visible)
                loadBouquets()
        }
        get("api/v1/system/info", function(text) {
            if (text !== null)
                answered(false)
            else
                get("control/info", function(info) {
                    if (info !== null)
                        answered(true)
                })
        }, true)
    }

    function sendKey(key) {
        for (var i = 0; i < areas.length; i++) {
            if (areas[i].key === key) {
                flash = areas[i]
                flashTimer.restart()
                break
            }
        }
        if (key === "KEY_POWER") {
            get(standbyPath(), function(state) {
                if (state === null) {
                    startLocal()
                    return
                }
                var on
                try {
                    on = legacy ? state.trim() === "on" : JSON.parse(state).on
                } catch (e) {
                    showStatus("Standby state not readable", true)
                    return
                }
                if (on)
                    sendRaw("KEY_POWER")
                else
                    standbyDialog.open()
            })
            return
        }
        sendRaw(key)
    }

    function standbyPath() {
        return legacy ? "control/standby" : "api/v1/system/standby"
    }

    function isLocal(h) {
        return /^(localhost|127(\.\d+){3}|\[::1\])$/i.test(h.trim().replace(/\/+$/, ""))
    }

    function localStartCommand() {
        if (!native.available("neutrino-desktop"))
            return null
        if (native.available("systemd-run"))
            return ["systemd-run", "--user", "--quiet", "--collect", "neutrino-desktop"]
        if (native.available("setsid"))
            return ["setsid", "-f", "neutrino-desktop"]
        return ["neutrino-desktop"]
    }

    function startLocal() {
        var command = isLocal(host) ? localStartCommand() : null
        if (!command)
            return
        if (!native.start(command[0], command.slice(1))) {
            showStatus("neutrino-desktop could not be started", true)
            return
        }
        showStatus("Starting Neutrino ...")
        retries = 15
        retryTimer.start()
    }

    property int retries: 0

    Timer {
        id: retryTimer
        interval: 2000
        onTriggered: {
            root.retries -= 1
            root.get(root.standbyPath(), function(state) {
                if (state !== null)
                    root.connectTo(root.host)
                else if (root.retries > 0)
                    retryTimer.start()
                else
                    root.showStatus("Neutrino did not come up", true)
            }, true)
        }
    }

    function sendRaw(key) {
        var sent = function(r) {
            if (r !== null) {
                showStatus(key.substring(4) + " sent")
                followOsd()
            }
        }
        if (legacy)
            get("control/rcem?" + key, sent)
        else
            post("api/v1/osd/remote/key", { name: key }, sent)
    }

    /* the screen follows the last key of a row: a shot when the keys have stopped
     * for a moment, and one more for a channel change */
    function followOsd() {
        lastKey = Date.now()
        osdSoon.restart()
        osdLate.restart()
    }

    function grabOsd() {
        if (!sideBar.visible)
            return
        if (osdBusy) {
            osdAgain = true
            return
        }
        osdBusy = true
        var back = osdShown === 0 ? osdB : osdA
        if (!legacy) {
            back.source = base + osdShot + "&at=" + (Date.now() % 4294967296)
            return
        }
        get(legacyShot, function(r) {
            if (r === null) {
                osdDone()
                return
            }
            back.source = base + legacyImage + "?" + Date.now()
        }, true)
    }

    function osdDone() {
        osdBusy = false
        if (osdAgain) {
            osdAgain = false
            grabOsd()
        }
    }

    function osdLoaded(index, image) {
        if (image.status === Image.Ready) {
            osdShown = index
            osdDone()
        } else if (image.status === Image.Error) {
            osdDone()
        }
    }

    Timer { id: osdSoon; interval: 250; onTriggered: root.grabOsd() }
    Timer { id: osdLate; interval: 2000; onTriggered: root.grabOsd() }
    Timer {
        interval: 5000
        repeat: true
        running: sideBar.visible
        onTriggered: {
            if (Date.now() - root.lastKey > 2000)
                root.grabOsd()
        }
    }

    /* a box first met on the control API is asked again for the REST API, which it may
       only have lacked while Neutrino was starting; then(true) once it answers */
    function retryApi(then) {
        if (!legacy) {
            then(false)
            return
        }
        get("api/v1/system/info", function(text) {
            if (text === null) {
                then(false)
                return
            }
            legacy = false
            showStatus("Connected to " + host)
            then(true)
        }, true)
    }

    function loadBouquets() {
        retryApi(function() { fetchBouquets() })
    }

    function fetchBouquets() {
        get(legacy ? "control/getbouquets?format=json" : "api/v1/bouquets", function(text) {
            if (text === null)
                return
            var list
            try {
                if (legacy)
                    list = (JSON.parse(text).data.bouquets || []).map(function(b) { return { id: b.number, name: b.name } })
                else
                    list = (JSON.parse(text).items || []).filter(function(b) { return !b.hidden && b.tv_count > 0 })
            } catch (e) {
                showStatus("Bouquet list not readable", true)
                return
            }
            bouquetNumbers = list.map(function(b) { return b.id })
            bouquetBox.model = list.map(function(b) { return b.name })
            if (list.length > 0) {
                bouquetBox.currentIndex = 0
                loadChannels(0)
            }
        })
    }

    function loadChannels(index) {
        if (index < 0 || index >= bouquetNumbers.length)
            return
        var number = bouquetNumbers[index]
        if (legacy) {
            loadLegacyChannels(number)
            return
        }
        getAll(function(cursor) {
            return "api/v1/channels?bouquet=" + number + "&limit=500" + (cursor ? "&cursor=" + cursor : "")
        }, function(list) {
            if (list === null)
                return
            var now = Math.floor(Date.now() / 1000)
            getAll(function(cursor) {
                return "api/v1/epg/grid?bouquet=" + number + "&from=" + now + "&to=" + (now + epgWindow)
                    + "&limit=100" + (cursor ? "&cursor=" + cursor : "")
            }, function(grid) {
                var events = {}
                ;(grid || []).forEach(function(row) { events[row.channel_id] = row.events || [] })
                get("api/v1/channels/current", function(current) {
                    try {
                        currentChannel = current ? JSON.parse(current).id || "" : ""
                    } catch (e) {
                        currentChannel = ""
                    }
                    fillChannels(list.map(function(c) { return channelItem(c, events[c.id] || []) }))
                }, true)
            }, true)
        })
    }

    function loadLegacyChannels(number) {
        get("control/getbouquet?bouquet=" + number + "&format=json&epg=true&epginfo=false", function(text) {
            if (text === null)
                return
            var list
            try {
                list = JSON.parse(text).data.channels || []
            } catch (e) {
                showStatus("Channel list not readable", true)
                return
            }
            get("control/zapto", function(current) {
                currentChannel = (current || "").trim()
                fillChannels(list.map(legacyItem))
            }, true)
        })
    }

    function fillChannels(items) {
        var same = channelModel.count === items.length
        for (var j = 0; same && j < items.length; j++)
            same = channelModel.get(j).cid === items[j].cid
        if (!same)
            channelModel.clear()
        for (var i = 0; i < items.length; i++) {
            if (same)
                channelModel.set(i, items[i])
            else
                channelModel.append(items[i])
        }
    }

    /* a row of the channel list from getbouquet of the control API */
    function legacyItem(c) {
        var now = c.firstEPG, next = c.secondEPG
        var tip = []
        if (now && now.description)
            tip.push("Now: " + now.startTime + "  " + now.description)
        if (next && next.description)
            tip.push("Next: " + next.startTime + "  " + next.description)
        var percent = now ? parseInt(now.percentage) : -1
        var left = now ? parseInt(now.timeTotal) - parseInt(now.timeElapsed) : NaN
        return {
            number: String(c.number), cid: c.id, name: c.name,
            epg: now && now.description ? now.startTime + "  " + now.description : "",
            title: now && now.description ? now.description : "",
            end: now && now.description && !isNaN(left) ? Math.floor(Date.now() / 1000) + left * 60 : 0,
            epgId: "",
            begin: 0,
            percent: isNaN(percent) ? -1 : Math.max(0, Math.min(100, percent)),
            tip: tip.join("\n")
        }
    }

    function clock(t) {
        var d = new Date(t * 1000)
        return ("0" + d.getHours()).slice(-2) + ":" + ("0" + d.getMinutes()).slice(-2)
    }

    /* a row of the channel list with the programme that is on and the next one */
    function channelItem(c, events) {
        var t = Math.floor(Date.now() / 1000)
        var evs = events.filter(function(e) { return e.start + e.duration > t })
                        .sort(function(a, b) { return a.start - b.start })
        var now = evs.filter(function(e) { return e.start <= t })[0]
        var next = evs.filter(function(e) { return e.start > t })[0]
        var tip = []
        if (now)
            tip.push("Now: " + clock(now.start) + "  " + now.title)
        if (next)
            tip.push("Next: " + clock(next.start) + "  " + next.title)
        var percent = now && now.duration > 0 ? Math.floor((t - now.start) * 100 / now.duration) : -1
        return {
            number: String(c.number), cid: c.id, name: c.name,
            epg: now ? clock(now.start) + "  " + now.title : "",
            title: now ? now.title : "",
            end: now ? now.start + now.duration : 0,
            epgId: now ? now.id : "",
            begin: now ? now.start : 0,
            percent: percent < 0 ? -1 : Math.max(0, Math.min(100, percent)),
            tip: tip.join("\n")
        }
    }

    /* a record timer for the programme that is on, from now to its end; the box adds
     * its own lead and follow-up time */
    function record(cid, end, title, epgId, begin) {
        var now = Math.floor(Date.now() / 1000)
        if (end <= now)
            return
        var done = function(r) {
            if (r !== null)
                showStatus("Recording: " + title)
        }
        if (legacy) {
            get("control/timer?action=new&type=5&channel_id=" + cid + "&alarm=" + now + "&stop=" + end + "&rs=1", done)
            return
        }
        var body = { kind: "record", channel_id: cid, start: now, stop: end, title: title, recording_safety: true }
        if (epgId) {
            body.epg_id = epgId
            body.epg_start = begin
        }
        post("api/v1/timers", body, done)
    }

    function stream(cid, name) {
        get((legacy ? "control/streamurl?id=" : "api/v1/stream/") + cid, function(text) {
            var url = ""
            try {
                url = !text ? "" : legacy ? text.trim() : (JSON.parse(text).url || "").trim()
            } catch (e) {
            }
            if (!url) {
                showStatus(name + ": no stream address", true)
                return
            }
            if (url.charAt(0) === "/")
                url = base + url.substring(1)
            var players = ["mpv", "celluloid", "vlc"]
            for (var i = 0; i < players.length; i++) {
                if (native.available(players[i])) {
                    if (native.start(players[i], [url]))
                        showStatus("Streaming " + name)
                    else
                        showStatus(players[i] + " could not be started", true)
                    return
                }
            }
            if (Qt.openUrlExternally(url))
                showStatus("Streaming " + name)
            else
                showStatus("No player for " + name, true)
        })
    }

    function zapTo(cid) {
        var done = function(r) {
            if (r === null)
                return
            currentChannel = cid
            showStatus("Switched channel")
            followOsd()
        }
        if (legacy)
            get("control/zapto?" + cid, done)
        else
            post("api/v1/zap", { channel_id: cid }, done)
    }

    readonly property var keyboard: ({
        [Qt.Key_Up]: "KEY_UP", [Qt.Key_Down]: "KEY_DOWN", [Qt.Key_Left]: "KEY_LEFT",
        [Qt.Key_Right]: "KEY_RIGHT", [Qt.Key_Return]: "KEY_OK", [Qt.Key_Enter]: "KEY_OK",
        [Qt.Key_Space]: "KEY_OK", [Qt.Key_Escape]: "KEY_HOME", [Qt.Key_Backspace]: "KEY_HOME",
        [Qt.Key_M]: "KEY_SETUP", [Qt.Key_I]: "KEY_INFO", [Qt.Key_E]: "KEY_EPG",
        [Qt.Key_F]: "KEY_FAVORITES", [Qt.Key_Plus]: "KEY_VOLUMEUP", [Qt.Key_Minus]: "KEY_VOLUMEDOWN",
        [Qt.Key_PageUp]: "KEY_PAGEUP", [Qt.Key_PageDown]: "KEY_PAGEDOWN",
        [Qt.Key_F1]: "KEY_RED", [Qt.Key_F2]: "KEY_GREEN", [Qt.Key_F3]: "KEY_YELLOW",
        [Qt.Key_F4]: "KEY_BLUE", [Qt.Key_T]: "KEY_TEXT", [Qt.Key_A]: "KEY_AUDIO",
        [Qt.Key_H]: "KEY_HELP", [Qt.Key_R]: "KEY_RADIO", [Qt.Key_V]: "KEY_TV",
        [Qt.Key_0]: "KEY_0", [Qt.Key_1]: "KEY_1", [Qt.Key_2]: "KEY_2", [Qt.Key_3]: "KEY_3",
        [Qt.Key_4]: "KEY_4", [Qt.Key_5]: "KEY_5", [Qt.Key_6]: "KEY_6", [Qt.Key_7]: "KEY_7",
        [Qt.Key_8]: "KEY_8", [Qt.Key_9]: "KEY_9"
    })

    Timer {
        id: flashTimer
        interval: 150
        onTriggered: root.flash = null
    }

    header: ToolBar {
        implicitHeight: toolRow.implicitHeight + 12
        background: Rectangle { color: root.panel; Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: root.line } }
        RowLayout {
            id: toolRow
            anchors.fill: parent
            anchors.margins: 6
            spacing: 6
            TextField {
                id: hostField
                Layout.fillWidth: true
                Layout.minimumWidth: ipWidth.advanceWidth + leftPadding + rightPadding + 8
                text: root.host
                placeholderText: "Box address"
                TextMetrics { id: ipWidth; font: hostField.font; text: "192.168.178.111" }
                color: root.fg
                placeholderTextColor: root.dim
                background: Rectangle { color: root.raised; border.color: hostField.activeFocus ? root.accent : root.line; radius: 4 }
                ToolTip.visible: hovered
                ToolTip.text: "IP address or host name of the Neutrino box"
                onAccepted: {
                    root.connectTo(text)
                    remoteArea.forceActiveFocus()
                }
            }
            ToolButton {
                id: listButton
                checkable: true
                text: "\u2630"
                ToolTip.visible: hovered
                ToolTip.text: "Channel list"
                contentItem: Text { text: listButton.text; color: listButton.checked ? root.accent : root.fg; font.pixelSize: 18; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
                background: Rectangle { color: listButton.hovered ? root.raised : "transparent"; radius: 4 }
                onToggled: {
                    sideBar.visible = checked
                    root.fitToScreen()
                    if (checked) {
                        root.loadBouquets()
                        root.grabOsd()
                    }
                }
            }
            ToolButton {
                id: trayButton
                visible: native.trayAvailable()
                ToolTip.visible: hovered
                ToolTip.text: "Minimize to the tray"
                contentItem: IconImage { name: "go-down-symbolic"; color: root.fg; sourceSize: Qt.size(16, 16); fillMode: Image.Pad }
                background: Rectangle { color: trayButton.hovered ? root.raised : "transparent"; radius: 4 }
                onClicked: native.toTray(root)
            }
            ToolButton {
                id: closeButton
                ToolTip.visible: hovered
                ToolTip.text: "Quit"
                contentItem: IconImage { name: "window-close-symbolic"; color: root.fg; sourceSize: Qt.size(16, 16); fillMode: Image.Pad }
                background: Rectangle { color: closeButton.hovered ? root.raised : "transparent"; radius: 4 }
                onClicked: Qt.quit()
            }
        }
    }

    RowLayout {
        anchors.fill: parent
        spacing: 6
        layoutDirection: root.listSide === "right" ? Qt.RightToLeft : Qt.LeftToRight

        ColumnLayout {
            id: sideBar
            visible: false
            Layout.fillHeight: true
            Layout.preferredWidth: Math.max(320, Math.round(Screen.width * 0.25)) - 6
            Layout.minimumWidth: Layout.preferredWidth
            Layout.maximumWidth: Layout.preferredWidth
            spacing: 4

            ComboBox {
                id: bouquetBox
                Layout.fillWidth: true
                model: []
                onActivated: function(index) { root.loadChannels(index) }
            }

            Timer {
                interval: 60000
                repeat: true
                running: sideBar.visible
                onTriggered: root.retryApi(function(switched) {
                    if (switched)
                        root.loadBouquets()
                    else
                        root.loadChannels(bouquetBox.currentIndex)
                })
            }

            SplitView {
                id: split
                Layout.fillWidth: true
                Layout.fillHeight: true
                orientation: Qt.Vertical
                handle: Rectangle {
                    implicitHeight: 6
                    color: SplitHandle.hovered || SplitHandle.pressed ? root.line : "transparent"
                }

                ListView {
                    id: channelList
                    SplitView.fillHeight: true
                    SplitView.minimumHeight: 80
                    clip: true
                    model: ListModel { id: channelModel }
                    ScrollBar.vertical: ScrollBar {}
                    delegate: ItemDelegate {
                        width: channelList.width
                        onClicked: root.zapTo(model.cid)
                        background: Rectangle { color: parent.hovered ? root.raised : "transparent" }
                        ToolTip.visible: hovered && model.tip !== ""
                        ToolTip.text: model.tip
                        ToolTip.delay: 500
                        contentItem: RowLayout {
                            spacing: 8
                            Text { text: model.number; color: root.dim; font.family: "monospace"; Layout.preferredWidth: 36; Layout.alignment: Qt.AlignTop; horizontalAlignment: Text.AlignRight }
                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 1
                                Text {
                                    text: model.name
                                    Layout.fillWidth: true
                                    elide: Text.ElideRight
                                    color: model.cid === root.currentChannel ? root.accent : root.fg
                                    font.bold: model.cid === root.currentChannel
                                }
                                RowLayout {
                                    visible: model.epg !== ""
                                    Layout.fillWidth: true
                                    spacing: 8
                                    Text { text: model.epg; Layout.fillWidth: true; elide: Text.ElideRight; color: root.dim; font.pointSize: Qt.application.font.pointSize * 0.85 }
                                    Rectangle {
                                        visible: model.percent >= 0
                                        Layout.preferredWidth: 48
                                        Layout.preferredHeight: 3
                                        color: root.line
                                        Rectangle { width: parent.width * model.percent / 100; height: parent.height; color: root.accent }
                                    }
                                }
                            }
                            ToolButton {
                                id: recordButton
                                visible: model.end > 0
                                Layout.alignment: Qt.AlignVCenter
                                ToolTip.visible: hovered
                                ToolTip.text: "Record the programme that is on"
                                contentItem: IconImage { name: "media-record-symbolic"; color: root.fg; sourceSize: Qt.size(16, 16); fillMode: Image.Pad }
                                background: Rectangle { color: recordButton.hovered ? root.line : "transparent"; radius: 4 }
                                onClicked: root.record(model.cid, model.end, model.title, model.epgId, model.begin)
                            }
                            ToolButton {
                                id: streamButton
                                visible: !root.isLocal(root.host)
                                Layout.alignment: Qt.AlignVCenter
                                ToolTip.visible: hovered
                                ToolTip.text: "Watch on this computer"
                                contentItem: IconImage { name: "media-playback-start-symbolic"; color: root.fg; sourceSize: Qt.size(16, 16); fillMode: Image.Pad }
                                background: Rectangle { color: streamButton.hovered ? root.line : "transparent"; radius: 4 }
                                onClicked: root.stream(model.cid, model.name)
                            }
                        }
                    }
                }

                Item {
                    SplitView.preferredHeight: Math.min(split.width * 9 / 16, split.height * 0.7)
                    ToolTip.visible: osdHover.hovered
                    ToolTip.text: "Screen of the box"
                    HoverHandler { id: osdHover }

                    Image {
                        id: osdA
                        anchors.fill: parent
                        fillMode: Image.PreserveAspectFit
                        smooth: true
                        mipmap: true
                        cache: false
                        visible: root.osdShown === 0
                        onStatusChanged: root.osdLoaded(0, osdA)
                    }
                    Image {
                        id: osdB
                        anchors.fill: parent
                        fillMode: Image.PreserveAspectFit
                        smooth: true
                        mipmap: true
                        cache: false
                        visible: root.osdShown === 1
                        onStatusChanged: root.osdLoaded(1, osdB)
                    }
                }
            }
        }

        ColumnLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 0

            Item {
                id: remoteArea
                Layout.fillWidth: true
                Layout.fillHeight: true
                focus: true

                Keys.onPressed: function(event) {
                    if (event.modifiers & (Qt.ControlModifier | Qt.AltModifier))
                        return
                    var key = root.keyboard[event.key]
                    if (key) {
                        root.sendKey(key)
                        event.accepted = true
                    }
                }

                Item {
                    id: keysView
                    anchors.fill: parent
                    anchors.margins: 6
                    readonly property real s: root.canvasW > 0 ? Math.min(width / root.canvasW, height / root.canvasH) : 0
                    readonly property real ox: (width - root.canvasW * s) / 2
                    readonly property real oy: (height - root.canvasH * s) / 2

                    Rectangle {
                        visible: keysView.s > 0
                        x: keysView.ox
                        y: keysView.oy
                        width: root.canvasW * keysView.s
                        height: root.canvasH * keysView.s
                        radius: 24 * keysView.s
                        color: root.raised

                        Repeater {
                            model: root.areas
                            Rectangle {
                                readonly property var b: root.bounds(modelData)
                                x: b.x * keysView.s
                                y: b.y * keysView.s
                                width: b.w * keysView.s
                                height: b.h * keysView.s
                                radius: modelData.shape === "circle" ? width / 2 : 5 * keysView.s
                                color: modelData.color || "#3a4150"

                                IconImage {
                                    visible: !!modelData.icon
                                    anchors.centerIn: parent
                                    name: modelData.icon || ""
                                    color: root.fg
                                    sourceSize: Qt.size(Math.max(8, Math.min(parent.width, parent.height) * 0.55),
                                                        Math.max(8, Math.min(parent.width, parent.height) * 0.55))
                                }
                                Text {
                                    visible: !modelData.icon
                                    anchors.centerIn: parent
                                    text: modelData.label || ""
                                    color: root.fg
                                    font.pixelSize: Math.max(6, Math.min(parent.height * 0.45, 13 * keysView.s))
                                }
                            }
                        }
                    }

                    Repeater {
                        model: [root.hot, root.flash]
                        Rectangle {
                            readonly property var b: modelData ? root.bounds(modelData) : null
                            visible: b !== null && keysView.s > 0
                            x: b ? keysView.ox + b.x * keysView.s : 0
                            y: b ? keysView.oy + b.y * keysView.s : 0
                            width: b ? b.w * keysView.s : 0
                            height: b ? b.h * keysView.s : 0
                            radius: modelData && modelData.shape === "circle" ? width / 2 : 3
                            color: index === 0 ? Qt.rgba(0.4, 0.68, 0.91, 0.25) : Qt.rgba(0.4, 0.68, 0.91, 0.6)
                        }
                    }

                    MouseArea {
                        id: mouse
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: root.hot ? Qt.PointingHandCursor : Qt.ArrowCursor
                        onPositionChanged: function(m) { root.hot = root.areaAt(m.x, m.y) }
                        onExited: root.hot = null
                        onPressed: function(m) {
                            remoteArea.forceActiveFocus()
                            var a = root.areaAt(m.x, m.y)
                            if (a)
                                root.sendKey(a.key)
                        }
                        ToolTip.visible: root.hot !== null && containsMouse
                        ToolTip.text: root.hot ? root.hot.title : ""
                        ToolTip.delay: 600
                    }
                }
            }

            Label {
                Layout.fillWidth: true
                padding: 6
                text: root.statusText
                elide: Text.ElideRight
                color: root.statusError ? root.errorFg : root.dim
            }
        }

    }

    Dialog {
        id: standbyDialog
        anchors.centerIn: parent
        modal: true
        title: "Put the box into standby?"
        standardButtons: Dialog.Cancel | Dialog.Ok
        onAccepted: root.sendRaw("KEY_POWER")
    }

    Dialog {
        id: loginDialog
        anchors.centerIn: parent
        modal: true
        title: "Sign in to " + root.host
        closePolicy: Popup.CloseOnEscape
        onRejected: root.finishSignIn(false)

        ColumnLayout {
            spacing: 8
            Label {
                id: loginNote
                Layout.preferredWidth: 240
                wrapMode: Text.WordWrap
            }
            TextField {
                id: userField
                Layout.fillWidth: true
                text: "root"
                placeholderText: "Name"
            }
            TextField {
                id: passField
                Layout.fillWidth: true
                echoMode: TextInput.Password
                placeholderText: "Password"
                onAccepted: root.submitSignIn()
            }
            RowLayout {
                Layout.alignment: Qt.AlignRight
                Button { text: "Cancel"; onClicked: loginDialog.reject() }
                Button { id: signInButton; text: "Sign in"; onClicked: root.submitSignIn() }
            }
            Rectangle { Layout.fillWidth: true; height: 1; color: root.line }
            Label {
                Layout.preferredWidth: 240
                wrapMode: Text.WordWrap
                color: root.dim
                text: "Or with a token the box knows, which lasts beyond a restart of the box:"
            }
            RowLayout {
                Layout.fillWidth: true
                TextField {
                    id: tokenField
                    Layout.fillWidth: true
                    placeholderText: "Token"
                    onAccepted: if (text.trim()) root.useToken()
                }
                Button { text: "Generate"; onClicked: tokenField.text = native.randomHex(16) }
            }
            Label {
                id: tokenHint
                Layout.preferredWidth: 240
                visible: tokenField.text.trim() !== ""
                wrapMode: Text.WrapAnywhere
                font.pixelSize: 11
                color: root.dim
                text: root.tokenLines(tokenField.text.trim())
            }
            RowLayout {
                Layout.alignment: Qt.AlignRight
                Button { text: "Copy line"; enabled: tokenField.text.trim() !== ""; onClicked: native.copyText(tokenHint.text) }
                Button { id: useTokenButton; text: "Use token"; enabled: tokenField.text.trim() !== ""; onClicked: root.useToken() }
            }
        }
    }

    Component.onCompleted: {
        var args = Qt.application.arguments
        var i = args.indexOf("--")
        var rest = args.slice(i >= 0 ? i + 1 : 1)
        configFile = rest.length > 1 ? rest[1] : ""
        listSide = rest.length > 2 ? rest[2] : "left"
        fitToScreen()
        visible = true
        connectTo(rest.length > 0 ? rest[0] : "")
    }
}
