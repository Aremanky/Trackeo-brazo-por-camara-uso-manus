#include "ui/components/Format.hpp"

#include <sstream>

namespace ui
{
	std::string Id(uint32_t p_Id)
	{
		std::ostringstream t_Stream;
		t_Stream << "0x" << std::hex << std::uppercase << p_Id;
		return t_Stream.str();
	}
}
