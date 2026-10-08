#include "ui/components/AssignmentHint.hpp"

#include "sdk/Connection.hpp"
#include "sdk/Users.hpp"

using namespace ftxui;

namespace ui
{
	Element RenderAssignmentHint(uint32_t p_GloveId)
	{
		UserLandscapeData t_User{};
		if (manus::Users::TryFindUserForGlove(p_GloveId, t_User))
			return emptyElement();

		return text(std::string("No user assigned - data only flows for assigned gloves. ")
			+ (manus::Connection::Mode() == manus::ConnectionMode::Integrated
				? "Auto-assignment may be off (Users screen)."
				: "Assign one on the Users screen.")) | dim;
	}
}
