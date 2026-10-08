#include "ui/components/RotationGizmo.hpp"

#include <ftxui/dom/canvas.hpp>

#include <cmath>

using namespace ftxui;

namespace ui
{
	namespace
	{
		struct Vec3 { float x, y, z; };

		// Rotate v by quaternion q: v' = v + 2 * qv x (qv x v + w * v)
		Vec3 Rotate(const ManusQuaternion& p_Q, Vec3 p_V)
		{
			const Vec3 t_Qv = { p_Q.x, p_Q.y, p_Q.z };
			auto t_Cross = [](Vec3 a, Vec3 b) {
				return Vec3{ a.y * b.z - a.z * b.y, a.z * b.x - a.x * b.z, a.x * b.y - a.y * b.x };
				};
			const Vec3 t_C1 = t_Cross(t_Qv, p_V);
			const Vec3 t_Inner = { t_C1.x + p_Q.w * p_V.x, t_C1.y + p_Q.w * p_V.y, t_C1.z + p_Q.w * p_V.z };
			const Vec3 t_C2 = t_Cross(t_Qv, t_Inner);
			return { p_V.x + 2.0f * t_C2.x, p_V.y + 2.0f * t_C2.y, p_V.z + 2.0f * t_C2.z };
		}

		// Isometric projection, Z up on screen.
		void Project(Vec3 p_V, float p_Scale, int p_CenterX, int p_CenterY, int& p_OutX, int& p_OutY)
		{
			const float t_ScreenX = (p_V.x - p_V.y) * 0.866f;
			const float t_ScreenY = (p_V.x + p_V.y) * 0.5f - p_V.z;
			p_OutX = p_CenterX + (int)std::lround(t_ScreenX * p_Scale);
			p_OutY = p_CenterY + (int)std::lround(t_ScreenY * p_Scale);
		}
	}

	Element RenderRotationGizmo(const ManusQuaternion& p_Rotation)
	{
		// Normalize; a zero quaternion renders as identity.
		ManusQuaternion t_Q = p_Rotation;
		const float t_Length = std::sqrt(t_Q.w * t_Q.w + t_Q.x * t_Q.x + t_Q.y * t_Q.y + t_Q.z * t_Q.z);
		if (t_Length < 1e-6f) t_Q = { 1.0f, 0.0f, 0.0f, 0.0f };
		else { t_Q.w /= t_Length; t_Q.x /= t_Length; t_Q.y /= t_Length; t_Q.z /= t_Length; }

		const int t_Width = 52, t_Height = 48;      // braille pixels (26x12 cells)
		const int t_CenterX = t_Width / 2, t_CenterY = t_Height / 2;
		const float t_Scale = 14.0f;
		Canvas t_Canvas(t_Width, t_Height);

		// Ground-plane diamond (unrotated) as a depth reference.
		const Vec3 t_Corners[4] = { { 0.9f, 0.9f, 0 }, { 0.9f, -0.9f, 0 }, { -0.9f, -0.9f, 0 }, { -0.9f, 0.9f, 0 } };
		for (int i = 0; i < 4; ++i)
		{
			int t_X1, t_Y1, t_X2, t_Y2;
			Project(t_Corners[i], t_Scale, t_CenterX, t_CenterY, t_X1, t_Y1);
			Project(t_Corners[(i + 1) % 4], t_Scale, t_CenterX, t_CenterY, t_X2, t_Y2);
			t_Canvas.DrawPointLine(t_X1, t_Y1, t_X2, t_Y2, ftxui::Color::GrayDark);
		}

		// The three world axes, rotated by the tracker's orientation.
		const struct { Vec3 axis; ftxui::Color color; const char* label; } t_Axes[3] = {
			{ { 1, 0, 0 }, ftxui::Color::Red,   "X" },
			{ { 0, 1, 0 }, ftxui::Color::Green, "Y" },
			{ { 0, 0, 1 }, ftxui::Color::Blue,  "Z" },
		};
		for (const auto& t_Axis : t_Axes)
		{
			const Vec3 t_Rotated = Rotate(t_Q, t_Axis.axis);
			int t_TipX, t_TipY, t_LabelX, t_LabelY;
			Project(t_Rotated, t_Scale, t_CenterX, t_CenterY, t_TipX, t_TipY);
			Project({ t_Rotated.x * 1.3f, t_Rotated.y * 1.3f, t_Rotated.z * 1.3f },
				t_Scale, t_CenterX, t_CenterY, t_LabelX, t_LabelY);
			t_Canvas.DrawPointLine(t_CenterX, t_CenterY, t_TipX, t_TipY, t_Axis.color);
			t_Canvas.DrawText(t_LabelX, t_LabelY, t_Axis.label, t_Axis.color);
		}

		return canvas(std::move(t_Canvas));
	}
}
