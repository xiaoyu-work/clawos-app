#include "launch/main.hpp"
#include <array>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>

int main(int argc, char** argv) {
	const auto* gui = std::getenv("COS_APP_GUI");
	if (!gui || std::strcmp(gui, "1") != 0) return qs::launch::main(argc, argv);

	if (argc != 2 || std::strcmp(argv[1], "--gui") != 0) {
		std::fputs("Managed desktop launch accepts only its declared GUI selector.\n", stderr);
		return 1;
	}
	const auto* resources = std::getenv("COS_APP_RESOURCE_DIR");
	if (!resources || resources[0] != '/') {
		std::fputs("Managed desktop launch requires package-local resources.\n", stderr);
		return 1;
	}
	const std::string shell = std::string(resources) + "/usr/share/claw-desktop-shell";
	::unsetenv("QT_PLUGIN_PATH");
	::unsetenv("QT_QPA_PLATFORM_PLUGIN_PATH");
	::unsetenv("QML2_IMPORT_PATH");
	if (::setenv("QML_IMPORT_PATH", (shell + "/qml").c_str(), 1) != 0) {
		std::perror("Set desktop QML import path");
		return 1;
	}
	std::array<std::string, 4> arguments {argv[0], "--path", shell, "--no-duplicate"};
	std::array<char*, 5> native {};
	for (size_t index = 0; index < arguments.size(); ++index) native[index] = arguments[index].data();
	return qs::launch::main(static_cast<int>(arguments.size()), native.data());
}
