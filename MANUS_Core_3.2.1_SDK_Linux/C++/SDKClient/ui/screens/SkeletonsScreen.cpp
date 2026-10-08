#include "ui/screens/SkeletonsScreen.hpp"

#include "sdk/Connection.hpp"
#include "sdk/LandscapeCache.hpp"
#include "sdk/SkeletonsRaw.hpp"
#include "sdk/SkeletonsRetargeted.hpp"
#include "sdk/SkeletonsTemporary.hpp"

#include "ui/components/AssignmentHint.hpp"
#include "ui/components/DeviceSelector.hpp"
#include "ui/components/FilePicker.hpp"
#include "ui/components/Format.hpp"
#include "ui/components/SkeletonSketch.hpp"
#include "ui/components/StatusMessage.hpp"

#include <ftxui/component/component.hpp>
#include <ftxui/component/event.hpp>
#include <ftxui/dom/elements.hpp>
#include <ftxui/dom/table.hpp>

#include <cstdio>
#include <map>
#include <memory>
#include <string>
#include <vector>

using namespace ftxui;

namespace ui
{
	namespace
	{
		struct SkeletonsState
		{
			int view = 0; // 0 raw, 1 retargeted, 2 temporary
			int tab = 0;

			bool sendToDevTools = false;
			int selectedLoaded = 0;
			std::vector<std::string> loadedLabels;
			std::vector<uint32_t> loadedIds;

			int selectedOwned = 0;
			std::vector<std::string> ownedLabels;
			std::vector<uint32_t> ownedIndexes;
			bool pickingFile = false;
			bool loadAfterImport = false; // picker purpose: also load for animation
			bool confirmClearAll = false;
			bool rawVisual = true; // raw view: sketch (true) or node table (false)

			std::shared_ptr<DeviceSelectorState> gloves;
			std::shared_ptr<FilePickerState> filePicker;
		};

		std::string TransformString(const ManusTransform& p_Transform)
		{
			char t_Buffer[96];
			std::snprintf(t_Buffer, sizeof(t_Buffer), "%6.3f %6.3f %6.3f | %5.2f %5.2f %5.2f %5.2f",
				p_Transform.position.x, p_Transform.position.y, p_Transform.position.z,
				p_Transform.rotation.x, p_Transform.rotation.y, p_Transform.rotation.z, p_Transform.rotation.w);
			return t_Buffer;
		}

		void RebuildLoadedList(SkeletonsState& p_State)
		{
			p_State.loadedIds = manus::SkeletonsRetargeted::LoadedIds();
			p_State.loadedLabels.clear();
			for (const uint32_t t_Id : p_State.loadedIds)
				p_State.loadedLabels.push_back("Skeleton " + Id(t_Id));
			if (p_State.selectedLoaded >= (int)p_State.loadedIds.size()) p_State.selectedLoaded = 0;
		}

		void RebuildOwnedList(SkeletonsState& p_State)
		{
			p_State.ownedIndexes = manus::SkeletonsTemporary::OwnedIndexes();
			p_State.ownedLabels.clear();
			for (const uint32_t t_Index : p_State.ownedIndexes)
				p_State.ownedLabels.push_back("Temporary skeleton, setup index " + std::to_string(t_Index));
			if (p_State.selectedOwned >= (int)p_State.ownedIndexes.size()) p_State.selectedOwned = 0;
		}

		Element RenderAnimationTarget()
		{
			// The example skeletons target user index 0 - say plainly whether
			// that user exists and has gloves, since without them a loaded
			// skeleton sits still and the stream stays silent.
			const Landscape t_Landscape = manus::LandscapeCache::Snapshot();
			if (t_Landscape.users.userCount == 0)
				return text("Animation target: user index 0 - no users in Core, "
					"skeletons will not animate (Users screen).") | dim;

			const UserLandscapeData& t_User = t_Landscape.users.users[0];
			const std::string t_Name = t_User.name[0] != '\0' ? t_User.name : "(unnamed)";
			if (t_User.leftGloveID == 0 && t_User.rightGloveID == 0)
				return text("Animation target: user index 0 = " + t_Name + " (id " + Id(t_User.id)
					+ ") - no gloves assigned, no data will flow (Users screen).") | dim;

			return text("Animation target: user index 0 = " + t_Name + " (id " + Id(t_User.id)
				+ ")  gloves L: " + (t_User.leftGloveID != 0 ? Id(t_User.leftGloveID) : "-")
				+ "  R: " + (t_User.rightGloveID != 0 ? Id(t_User.rightGloveID) : "-"));
		}

		// A sketch of a live retargeted skeleton. The stream carries poses but
		// no parent links; for the 21-node example hand the topology is known
		// (root + 5 fingers of 4 joints), other skeletons show joints only.
		Element RenderRetargetedSketch(const manus::SkeletonsRetargeted::LiveSkeleton& p_Skeleton)
		{
			std::map<uint32_t, size_t> t_IndexById;
			for (size_t i = 0; i < p_Skeleton.nodes.size(); ++i)
				t_IndexById[p_Skeleton.nodes[i].id] = i;

			std::vector<SketchPoint> t_Points(p_Skeleton.nodes.size());
			for (size_t i = 0; i < p_Skeleton.nodes.size(); ++i)
				t_Points[i] = { p_Skeleton.nodes[i].transform.position, ftxui::Color::White };

			std::vector<SketchBone> t_Bones;
			if (p_Skeleton.nodes.size() == 21) // the example hand
			{
				for (int t_Finger = 0; t_Finger < 5; ++t_Finger)
				{
					uint32_t t_ParentId = 0;
					for (int t_Joint = 0; t_Joint < 4; ++t_Joint)
					{
						const uint32_t t_NodeId = 1 + t_Finger * 4 + t_Joint;
						const auto t_From = t_IndexById.find(t_ParentId);
						const auto t_To = t_IndexById.find(t_NodeId);
						if (t_From != t_IndexById.end() && t_To != t_IndexById.end())
						{
							t_Points[t_To->second].color = FingerColor(t_Finger);
							t_Bones.push_back({ t_From->second, t_To->second, FingerColor(t_Finger) });
						}
						t_ParentId = t_NodeId;
					}
				}
			}
			// Fixed scale for the known-size example hand; auto-fit otherwise.
			return RenderSketch(t_Points, t_Bones, 100, 72,
				p_Skeleton.nodes.size() == 21 ? 0.28f : 0.0f);
		}

		Element RenderRetargeted(const SkeletonsState& p_State, Component p_LoadedMenu)
		{
			// Live animated skeletons from the stream.
			const std::vector<manus::SkeletonsRetargeted::LiveSkeleton> t_Skeletons =
				manus::SkeletonsRetargeted::Latest();
			Elements t_Live;
			for (const manus::SkeletonsRetargeted::LiveSkeleton& t_Skeleton : t_Skeletons)
			{
				std::string t_Line = "Skeleton " + Id(t_Skeleton.info.id) + " - "
					+ std::to_string(t_Skeleton.info.nodesCount) + " nodes";
				if (!t_Skeleton.nodes.empty())
					t_Line += "   root (pos x y z | rot x y z w): " + TransformString(t_Skeleton.nodes[0].transform);
				t_Live.push_back(text(t_Line));
			}
			// Sketch the skeleton selected in the left list (stable: the buffer
			// keeps per-id data, so partial stream updates don't switch it).
			if (!p_State.loadedIds.empty() && p_State.selectedLoaded < (int)p_State.loadedIds.size())
			{
				const uint32_t t_WantedId = p_State.loadedIds[p_State.selectedLoaded];
				manus::SkeletonsRetargeted::LiveSkeleton t_Selected;
				t_Live.push_back(separator());
				if (manus::SkeletonsRetargeted::LatestForSkeleton(t_WantedId, t_Selected))
				{
					t_Live.push_back(text("Sketch: skeleton " + Id(t_WantedId)) | dim);
					t_Live.push_back(RenderRetargetedSketch(t_Selected) | center);
				}
				else
				{
					t_Live.push_back(text("No stream data yet for skeleton " + Id(t_WantedId) + ".") | dim);
				}
			}
			else if (!t_Skeletons.empty())
			{
				t_Live.push_back(separator());
				t_Live.push_back(text("Sketch: skeleton " + Id(t_Skeletons.front().info.id)) | dim);
				t_Live.push_back(RenderRetargetedSketch(t_Skeletons.front()) | center);
			}

			return hbox({
				window(text(" Loaded by this client "),
					p_State.loadedLabels.empty()
						? text("(none - [B]/[N] load the example hand)") | dim
						: p_LoadedMenu->Render() | frame) | flex,
				window(text(" Live skeleton stream "),
					t_Live.empty()
						? text("(no animated skeletons - load one and connect a glove)") | dim
						: vbox(std::move(t_Live)) | frame) | flex,
				}) | flex;
		}

		Element RenderTemporary(const SkeletonsState& p_State, Component p_OwnedMenu)
		{
			uint32_t t_Count = 0;
			const manus::SdkResult t_CountResult = manus::SkeletonsTemporary::CountForAllSessions(t_Count);
			Element t_CountLine;
			if (t_CountResult.Ok())
				t_CountLine = text("Temporary skeletons across all sessions: " + std::to_string(t_Count));
			else if (t_CountResult.code == SDKReturnCode_FunctionNotAvailable)
				t_CountLine = text("The all-sessions count is not available in this Core mode/version.") | dim;
			else
				t_CountLine = text("Could not get the count: " + t_CountResult.Description()) | dim;

			Element t_Left = window(text(" This client's temporary skeletons "),
				p_State.ownedLabels.empty()
					? text("(none - [B] build the example)") | dim
					: p_OwnedMenu->Render() | frame);

			return vbox({
				t_CountLine,
				text("Temporary skeletons are shared with the DevTools application for "
					"inspection and editing; they are not loaded for animation.") | dim,
				separator(),
				t_Left | flex,
				}) | flex;
		}

		Element RenderRaw(const SkeletonsState& p_State, Component p_GloveSelector)
		{
			Element t_Right;
			if (!HasSelection(*p_State.gloves))
			{
				t_Right = text("Select a glove on the left.") | dim | center;
			}
			else
			{
				const uint32_t t_GloveId = SelectedId(*p_State.gloves);
				manus::SkeletonsRaw::RawSkeleton t_Skeleton;
				if (!manus::SkeletonsRaw::LatestForGlove(t_GloveId, t_Skeleton))
				{
					t_Right = vbox({
						text("No raw skeleton data for glove " + Id(t_GloveId)
							+ " yet - is it on and streaming?") | dim,
						RenderAssignmentHint(t_GloveId),
						}) | center;
				}
				else
				{
					std::vector<NodeInfo> t_Hierarchy;
					manus::SkeletonsRaw::NodeHierarchy(t_GloveId, t_Hierarchy);

					if (p_State.rawVisual)
					{
						t_Right = vbox({
							text(std::to_string(t_Skeleton.info.nodesCount)
								+ " nodes on the standardized MANUS hand - [V] for the node table"),
							RenderSkeletonSketch(t_Skeleton.nodes, t_Hierarchy) | center | flex,
							}) | flex;
					}
					else
					{
						auto t_Pad = [](const std::string& p_Text) { return " " + p_Text + " "; };
						std::vector<std::vector<std::string>> t_Rows = {
							{ t_Pad("Node"), t_Pad("Parent"), t_Pad("Finger"), t_Pad("Joint"),
							  t_Pad("Position (x y z) / Rotation (x y z w)") } };
						for (size_t i = 0; i < t_Skeleton.nodes.size(); ++i)
						{
							const SkeletonNode& t_Node = t_Skeleton.nodes[i];
							std::string t_Parent = "-", t_Finger = "-", t_Joint = "-";
							if (i < t_Hierarchy.size())
							{
								t_Parent = std::to_string(t_Hierarchy[i].parentId);
								t_Finger = manus::SkeletonsRaw::ChainName(t_Hierarchy[i].chainType);
								t_Joint = manus::SkeletonsRaw::FingerJointName(t_Hierarchy[i].fingerJointType);
							}
							t_Rows.push_back({ t_Pad(std::to_string(t_Node.id)), t_Pad(t_Parent),
								t_Pad(t_Finger), t_Pad(t_Joint), t_Pad(TransformString(t_Node.transform)) });
						}
						Table t_Table(std::move(t_Rows));
						t_Table.SelectAll().Border(LIGHT);
						t_Table.SelectRow(0).Decorate(bold);
						t_Right = vbox({
							text(std::to_string(t_Skeleton.info.nodesCount)
								+ " nodes on the standardized MANUS hand - [V] for the sketch"),
							t_Table.Render() | frame | flex,
							}) | flex;
					}
				}
			}

			// Current raw-skeleton settings.
			HandMotion t_Motion = HandMotion_None;
			manus::SkeletonsRaw::GetHandMotion(t_Motion);
			bool t_Pinch = false;
			const bool t_HavePinch = manus::SkeletonsRaw::GetPinchCompensation(t_Pinch).Ok();
			float t_Casing = 0.0f;
			const bool t_HaveCasing = manus::SkeletonsRaw::GetCasingCompensation(t_Casing).Ok();
			char t_CasingText[32];
			std::snprintf(t_CasingText, sizeof(t_CasingText), "%.2f", t_Casing);

			return hbox({
				vbox({
					window(text(" Gloves "), p_GloveSelector->Render()) | flex,
					window(text(" Settings "), vbox({
						text("Wrist motion: " + std::string(manus::SkeletonsRaw::HandMotionName(t_Motion))),
						text(std::string("Pinch compensation:  ") + (t_HavePinch ? (t_Pinch ? "Enabled" : "Disabled") : "n/a")),
						text(std::string("Casing compensation: ") + (t_HaveCasing ? t_CasingText : "n/a")),
						})),
					}) | size(WIDTH, GREATER_THAN, 46),
				t_Right | flex,
				}) | flex;
		}

		std::string ViewHints(const SkeletonsState& p_State)
		{
			if (p_State.pickingFile) return " [Up/Down] browse   [Enter] open folder / import file   [C] cancel ";
			if (p_State.confirmClearAll) return " [Y] clear ALL sessions' temporary skeletons   [C] cancel ";
			switch (p_State.view)
			{
			case 0: return " [V] sketch/table   [H] cycle wrist motion   [P] pinch compensation   [J]/[K] casing compensation -/+   |   [2][3] other views ";
			case 1: return " [B] load left hand   [N] load right hand   [L] load .mskl...   [M] unload selected   [D] DevTools on load: toggle   |   [1][3] other views ";
			default: return " [B] build example   [E] export selected   [F] import .mskl...   [C] clear selected   [X] clear all...   |   [1][2] other views ";
			}
		}
	}

	Component MakeSkeletonsScreen()
	{
		auto t_State = std::make_shared<SkeletonsState>();
		t_State->gloves = MakeDeviceSelectorState(DeviceKind::Gloves);
		t_State->filePicker = MakeFilePickerState(
			manus::SkeletonsTemporary::DefaultSkeletonFolder(), ".mskl",
			[t_State](const std::filesystem::path& p_File) {
				t_State->pickingFile = false;

				uint32_t t_Index = 0;
				const manus::SdkResult t_Result = manus::SkeletonsTemporary::LoadFromFile(
					manus::Connection::CurrentInfo().sessionId, p_File.string(), t_Index);
				if (!t_Result.Ok())
				{
					Status::Error("Import failed: " + t_Result.Description());
					return;
				}
				if (!t_State->loadAfterImport)
				{
					Status::Success("Imported \"" + p_File.filename().string()
						+ "\" as temporary skeleton (setup index " + std::to_string(t_Index) + ").");
					return;
				}

				// Retargeted view: the imported setup goes straight into Core
				// for animation.
				uint32_t t_SkeletonId = 0;
				const manus::SdkResult t_LoadResult = manus::SkeletonsRetargeted::LoadSetup(t_Index, t_SkeletonId);
				if (!t_LoadResult.Ok())
				{
					Status::Error("Imported the setup, but loading it failed: " + t_LoadResult.Description());
					return;
				}
				manus::SkeletonsTemporary::Untrack(t_Index); // consumed by the load
				Status::Success("Loaded \"" + p_File.filename().string() + "\" as skeleton "
					+ Id(t_SkeletonId) + ".");
			});

		Component t_LoadedMenu = Menu(&t_State->loadedLabels, &t_State->selectedLoaded);
		Component t_OwnedMenu = Menu(&t_State->ownedLabels, &t_State->selectedOwned);
		Component t_GloveSelector = MakeDeviceSelector(t_State->gloves);
		Component t_FilePicker = MakeFilePicker(t_State->filePicker);

		Component t_Areas = Container::Tab(
			{ t_GloveSelector, t_LoadedMenu, t_OwnedMenu, t_FilePicker }, &t_State->tab);

		Component t_Root = Renderer(t_Areas, [=] {
			RebuildLoadedList(*t_State);
			RebuildOwnedList(*t_State);

			if (t_State->pickingFile) t_State->tab = 3;
			else t_State->tab = t_State->view;

			Element t_Body;
			std::string t_Title;
			if (t_State->pickingFile)
			{
				// The picker is rendered here, view-independently, so it is
				// visible no matter which view requested it.
				t_Title = t_State->loadAfterImport
					? " Pick a .mskl file to load for animation "
					: " Pick a .mskl file to import ";
				t_Body = t_FilePicker->Render() | flex;
			}
			else switch (t_State->view)
			{
			case 0:
				t_Title = " Skeletons - [1] Raw ";
				t_Body = RenderRaw(*t_State, t_GloveSelector);
				break;
			case 1:
				t_Title = " Skeletons - [2] Retargeted ";
				t_Body = vbox({
					text(std::string("Send new skeletons to DevTools on load: ")
						+ (t_State->sendToDevTools ? "Enabled" : "Disabled")
						+ "  (shares the setup so DevTools can inspect it)") | dim,
					RenderAnimationTarget(),
					RenderRetargeted(*t_State, t_LoadedMenu),
					}) | flex;
				break;
			default:
				t_Title = " Skeletons - [3] Temporary ";
				t_Body = RenderTemporary(*t_State, t_OwnedMenu);
				break;
			}

			return vbox({
				Status::Render(),
				window(text(t_Title), t_Body) | flex,
				text(ViewHints(*t_State)) | dim,
				}) | flex;
			});

		return CatchEvent(t_Root, [t_State](Event p_Event) {
			const bool t_IsC = p_Event == Event::Character('c') || p_Event == Event::Character('C');

			if (t_State->pickingFile)
			{
				if (t_IsC)
				{
					t_State->pickingFile = false;
					Status::Clear();
					return true;
				}
				return false;
			}
			if (t_State->confirmClearAll)
			{
				if (p_Event == Event::Character('y') || p_Event == Event::Character('Y'))
				{
					const manus::SdkResult t_Result = manus::SkeletonsTemporary::ClearAll();
					if (!t_Result.Ok()) Status::Error("Clear all failed: " + t_Result.Description());
					else Status::Success("Cleared the temporary skeletons of all sessions.");
					t_State->confirmClearAll = false;
					return true;
				}
				if (t_IsC)
				{
					t_State->confirmClearAll = false;
					Status::Clear();
					return true;
				}
				return false;
			}

			if (p_Event == Event::Character('1')) { t_State->view = 0; return true; }
			if (p_Event == Event::Character('2')) { t_State->view = 1; return true; }
			if (p_Event == Event::Character('3')) { t_State->view = 2; return true; }

			const uint32_t t_SessionId = manus::Connection::CurrentInfo().sessionId;

			if (t_State->view == 1) // Retargeted
			{
				const bool t_IsB = p_Event == Event::Character('b') || p_Event == Event::Character('B');
				const bool t_IsN = p_Event == Event::Character('n') || p_Event == Event::Character('N');
				if (t_IsB || t_IsN)
				{
					uint32_t t_SkeletonId = 0;
					const Side t_Side = t_IsB ? Side_Left : Side_Right;
					const manus::SdkResult t_Result = manus::SkeletonsRetargeted::LoadExampleHand(
						t_Side, t_State->sendToDevTools, t_SessionId, t_SkeletonId);
					if (!t_Result.Ok()) Status::Error("Failed to load skeleton: " + t_Result.Description());
					else Status::Success(std::string("Loaded the example ") + (t_IsB ? "left" : "right")
						+ " hand as skeleton " + Id(t_SkeletonId) + " (animates with user index 0).");
					return true;
				}
				if (p_Event == Event::Character('m') || p_Event == Event::Character('M'))
				{
					if (t_State->loadedIds.empty())
					{
						Status::Info("Nothing to unload.");
						return true;
					}
					const uint32_t t_SkeletonId = t_State->loadedIds[t_State->selectedLoaded];
					const manus::SdkResult t_Result = manus::SkeletonsRetargeted::Unload(t_SkeletonId);
					if (!t_Result.Ok()) Status::Error("Failed to unload: " + t_Result.Description());
					else Status::Success("Unloaded skeleton " + Id(t_SkeletonId) + ".");
					return true;
				}
				if (p_Event == Event::Character('l') || p_Event == Event::Character('L'))
				{
					t_State->pickingFile = true;
					t_State->loadAfterImport = true;
					RefreshFilePicker(*t_State->filePicker);
					Status::Info("Pick the .mskl file to load for animation.");
					return true;
				}
				if (p_Event == Event::Character('d') || p_Event == Event::Character('D'))
				{
					t_State->sendToDevTools = !t_State->sendToDevTools;
					return true;
				}
				return false;
			}

			if (t_State->view == 2) // Temporary
			{
				if (p_Event == Event::Character('b') || p_Event == Event::Character('B'))
				{
					uint32_t t_Index = 0;
					const manus::SdkResult t_Result = manus::SkeletonsTemporary::BuildExample(t_SessionId, t_Index);
					if (!t_Result.Ok()) Status::Error("Failed to build: " + t_Result.Description());
					else Status::Success("Built the example hand as temporary skeleton (setup index "
						+ std::to_string(t_Index) + ") - visible in DevTools.");
					return true;
				}
				if (p_Event == Event::Character('e') || p_Event == Event::Character('E'))
				{
					if (t_State->ownedIndexes.empty())
					{
						Status::Info("No temporary skeleton to export - [B] build one first.");
						return true;
					}
					const uint32_t t_Index = t_State->ownedIndexes[t_State->selectedOwned];
					const std::string t_Path = manus::SkeletonsTemporary::DefaultSkeletonFolder()
						+ "/TemporarySkeleton_" + std::to_string(t_Index) + ".mskl";
					const manus::SdkResult t_Result = manus::SkeletonsTemporary::SaveToFile(t_Index, t_SessionId, t_Path);
					if (!t_Result.Ok()) Status::Error("Export failed: " + t_Result.Description());
					else Status::Success("Exported to " + t_Path);
					return true;
				}
				if (p_Event == Event::Character('f') || p_Event == Event::Character('F'))
				{
					t_State->pickingFile = true;
					t_State->loadAfterImport = false;
					RefreshFilePicker(*t_State->filePicker);
					Status::Info("Pick the .mskl file to import.");
					return true;
				}
				if (t_IsC)
				{
					if (t_State->ownedIndexes.empty())
					{
						Status::Info("No temporary skeleton to clear.");
						return true;
					}
					const uint32_t t_Index = t_State->ownedIndexes[t_State->selectedOwned];
					const manus::SdkResult t_Result = manus::SkeletonsTemporary::Clear(t_Index, t_SessionId);
					if (!t_Result.Ok()) Status::Error("Clear failed: " + t_Result.Description());
					else Status::Success("Cleared temporary skeleton (setup index " + std::to_string(t_Index) + ").");
					return true;
				}
				if (p_Event == Event::Character('x') || p_Event == Event::Character('X'))
				{
					t_State->confirmClearAll = true;
					Status::Info("Clear the temporary skeletons of ALL sessions (also other clients')? [Y]/[C]");
					return true;
				}
				return false;
			}

			// Raw view
			if (p_Event == Event::Character('v') || p_Event == Event::Character('V'))
			{
				t_State->rawVisual = !t_State->rawVisual;
				return true;
			}
			if (p_Event == Event::Character('h') || p_Event == Event::Character('H'))
			{
				HandMotion t_Motion = HandMotion_None;
				manus::SkeletonsRaw::GetHandMotion(t_Motion);
				const HandMotion t_Next = t_Motion == HandMotion_Auto ? HandMotion_None : (HandMotion)(t_Motion + 1);
				const manus::SdkResult t_Result = manus::SkeletonsRaw::SetHandMotion(t_Next);
				if (!t_Result.Ok()) Status::Error("Failed to set wrist motion: " + t_Result.Description());
				else Status::Success(std::string("Wrist motion: ") + manus::SkeletonsRaw::HandMotionName(t_Next));
				return true;
			}
			if (p_Event == Event::Character('p') || p_Event == Event::Character('P'))
			{
				bool t_Enabled = false;
				manus::SkeletonsRaw::GetPinchCompensation(t_Enabled);
				const manus::SdkResult t_Result = manus::SkeletonsRaw::SetPinchCompensation(!t_Enabled);
				if (!t_Result.Ok()) Status::Error("Failed to switch pinch compensation: " + t_Result.Description());
				else Status::Success(std::string("Pinch compensation ") + (!t_Enabled ? "Enabled." : "Disabled."));
				return true;
			}
			const bool t_IsJ = p_Event == Event::Character('j') || p_Event == Event::Character('J');
			const bool t_IsK = p_Event == Event::Character('k') || p_Event == Event::Character('K');
			if (t_IsJ || t_IsK)
			{
				float t_Strength = 0.0f;
				manus::SkeletonsRaw::GetCasingCompensation(t_Strength);
				t_Strength += t_IsK ? 0.1f : -0.1f;
				if (t_Strength < 0.0f) t_Strength = 0.0f;
				if (t_Strength > 1.0f) t_Strength = 1.0f;
				const manus::SdkResult t_Result = manus::SkeletonsRaw::SetCasingCompensation(t_Strength);
				char t_Text[64];
				std::snprintf(t_Text, sizeof(t_Text), "Casing compensation strength: %.2f", t_Strength);
				if (!t_Result.Ok()) Status::Error("Failed to set casing compensation: " + t_Result.Description());
				else Status::Success(t_Text);
				return true;
			}
			return false;
			});
	}
}
