#include "ui/components/SkeletonSketch.hpp"

#include <ftxui/dom/canvas.hpp>

#include <algorithm>
#include <cmath>
#include <map>

using namespace ftxui;

namespace ui
{
	namespace
	{
		struct Point2 { float x, y; };

		// Isometric projection, Z up on screen (same view as the rotation gizmo).
		Point2 Project(const ManusVec3& p_Position)
		{
			return {
				(p_Position.x - p_Position.y) * 0.866f,
				(p_Position.x + p_Position.y) * 0.5f - p_Position.z,
			};
		}

		ftxui::Color ChainColor(ChainType p_Chain)
		{
			switch (p_Chain)
			{
			case ChainType_FingerThumb: return FingerColor(0);
			case ChainType_FingerIndex: return FingerColor(1);
			case ChainType_FingerMiddle: return FingerColor(2);
			case ChainType_FingerRing: return FingerColor(3);
			case ChainType_FingerPinky: return FingerColor(4);
			default: return ftxui::Color::GrayLight;
			}
		}
	}

	ftxui::Color FingerColor(int p_FingerIndex)
	{
		switch (p_FingerIndex)
		{
		case 0: return ftxui::Color::Red;
		case 1: return ftxui::Color::Yellow;
		case 2: return ftxui::Color::Green;
		case 3: return ftxui::Color::Cyan;
		case 4: return ftxui::Color::Magenta;
		default: return ftxui::Color::White;
		}
	}

	Element RenderSketch(
		const std::vector<SketchPoint>& p_Points,
		const std::vector<SketchBone>& p_Bones,
		int p_WidthPixels, int p_HeightPixels,
		float p_WorldExtent)
	{
		if (p_Points.empty())
			return text("(nothing to draw)") | dim | center;

		// Project everything; the view centers on the current frame's bounds.
		std::vector<Point2> t_Projected(p_Points.size());
		float t_MinX = 1e9f, t_MaxX = -1e9f, t_MinY = 1e9f, t_MaxY = -1e9f;
		for (size_t i = 0; i < p_Points.size(); ++i)
		{
			t_Projected[i] = Project(p_Points[i].position);
			t_MinX = std::min(t_MinX, t_Projected[i].x);
			t_MaxX = std::max(t_MaxX, t_Projected[i].x);
			t_MinY = std::min(t_MinY, t_Projected[i].y);
			t_MaxY = std::max(t_MaxY, t_Projected[i].y);
		}
		// With a known world extent the scale is CONSTANT - the zoom must not
		// pump when a fist closes. Otherwise auto-fit to the current frame.
		const float t_Extent = p_WorldExtent > 0.0f
			? p_WorldExtent
			: std::max(std::max(t_MaxX - t_MinX, t_MaxY - t_MinY), 1e-4f);
		const float t_Scale = (std::min(p_WidthPixels, p_HeightPixels) - 10) / t_Extent;
		const float t_CenterX = (t_MinX + t_MaxX) * 0.5f;
		const float t_CenterY = (t_MinY + t_MaxY) * 0.5f;

		auto t_ToPixel = [&](const Point2& p_Point, int& p_OutX, int& p_OutY) {
			p_OutX = p_WidthPixels / 2 + (int)std::lround((p_Point.x - t_CenterX) * t_Scale);
			p_OutY = p_HeightPixels / 2 + (int)std::lround((p_Point.y - t_CenterY) * t_Scale);
			};

		Canvas t_Canvas(p_WidthPixels, p_HeightPixels);

		// Bones first, then joints on top so the joints stay visible.
		for (const SketchBone& t_Bone : p_Bones)
		{
			if (t_Bone.from >= p_Points.size() || t_Bone.to >= p_Points.size()) continue;
			int t_X1, t_Y1, t_X2, t_Y2;
			t_ToPixel(t_Projected[t_Bone.from], t_X1, t_Y1);
			t_ToPixel(t_Projected[t_Bone.to], t_X2, t_Y2);
			t_Canvas.DrawPointLine(t_X1, t_Y1, t_X2, t_Y2, t_Bone.color);
		}
		for (size_t i = 0; i < p_Points.size(); ++i)
		{
			int t_X, t_Y;
			t_ToPixel(t_Projected[i], t_X, t_Y);
			// A small plus-shaped cluster makes the joint stand out.
			t_Canvas.DrawPoint(t_X, t_Y, true, p_Points[i].color);
			t_Canvas.DrawPoint(t_X - 1, t_Y, true, p_Points[i].color);
			t_Canvas.DrawPoint(t_X + 1, t_Y, true, p_Points[i].color);
			t_Canvas.DrawPoint(t_X, t_Y - 1, true, p_Points[i].color);
			t_Canvas.DrawPoint(t_X, t_Y + 1, true, p_Points[i].color);
		}

		return canvas(std::move(t_Canvas));
	}

	Element RenderSkeletonSketch(
		const std::vector<SkeletonNode>& p_Nodes,
		const std::vector<NodeInfo>& p_Hierarchy)
	{
		if (p_Nodes.empty())
			return text("(no nodes to draw)") | dim | center;

		std::vector<SketchPoint> t_Points(p_Nodes.size());
		std::map<uint32_t, size_t> t_IndexById;
		for (size_t i = 0; i < p_Nodes.size(); ++i)
		{
			const ftxui::Color t_Color = i < p_Hierarchy.size()
				? ChainColor(p_Hierarchy[i].chainType) : ftxui::Color::White;
			t_Points[i] = { p_Nodes[i].transform.position, t_Color };
			t_IndexById[p_Nodes[i].id] = i;
		}

		std::vector<SketchBone> t_Bones;
		for (size_t i = 0; i < p_Nodes.size() && i < p_Hierarchy.size(); ++i)
		{
			if (p_Hierarchy[i].parentId == p_Hierarchy[i].nodeId) continue; // root
			const auto t_Parent = t_IndexById.find(p_Hierarchy[i].parentId);
			if (t_Parent == t_IndexById.end()) continue;
			t_Bones.push_back({ t_Parent->second, i, ChainColor(p_Hierarchy[i].chainType) });
		}

		// A hand spans ~28 cm; fixing the extent keeps the zoom steady.
		return RenderSketch(t_Points, t_Bones, 120, 88, 0.28f);
	}
}
