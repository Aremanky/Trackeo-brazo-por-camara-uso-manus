#include "ui/components/Focusable.hpp"

using namespace ftxui;

namespace ui
{
	namespace
	{
		class AlwaysFocusableBase : public ComponentBase
		{
		public:
			explicit AlwaysFocusableBase(Component p_Child) { Add(std::move(p_Child)); }

			bool Focusable() const override { return true; }
			Element OnRender() override { return children_[0]->Render(); }
		};
	}

	Component AlwaysFocusable(Component p_Child)
	{
		return Make<AlwaysFocusableBase>(std::move(p_Child));
	}
}
