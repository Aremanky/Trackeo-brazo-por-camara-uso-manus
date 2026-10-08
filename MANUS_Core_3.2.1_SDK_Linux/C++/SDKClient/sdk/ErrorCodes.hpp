// SDKClient sdk/ module - SDK return codes as readable text.
// No SDK return code is ever shown to a user as a bare number.
#pragma once

#include "ManusSDKTypes.h"

#include <string>

namespace manus
{
	/// @brief The enumerator name of a return code, e.g. "FunctionNotAvailable".
	const char* ReturnCodeName(SDKReturnCode p_Code);

	/// @brief A one-line explanation for codes a user can act on; "" when there is none.
	const char* ReturnCodeHint(SDKReturnCode p_Code);

	/// @brief "Name (value) - hint", the standard way to present a return code.
	std::string Describe(SDKReturnCode p_Code);

	/// @brief Small wrapper so sdk/ functions return a code that is convenient
	/// to check (`if (!t_Result.Ok())`) and to present (`t_Result.Description()`).
	struct SdkResult
	{
		SDKReturnCode code = SDKReturnCode_Success;

		SdkResult() = default;
		SdkResult(SDKReturnCode p_Code) : code(p_Code) {}

		bool Ok() const { return code == SDKReturnCode_Success; }
		std::string Description() const { return Describe(code); }
	};
}
