#pragma once

#include <QByteArray>
#include <QDir>
#include <QFile>
#include <QObject>
#include <QProcess>
#include <QRegularExpression>
#include <QStandardPaths>
#include <QString>
#include <QStringList>
#include <QVariant>

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
};
