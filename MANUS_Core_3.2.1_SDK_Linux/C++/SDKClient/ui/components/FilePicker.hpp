// SDKClient ui/ component - the ONE way a file is picked in any screen.
// A navigable directory listing: Enter descends into folders or picks a file,
// ".." goes up. Optionally filtered to one extension.
#pragma once

#include <ftxui/component/component.hpp>

#include <filesystem>
#include <functional>
#include <memory>
#include <string>
#include <vector>

namespace ui
{
	struct FilePickerState
	{
		std::filesystem::path directory;
		std::string extensionFilter; // e.g. ".lic"; empty shows all files

		int selected = 0;
		// FTXUI's highlight bar follows focused_entry, not selected; bound into
		// the menu so navigation can reset both together.
		int focusedEntry = 0;
		std::vector<std::string> labels;
		std::vector<std::filesystem::path> paths;
		std::vector<bool> isDirectory;

		std::function<void(const std::filesystem::path&)> onPick;
	};

	std::shared_ptr<FilePickerState> MakeFilePickerState(
		const std::string& p_StartDirectory,
		const std::string& p_ExtensionFilter,
		std::function<void(const std::filesystem::path&)> p_OnPick);

	ftxui::Component MakeFilePicker(std::shared_ptr<FilePickerState> p_State);

	/// @brief Re-reads the directory listing (also called on navigation).
	void RefreshFilePicker(FilePickerState& p_State);
}
