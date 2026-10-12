#pragma once

#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QIcon>
#include <QNetworkAccessManager>
#include <QNetworkCookie>
#include <QNetworkCookieJar>
#include <QObject>
#include <QGuiApplication>
#include <QClipboard>
#include <QQmlEngine>
#include <QRandomGenerator>
#include <QProcess>
#include <QStandardPaths>
#include <QString>
#include <QStringList>
#include <QSystemTrayIcon>
#include <QUrl>
#include <QWindow>

class Native : public QObject
{
	Q_OBJECT
public:
	using QObject::QObject;

	void setEngine(QQmlEngine *engine) { m_engine = engine; }

	Q_INVOKABLE bool available(const QString &program) const
	{
		return !QStandardPaths::findExecutable(program).isEmpty();
	}

	Q_INVOKABLE bool start(const QString &program, const QStringList &arguments) const
	{
		return QProcess::startDetached(program, arguments);
	}

	Q_INVOKABLE bool exists(const QString &path) const { return QFile::exists(path); }

	Q_INVOKABLE QString readText(const QString &path) const
	{
		QFile file(path);
		if (!file.open(QIODevice::ReadOnly))
			return QString();
		return QString::fromUtf8(file.readAll());
	}

	/* a file only its owner may read, for a session of a box */
	Q_INVOKABLE bool writePrivate(const QString &path, const QString &text) const
	{
		QDir().mkpath(QFileInfo(path).path());
		QFile file(path);
		if (!file.open(QIODevice::WriteOnly | QIODevice::Truncate))
			return false;
		file.setPermissions(QFileDevice::ReadOwner | QFileDevice::WriteOwner);
		const QByteArray bytes = text.toUtf8();
		return file.write(bytes) == bytes.size();
	}

	Q_INVOKABLE bool remove(const QString &path) const { return QFile::remove(path); }

	/* hex digits from the system's random source, for a new token */
	Q_INVOKABLE QString randomHex(int bytes) const
	{
		QString out;
		for (int i = 0; i < bytes; i++)
			out += QString::asprintf("%02x", QRandomGenerator::system()->bounded(256));
		return out;
	}

	Q_INVOKABLE void copyText(const QString &text) const { QGuiApplication::clipboard()->setText(text); }

	/* the cookies the requests of QML carry, kept by the engine's network access */
	Q_INVOKABLE void setCookie(const QString &url, const QString &name, const QString &value) const
	{
		if (m_engine)
			m_engine->networkAccessManager()->cookieJar()->setCookiesFromUrl(
				{ QNetworkCookie(name.toUtf8(), value.toUtf8()) }, QUrl(url));
	}

	Q_INVOKABLE QString cookie(const QString &url, const QString &name) const
	{
		if (!m_engine)
			return QString();
		const auto cookies = m_engine->networkAccessManager()->cookieJar()->cookiesForUrl(QUrl(url));
		for (const QNetworkCookie &c : cookies)
			if (c.name() == name.toUtf8())
				return QString::fromUtf8(c.value());
		return QString();
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

	QQmlEngine *m_engine = nullptr;
	QSystemTrayIcon *m_tray = nullptr;
	QWindow *m_window = nullptr;
};
