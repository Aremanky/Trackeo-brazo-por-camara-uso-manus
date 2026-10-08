#include "ui/components/FilePicker.hpp"

#include <ftxui/component/component.hpp>
#include <ftxui/component/component_options.hpp>
#include <ftxui/dom/elements.hpp>

#include <algorithm>

#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#endif

using namespace ftxui;

namespace ui
{
	void RefreshFilePicker(FilePickerState& p_State)
	{
		p_State.labels.clear();
		p_State.paths.clear();
		p_State.isDirectory.clear();
		p_State.selected = 0;
		p_State.focusedEntry = 0;

		if (p_State.directory.has_parent_path()
			&& p_State.directory.parent_path() != p_State.directory)
		{
			p_State.labels.push_back("[..]");
			p_State.paths.push_back(p_State.directory.parent_path());
			p_State.isDirectory.push_back(true);
		}
#ifdef _WIN32
		else
		{
			// At a drive root [..] has nowhere to go; list the other drives
			// instead so the whole system is reachable.
			const DWORD t_Drives = GetLogicalDrives();
			for (char t_Letter = 'A'; t_Letter <= 'Z'; ++t_Letter)
			{
				if ((t_Drives & (1u << (t_Letter - 'A'))) == 0) continue;
				const std::string t_Root = std::string(1, t_Letter) + ":\\";
				if (std::filesystem::path(t_Root) == p_State.directory) continue;
				p_State.labels.push_back("[" + t_Root + "]");
				p_State.paths.push_back(t_Root);
				p_State.isDirectory.push_back(true);
			}
		}
#endif

		std::vector<std::filesystem::path> t_Folders;
		std::vector<std::filesystem::path> t_Files;
		std::error_code t_Error;
		for (const auto& t_Entry : std::filesystem::directory_iterator(p_State.directory, t_Error))
		{
			if (t_Entry.is_directory(t_Error)) t_Folders.push_back(t_Entry.path());
			else if (p_State.extensionFilter.empty()
				|| t_Entry.path().extension().string() == p_State.extensionFilter)
				t_Files.push_back(t_Entry.path());
		}
		std::sort(t_Folders.begin(), t_Folders.end());
		std::sort(t_Files.begin(), t_Files.end());

		for (const std::filesystem::path& t_Folder : t_Folders)
		{
			p_State.labels.push_back("[" + t_Folder.filename().string() + "]");
			p_State.paths.push_back(t_Folder);
			p_State.isDirectory.push_back(true);
		}
		for (const std::filesystem::path& t_File : t_Files)
		{
			p_State.labels.push_back(t_File.filename().string());
			p_State.paths.push_back(t_File);
			p_State.isDirectory.push_back(false);
		}
	}

	std::shared_ptr<FilePickerState> MakeFilePickerState(
		const std::string& p_StartDirectory,
		const std::string& p_ExtensionFilter,
		std::function<void(const std::filesystem::path&)> p_OnPick)
	{
		auto t_State = std::make_shared<FilePickerState>();
		t_State->directory = p_StartDirectory;
		t_State->extensionFilter = p_ExtensionFilter;
		t_State->onPick = std::move(p_OnPick);
		RefreshFilePicker(*t_State);
		return t_State;
	}

	Component MakeFilePicker(std::shared_ptr<FilePickerState> p_State)
	{
		MenuOption t_Option = MenuOption::Vertical();
		t_Option.focused_entry = &p_State->focusedEntry;
		t_Option.on_enter = [p_State] {
			if (p_State->selected < 0 || p_State->selected >= (int)p_State->paths.size()) return;
			const std::filesystem::path t_Path = p_State->paths[p_State->selected];
			if (p_State->isDirectory[p_State->selected])
			{
				p_State->directory = t_Path;
				RefreshFilePicker(*p_State);
				return;
			}
			if (p_State->onPick) p_State->onPick(t_Path);
			};
		Component t_Menu = Menu(&p_State->labels, &p_State->selected, t_Option);

		return Renderer(t_Menu, [p_State, t_Menu] {
			return vbox({
				text(p_State->directory.string()) | dim,
				separator(),
				p_State->labels.empty()
					? text("(empty folder)") | dim
					: t_Menu->Render() | frame | flex,
				}) | flex;
			});
	}
}
