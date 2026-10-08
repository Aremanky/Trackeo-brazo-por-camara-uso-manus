#include "sdk/Paths.hpp"

#include <cstdlib>
#include <filesystem>

namespace manus
{
	namespace
	{
		const char* HomeFolder()
		{
#ifdef _WIN32
			return std::getenv("USERPROFILE");
#else
			return std::getenv("HOME");
#endif
		}
	}

	std::string Paths::Documents()
	{
		const char* t_Home = HomeFolder();
		if (t_Home == nullptr) return std::filesystem::current_path().string();
		return (std::filesystem::path(t_Home) / "Documents").string();
	}

	std::string Paths::DocumentsSubfolder(const std::string& p_Folder)
	{
		const char* t_Home = HomeFolder();
		if (t_Home == nullptr) return std::filesystem::current_path().string();
		return (std::filesystem::path(t_Home) / "Documents" / p_Folder).string();
	}
}
