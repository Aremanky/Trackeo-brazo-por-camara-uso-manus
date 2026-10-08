// SDKClient ui/ component - a pseudo-3D orientation gizmo: the world axes
// rotated by a quaternion, drawn isometrically on a braille canvas.
// X = red, Y = green, Z = blue (MANUS world: Z up); the dim diamond is the
// (unrotated) ground plane for reference.
#pragma once

#include "ManusSDKTypes.h"

#include <ftxui/dom/elements.hpp>

namespace ui
{
	ftxui::Element RenderRotationGizmo(const ManusQuaternion& p_Rotation);
}
