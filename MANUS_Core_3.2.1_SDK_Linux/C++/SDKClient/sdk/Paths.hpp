// SDKClient sdk/ module - shared filesystem locations. The default folders the
// other sdk/ modules hand out (calibrations, licenses, temporary skeletons)
// all nest under the user's Documents folder; the home lookup lives here once.
#pragma once

#include <string>

namespace manus
{
	namespace Paths
	{
		/// @brief The user's Documents folder (from USERPROFILE on Windows,
		/// HOME elsewhere), or the current working directory when no home
		/// folder is set.
		std::string Documents();

		/// @brief Documents()/<p_Folder>, or the current working directory
		/// when no home folder is set (the subfolder only applies under a
		/// real home).
		std::string DocumentsSubfolder(const std::string& p_Folder);
	}
}
