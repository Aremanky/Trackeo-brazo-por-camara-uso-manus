#include "app/SelfTests.hpp"

#include "sdk/Connection.hpp"

#include "ui/components/Focusable.hpp"
#include "ui/screens/SkeletonsScreen.hpp"

#include <ftxui/component/component.hpp>
#include <ftxui/component/event.hpp>
#include <ftxui/dom/elements.hpp>
#include <ftxui/dom/table.hpp>
#include <ftxui/screen/screen.hpp>

#include <cstdio>
#include <string>
#include <vector>

using namespace ftxui;

namespace app
{
	int RunSmokeTest()
	{
		const manus::SdkResult t_InitResult = manus::Connection::Initialize(manus::ConnectionMode::Remote);

		Table t_SampleTable({
			{ "ID", "Side", "Battery" },
			{ "42", "Left", "87%" },
			{ "43", "Right", "91%" },
			});
		t_SampleTable.SelectAll().Border(LIGHT);
		t_SampleTable.SelectRow(0).Decorate(bold);

		Element t_Document = window(text(" SDKClient - smoke test ") | bold,
			vbox({
				text("SDK init: " + t_InitResult.Description()),
				separator(),
				t_SampleTable.Render(),
				}));

		Screen t_ScreenBuffer = Screen::Create(Dimension::Fixed(60), Dimension::Fit(t_Document));
		Render(t_ScreenBuffer, t_Document);
		printf("%s\n", t_ScreenBuffer.ToString().c_str());

		manus::Connection::Shutdown();

		printf("SMOKE %s\n", t_InitResult.Ok() ? "PASS" : "FAIL");
		return t_InitResult.Ok() ? 0 : 2;
	}

	int RunEventProbe()
	{
		Component t_Screen = ui::MakeSkeletonsScreen();

		auto t_RenderToString = [&t_Screen] {
			Screen t_Buffer = Screen::Create(Dimension::Fixed(110), Dimension::Fixed(30));
			Render(t_Buffer, t_Screen->Render());
			return t_Buffer.ToString();
			};

		std::string t_Frame = t_RenderToString();
		printf("initial view is [1]:        %s\n", t_Frame.find("[1] Raw") != std::string::npos ? "PASS" : "FAIL");

		const bool t_Handled2 = t_Screen->OnEvent(Event::Character('2'));
		t_Frame = t_RenderToString();
		printf("'2' handled:                %s\n", t_Handled2 ? "PASS" : "FAIL");
		printf("view switched to [2]:       %s\n", t_Frame.find("[2] Retargeted") != std::string::npos ? "PASS" : "FAIL");

		// 'b' loads the example left hand; without a running Core it fails,
		// but either way a status line must appear.
		const bool t_HandledB = t_Screen->OnEvent(Event::Character('b'));
		t_Frame = t_RenderToString();
		printf("'b' handled:                %s\n", t_HandledB ? "PASS" : "FAIL");
		printf("'b' produced a status line: %s\n",
			(t_Frame.find("Failed") != std::string::npos || t_Frame.find("Loaded") != std::string::npos) ? "PASS" : "FAIL");

		const bool t_Handled3 = t_Screen->OnEvent(Event::Character('3'));
		t_Frame = t_RenderToString();
		printf("view switched to [3]:       %s\n",
			t_Handled3 && t_Frame.find("[3] Temporary") != std::string::npos ? "PASS" : "FAIL");

		// Now replicate the app shell's exact nesting: CatchEvent(Renderer(Tab{..., Tab{screens}})).
		{
			std::vector<std::string> t_Dummy = { "a", "b" };
			int t_DummySelected = 0;
			Component t_Menu1 = Menu(&t_Dummy, &t_DummySelected);
			Component t_Menu2 = Menu(&t_Dummy, &t_DummySelected);
			Component t_Menu3 = Menu(&t_Dummy, &t_DummySelected);
			Component t_Skeletons = ui::MakeSkeletonsScreen();
			Component t_OtherScreen = Renderer([] { return text("other"); });

			int t_ActiveScreen = 1; // Skeletons is second in this fake registry
			Component t_ScreenTab = Container::Tab(
				{ ui::AlwaysFocusable(t_OtherScreen), ui::AlwaysFocusable(t_Skeletons) }, &t_ActiveScreen);
			int t_ActiveArea = 3;
			Component t_Areas = Container::Tab({ t_Menu1, t_Menu2, t_Menu3, t_ScreenTab }, &t_ActiveArea);
			Component t_AppRoot = Renderer(t_Areas, [&] { return t_ScreenTab->Render(); });
			t_AppRoot = CatchEvent(t_AppRoot, [](Event) { return false; });

			auto t_RenderApp = [&] {
				Screen t_Buffer = Screen::Create(Dimension::Fixed(110), Dimension::Fixed(30));
				Render(t_Buffer, t_AppRoot->Render());
				return t_Buffer.ToString();
				};
			t_RenderApp();
			const bool t_NestedHandled = t_AppRoot->OnEvent(Event::Character('2'));
			const std::string t_AppFrame = t_RenderApp();
			printf("nested: '2' handled:        %s\n", t_NestedHandled ? "PASS" : "FAIL");
			printf("nested: view is [2]:        %s\n",
				t_AppFrame.find("[2] Retargeted") != std::string::npos ? "PASS" : "FAIL");
		}
		return 0;
	}
}
