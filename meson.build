project('neutrino-remote',
  version: '0.1.0',
  license: 'GPL-2.0-or-later',
  meson_version: '>= 1.1.0',
)

app_id = 'de.flk.NeutrinoRemote'
datadir = get_option('prefix') / get_option('datadir')
pkgdatadir = datadir / meson.project_name()

install_data('src/neutrino-remote', install_dir: get_option('bindir'), install_mode: 'rwxr-xr-x')
install_data('src/remote.py', install_dir: pkgdatadir)
install_data('data' / app_id + '.desktop', install_dir: datadir / 'applications')
install_data('data' / app_id + '.svg', install_dir: datadir / 'icons/hicolor/scalable/apps')

if get_option('gtk')
  install_data('gtk/neutrino-remote-gtk.py', install_dir: pkgdatadir)
endif

if get_option('qt').allowed()
  build_qt = add_languages('cpp', native: false, required: get_option('qt'))
  if build_qt
    qt_dep = dependency('qt6', modules: ['Core', 'Gui', 'Qml', 'Quick'], required: get_option('qt'))
    if qt_dep.found()
      qml_file = pkgdatadir / 'neutrino-remote.qml'
      moc_files = import('qt6').compile_moc(headers: 'qt/native.h', dependencies: qt_dep)
      executable('neutrino-remote-qt', 'qt/main.cpp', moc_files,
        dependencies: qt_dep,
        cpp_args: ['-DAPP_ID="' + app_id + '"', '-DQML_FILE="' + qml_file + '"'],
        override_options: ['cpp_std=c++17'],
        install: true,
      )
      install_data('qt/neutrino-remote.qml', install_dir: pkgdatadir)
    endif
  endif
endif
