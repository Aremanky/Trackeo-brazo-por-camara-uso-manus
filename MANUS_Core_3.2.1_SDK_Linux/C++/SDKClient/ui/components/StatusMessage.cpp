#include "ui/components/StatusMessage.hpp"

#include <mutex>

using namespace ftxui;

namespace ui
{
	namespace
	{
		enum class Kind { None, Info, Success, Error, Busy };

		std::mutex g_Mutex;
		Kind g_Kind = Kind::None;
		std::string g_Text;
		int g_Frame = 0;

		void Set(Kind p_Kind, const std::string& p_Text)
		{
			std::lock_guard<std::mutex> t_Lock(g_Mutex);
			g_Kind = p_Kind;
			g_Text = p_Text;
		}
	}

	void Status::Info(const std::string& p_Text) { Set(Kind::Info, p_Text); }
	void Status::Success(const std::string& p_Text) { Set(Kind::Success, p_Text); }
	void Status::Error(const std::string& p_Text) { Set(Kind::Error, p_Text); }
	void Status::Busy(const std::string& p_Text) { Set(Kind::Busy, p_Text); }
	void Status::Clear() { Set(Kind::None, ""); }

	Element Status::Render()
	{
		std::lock_guard<std::mutex> t_Lock(g_Mutex);
		switch (g_Kind)
		{
		case Kind::Info: return text(g_Text);
		case Kind::Success: return text(g_Text) | color(Color::Green);
		case Kind::Error: return text(g_Text) | color(Color::Red);
		case Kind::Busy: return hbox({ spinner(2, ++g_Frame / 2), text(" " + g_Text) });
		default: return text("");
		}
	}
}
