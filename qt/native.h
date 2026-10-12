#pragma once

#include <QByteArray>
#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QIcon>
#include <QObject>
#include <QProcess>
#include <QRegularExpression>
#include <QStandardPaths>
#include <QString>
#include <QStringList>
#include <QSystemTrayIcon>
#include <QVariant>
#include <QWindow>

class Native : public QObject
{
	Q_OBJECT
public:
	using QObject::QObject;

	Q_INVOKABLE bool available(const QString &program) const
	{
		return !QStandardPaths::findExecutable(program).isEmpty();
	}

	Q_INVOKABLE bool start(const QString &program, const QStringList &arguments) const
	{
		return QProcess::startDetached(program, arguments);
	}

	Q_INVOKABLE QString cacheDir(const QString &host) const
	{
		QString name = host.trimmed();
		name.remove(QRegularExpression("/+$"));
		name.replace(QRegularExpression("[^\\w.-]"), "_");
		QDir dir(QStandardPaths::writableLocation(QStandardPaths::GenericCacheLocation)
			 + "/neutrino-remote/" + name);
		dir.mkpath(".");
		return dir.path();
	}

	Q_INVOKABLE bool exists(const QString &path) const { return QFile::exists(path); }

	Q_INVOKABLE QString readText(const QString &path) const
	{
		QFile file(path);
		if (!file.open(QIODevice::ReadOnly))
			return QString();
		return QString::fromUtf8(file.readAll());
	}

	Q_INVOKABLE bool write(const QString &path, const QVariant &data) const
	{
		QFile file(path);
		if (!file.open(QIODevice::WriteOnly))
			return false;
		const QByteArray bytes = data.typeId() == QMetaType::QByteArray ? data.toByteArray()
									      : data.toString().toUtf8();
		return file.write(bytes) == bytes.size();
	}

	Q_INVOKABLE bool trayAvailable() const { return QSystemTrayIcon::isSystemTrayAvailable(); }

	/* hides the window behind an icon in the panel's tray, a click on it brings it back */
	Q_INVOKABLE void toTray(QWindow *window)
	{
		if (!window)
			return;
		if (!m_tray) {
			m_tray = new QSystemTrayIcon(trayIcon(), this);
			m_tray->setToolTip("Neutrino Remote");
			connect(m_tray, &QSystemTrayIcon::activated, this, [this] {
				m_tray->hide();
				if (m_window) {
					m_window->show();
					m_window->raise();
					m_window->requestActivate();
				}
			});
		}
		m_window = window;
		m_tray->show();
		window->hide();
	}

private:
	/* the symbolic icon of the theme, or the one next to the QML file when run from the source tree */
	static QIcon trayIcon()
	{
		const QString name = QStringLiteral(APP_ID "-symbolic");
		if (QIcon::hasThemeIcon(name))
			return QIcon::fromTheme(name);
		const QString qml = qEnvironmentVariable("NEUTRINO_REMOTE_QML", QML_FILE);
		const QString file = QFileInfo(qml).dir().filePath("../data/" + name + ".svg");
		return QFile::exists(file) ? QIcon(file) : QIcon::fromTheme(APP_ID);
	}

	QSystemTrayIcon *m_tray = nullptr;
	QWindow *m_window = nullptr;
};
