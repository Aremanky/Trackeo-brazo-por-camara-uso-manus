// SDKClient ui/ component - pseudo-3D sketches on a braille canvas: joints
// (prominent dots) and bones (lines) in an isometric projection (Z up),
// auto-fitted and centered. Used for raw skeletons, retargeted skeletons and
// raw sensor data.
#pragma once

#include "ManusSDKTypes.h"

#include <ftxui/dom/elements.hpp>

#include <cstddef>
#include <vector>

namespace ui
{
	struct SketchPoint
	{
		ManusVec3 position;
		ftxui::Color color;
	};

	struct SketchBone
	{
		std::size_t from; // indexes into the point list
		std::size_t to;
		ftxui::Color color;
	};

	/// @brief The palette used for finger chains (0 = thumb .. 4 = pinky).
	ftxui::Color FingerColor(int p_FingerIndex);

	/// @brief Draws points (as prominent dots) and bones (as lines).
	/// p_WorldExtent fixes the scale to that many meters across the canvas -
	/// use it for content of known physical size (a hand) so the zoom does not
	/// jump with the pose. 0 auto-fits to the current frame instead.
	ftxui::Element RenderSketch(
		const std::vector<SketchPoint>& p_Points,
		const std::vector<SketchBone>& p_Bones,
		int p_WidthPixels = 120, int p_HeightPixels = 88,
		float p_WorldExtent = 0.0f);

	/// @brief Convenience for raw skeletons: p_Nodes carries the poses;
	/// p_Hierarchy (same order, from sdk/SkeletonsRaw NodeHierarchy) provides
	/// parent links and per-finger colors.
	ftxui::Element RenderSkeletonSketch(
		const std::vector<SkeletonNode>& p_Nodes,
		const std::vector<NodeInfo>& p_Hierarchy);
}
