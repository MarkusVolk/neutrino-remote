#include <QGuiApplication>
#include <QIcon>
#include <QQmlApplicationEngine>
#include <QUrl>

int main(int argc, char *argv[])
{
	qputenv("QML_XHR_ALLOW_FILE_WRITE", "1");
	QGuiApplication app(argc, argv);
	app.setApplicationName("neutrino-remote");
	app.setApplicationDisplayName("Neutrino Remote");
	app.setDesktopFileName(APP_ID);
	app.setWindowIcon(QIcon::fromTheme(APP_ID));

	QQmlApplicationEngine engine;
	QObject::connect(&engine, &QQmlApplicationEngine::objectCreationFailed, &app,
			 [] { QCoreApplication::exit(1); }, Qt::QueuedConnection);
	QString qml = qEnvironmentVariable("NEUTRINO_REMOTE_QML", QML_FILE);
	engine.load(QUrl::fromLocalFile(qml));
	return app.exec();
}
