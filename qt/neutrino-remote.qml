import QtQuick
import QtQuick.Controls.Basic
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

    title: "Neutrino Remote"
    color: bg
    visible: false

    function fitToScreen() {
        var header = 48
        var viewH = Math.round(Screen.height * 0.6) - header
        var w = Math.max(260, Math.round(viewH * aspect) + 24)
        if (sideBar.visible)
            w += Math.max(280, Math.round(Screen.width * 0.15))
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
        var xhr = new XMLHttpRequest()
        var url = /^https?:\/\//.test(path) ? path : base + path
        xhr.onreadystatechange = function() {
            if (xhr.readyState !== XMLHttpRequest.DONE)
                return
            if (xhr.status !== 200) {
                if (!quiet)
                    showStatus(host + ": " + (xhr.status ? "HTTP " + xhr.status : "not reachable"), true)
                callback(null)
                return
            }
            callback(xhr.responseText)
        }
        xhr.timeout = 5000
        xhr.open("GET", url)
        xhr.send()
    }

    function saveHost(h) {
        if (!configFile)
            return
        var xhr = new XMLHttpRequest()
        xhr.open("PUT", "file://" + configFile)
        xhr.send(h + "\n")
    }

    function attrs(text) {
        var re = /(\w+)\s*=\s*("([^"]*)"|'([^']*)')/g
        var out = {}
        var m
        while ((m = re.exec(text)) !== null)
            out[m[1].toLowerCase()] = m[3] !== undefined ? m[3] : m[4]
        return out
    }

    function parseRemote(html) {
        var img = /<img\b[^>]*\bsrc\s*=\s*["']([^"']+)["'][^>]*\busemap\b/i.exec(html)
        if (!img)
            return null
        var list = []
        var re = /<area\b([^>]*)>/gi
        var m
        while ((m = re.exec(html)) !== null) {
            var a = attrs(m[1])
            var key = /rcsim\(\s*['"](KEY_\w+)['"]\s*\)/.exec(a.href || "")
            var coords = (a.coords || "").split(",").filter(function(c) { return c.trim() !== "" })
                                             .map(function(c) { return Math.round(parseFloat(c)) })
            var shape = (a.shape || "rect").toLowerCase()
            if (!key || coords.some(isNaN))
                continue
            if ((shape === "circle" && coords.length !== 3) || (shape !== "circle" && coords.length < 4))
                continue
            var name = key[1].substring(4).replace(/_/g, " ").toLowerCase()
            list.push({ key: key[1], shape: shape, coords: coords,
                        title: a.title || a.alt || name.charAt(0).toUpperCase() + name.slice(1) })
        }
        var src = img[1]
        if (!/^https?:\/\//.test(src))
            src = base + src.replace(/^\/+/, "")
        return { image: src, areas: list }
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
        if (picture.status !== Image.Ready)
            return null
        var s = picture.paintedWidth / picture.sourceSize.width
        var px = (x - (picture.width - picture.paintedWidth) / 2) / s
        var py = (y - (picture.height - picture.paintedHeight) / 2) / s
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
        showStatus("Connecting to " + h + " ...")
        get("Y_Tools_Rcsim.yhtm", function(html) {
            if (html === null) {
                showCached()
                return
            }
            var parsed = parseRemote(html)
            if (!parsed) {
                showStatus(host + ": no remote control in the web interface", true)
                return
            }
            fetchPicture(parsed)
        })
    }

    function fetchPicture(parsed) {
        var xhr = new XMLHttpRequest()
        xhr.responseType = "arraybuffer"
        xhr.onreadystatechange = function() {
            if (xhr.readyState !== XMLHttpRequest.DONE)
                return
            if (xhr.status !== 200) {
                showStatus(host + ": " + (xhr.status ? "HTTP " + xhr.status : "not reachable"), true)
                showCached()
                return
            }
            var dir = native.cacheDir(host)
            native.write(dir + "/remote.img", xhr.response)
            native.write(dir + "/remote.json", JSON.stringify(parsed.areas))
            areas = parsed.areas
            connected = true
            picture.source = ""
            picture.source = "file://" + dir + "/remote.img"
            if (sideBar.visible)
                loadBouquets()
        }
        xhr.timeout = 5000
        xhr.open("GET", parsed.image)
        xhr.send()
    }

    function showCached() {
        var dir = native.cacheDir(host)
        if (!native.exists(dir + "/remote.img") || !native.exists(dir + "/remote.json"))
            return
        try {
            areas = JSON.parse(native.readText(dir + "/remote.json"))
        } catch (e) {
            return
        }
        connected = false
        picture.source = ""
        picture.source = "file://" + dir + "/remote.img"
    }

    property bool connected: false

    function sendKey(key) {
        for (var i = 0; i < areas.length; i++) {
            if (areas[i].key === key) {
                flash = areas[i]
                flashTimer.restart()
                break
            }
        }
        if (key === "KEY_POWER") {
            get("control/standby", function(state) {
                if (state === null) {
                    startLocal()
                    return
                }
                if (state.trim() === "off")
                    standbyDialog.open()
                else
                    sendRaw("KEY_POWER")
            })
            return
        }
        sendRaw(key)
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
            root.get("control/standby", function(state) {
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
        get("control/rcem?" + key, function(r) {
            if (r !== null)
                showStatus(key.substring(4) + " sent")
        })
    }

    function loadBouquets() {
        get("control/getbouquets?format=json", function(text) {
            if (text === null)
                return
            var list
            try {
                list = JSON.parse(text).data.bouquets || []
            } catch (e) {
                showStatus("Bouquet list not readable", true)
                return
            }
            bouquetNumbers = list.map(function(b) { return b.number })
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
        get("control/getbouquet?bouquet=" + bouquetNumbers[index] + "&format=json", function(text) {
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
                channelModel.clear()
                for (var i = 0; i < list.length; i++)
                    channelModel.append({ number: list[i].number, cid: list[i].id, name: list[i].name })
            })
        })
    }

    function zapTo(cid) {
        get("control/zapto?" + cid, function(r) {
            if (r === null)
                return
            currentChannel = cid
            showStatus("Switched channel")
        })
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
        background: Rectangle { color: root.panel; Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: root.line } }
        RowLayout {
            anchors.fill: parent
            anchors.margins: 6
            spacing: 6
            TextField {
                id: hostField
                Layout.fillWidth: true
                text: root.host
                placeholderText: "Box address"
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
                    if (checked)
                        root.loadBouquets()
                }
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
            Layout.preferredWidth: Math.max(280, Math.round(Screen.width * 0.15)) - 6
            spacing: 4

            ComboBox {
                id: bouquetBox
                Layout.fillWidth: true
                model: []
                onActivated: function(index) { root.loadChannels(index) }
            }

            ListView {
                id: channelList
                Layout.fillWidth: true
                Layout.fillHeight: true
                clip: true
                model: ListModel { id: channelModel }
                ScrollBar.vertical: ScrollBar {}
                delegate: ItemDelegate {
                    width: channelList.width
                    onClicked: root.zapTo(model.cid)
                    background: Rectangle { color: parent.hovered ? root.raised : "transparent" }
                    contentItem: RowLayout {
                        spacing: 8
                        Text { text: model.number; color: root.dim; font.family: "monospace"; Layout.preferredWidth: 36; horizontalAlignment: Text.AlignRight }
                        Text {
                            text: model.name
                            Layout.fillWidth: true
                            elide: Text.ElideRight
                            color: model.cid === root.currentChannel ? root.accent : root.fg
                            font.bold: model.cid === root.currentChannel
                        }
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

                Image {
                    id: picture
                    anchors.fill: parent
                    anchors.margins: 6
                    fillMode: Image.PreserveAspectFit
                    smooth: true
                    mipmap: true
                    cache: false
                    onStatusChanged: {
                        if (status === Image.Ready) {
                            root.aspect = sourceSize.width / sourceSize.height
                            root.fitToScreen()
                            if (root.connected)
                                root.showStatus("Connected to " + root.host)
                            else
                                root.showStatus(root.host + ": not reachable, last remote shown", true)
                        } else if (status === Image.Error) {
                            root.showStatus("Remote control picture not loaded", true)
                        }
                    }

                    Repeater {
                        model: [root.hot, root.flash]
                        Rectangle {
                            readonly property var b: modelData ? root.bounds(modelData) : null
                            readonly property real s: picture.sourceSize.width > 0 ? picture.paintedWidth / picture.sourceSize.width : 0
                            visible: b !== null && picture.status === Image.Ready
                            x: b ? (picture.width - picture.paintedWidth) / 2 + b.x * s : 0
                            y: b ? (picture.height - picture.paintedHeight) / 2 + b.y * s : 0
                            width: b ? b.w * s : 0
                            height: b ? b.h * s : 0
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
