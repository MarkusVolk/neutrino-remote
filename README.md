# neutrino-remote

A desktop remote control for receivers running [Neutrino](https://github.com/tuxbox-neutrino)
or [ni-neutrino](https://github.com/neutrino-images/ni-neutrino). The window shows a drawn remote
control; a click on a key, or the matching key on the keyboard, sends it to the box. A side panel
lists the bouquets with the programme that is on, switches channels, records or streams a channel,
and shows the screen of the box.

The remote talks to the REST API under `/api/v1` that ni-neutrino and Neutrino with libmicrohttpd
offer. A box that only has the old control API of nhttpd is driven through `/control`. The
address of the box is set in the header bar and kept in `~/.config/neutrino-remote/host`.

    neutrino-remote [--gtk | --qt] [--list-left | --list-right] [HOST]

The channel list opens to the left of the remote, so a window anchored at the right edge of
the screen grows to the left and the remote stays where it is. `--list-right` puts it on the
other side for a window anchored at the left edge; the choice is kept in
`~/.config/neutrino-remote/list`.

There are two frontends: GTK 4 (Python) and Qt 6 (QML). The launcher picks the Qt one under
KDE and the GTK one elsewhere, or the one that is installed.

A box that refuses a request asks for a sign-in. Name and password open a session that lasts until
the box ends it or restarts. A token lasts beyond that: the dialog generates one and shows the line
the box needs for it, `api_tokens=write:<token>` in `/var/tuxbox/config/ni-web.conf` on ni-neutrino
or `api.tokens=write:<token>` in `nhttpd.conf` on Neutrino. Sessions and tokens are kept per box in
`~/.config/neutrino-remote/`, readable only by the user; a file `token` there applies to every box.

The power key puts the box into standby or wakes it. When the address is localhost and no
Neutrino answers there, the key starts `neutrino-desktop` instead and connects once it is up.

Keyboard: arrows, Enter (OK), Esc/Backspace (Exit), digits, `m` menu, `i` info, `e` EPG,
`+`/`-` volume, Page Up/Down, F1-F4 colour keys, `t` text, `a` audio, `h` help, `r` radio, `v` TV.

## Build

    meson setup build -Dqt=enabled
    meson install -C build

## License

GPL-2.0-or-later
