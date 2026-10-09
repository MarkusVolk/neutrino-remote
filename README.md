# neutrino-remote

A desktop remote control for receivers running [Neutrino](https://github.com/tuxbox-neutrino).
The window shows the remote control of the box's web interface; a click on a key, or the
matching key on the keyboard, sends it through the web interface (`/control/rcem`). A side panel
lists the bouquets and switches channels through zapit (`/control/zapto`).

The picture and the key areas are taken from the box itself (`Y_Tools_Rcsim.yhtm`), so the
remote matches the box model. The address of the box is set in the header bar and kept in
`~/.config/neutrino-remote/host`.

    neutrino-remote [--gtk | --qt] [HOST]

There are two frontends: GTK 4 (Python) and Qt 6 (QML). The launcher picks the Qt one under
KDE and the GTK one elsewhere, or the one that is installed.

Keyboard: arrows, Enter (OK), Esc/Backspace (Exit), digits, `m` menu, `i` info, `e` EPG,
`+`/`-` volume, Page Up/Down, F1-F4 colour keys, `t` text, `a` audio, `h` help, `r` radio, `v` TV.

## Build

    meson setup build -Dqt=enabled
    meson install -C build

## License

GPL-2.0-or-later
