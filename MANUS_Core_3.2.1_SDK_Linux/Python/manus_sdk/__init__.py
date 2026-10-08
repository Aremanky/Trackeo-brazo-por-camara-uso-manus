"""
Manus Python SDK
Python wrapper for the Manus SDK using CFFI

Usage:
    from manus_sdk import lib, ffi, ManusSDK, SDKReturnCode
    
    # Direct CFFI calls for SDK functions
    result = lib.CoreSdk_InitializeCore()
    if result == SDKReturnCode.Success:
        print("SDK initialized")
    
    # Use ManusSDK wrapper only for callbacks
    sdk = ManusSDK()
    sdk.register_raw_skeleton_callback(my_callback_function)
"""

import os
import sys
import platform

def _get_platform_dir():
    """Determine the platform-specific subdirectory for native libraries
    
    Returns tuple of (os_dir, arch_dir) for consistent structure:
    - Windows: windows/x64
    - Linux: linux/amd64 or linux/aarch64
    """
    system = platform.system().lower()
    machine = platform.machine().lower()
    
    # Determine OS and architecture
    if system == 'windows':
        return 'windows', 'x64'
    elif system == 'linux':
        if machine in ('x86_64', 'amd64'):
            return 'linux', 'amd64'
        elif machine in ('aarch64', 'arm64'):
            return 'linux', 'aarch64'
        else:
            return 'linux', machine
    elif system == 'darwin':
        return 'macos', 'arm64'  # Future support
    else:
        return system, machine

def _setup_platform_paths():
    """Add platform-specific directories to the search paths"""
    package_dir = os.path.dirname(os.path.abspath(__file__))
    os_dir, arch_dir = _get_platform_dir()
    
    # Platform-specific subdirectory (e.g., windows/x64, linux/amd64)
    platform_subdir = os.path.join(package_dir, os_dir, arch_dir)
    #platform_subdir = os.path.join(package_dir, 'ManusSDK', 'lib', os_dir, arch_dir)
    
    # Add to Python path for importing .pyd/.so files
    if platform_subdir not in sys.path:
        sys.path.insert(0, platform_subdir)
    
    # Add to DLL search path on Windows (Python 3.8+)
    if sys.platform == 'win32':
        if hasattr(os, 'add_dll_directory'):
            # Python 3.8+ on Windows
            if os.path.isdir(platform_subdir):
                os.add_dll_directory(platform_subdir)
        # Also add to PATH for older Python versions
        os.environ['PATH'] = platform_subdir + os.pathsep + os.environ.get('PATH', '')
    
    # Set LD_LIBRARY_PATH on Linux
    elif sys.platform.startswith('linux'):
        ld_path = os.environ.get('LD_LIBRARY_PATH', '')
        if platform_subdir not in ld_path:
            os.environ['LD_LIBRARY_PATH'] = platform_subdir + (os.pathsep + ld_path if ld_path else '')
    
    return platform_subdir

# Set up platform-specific paths before importing
_platform_dir = _setup_platform_paths()

# Now try to import the CFFI bindings
lib = None
ffi = None

try:
    # Try to import from platform-specific directory (added to sys.path above)
    import _manus_sdk
    lib = _manus_sdk.lib
    ffi = _manus_sdk.ffi
except ImportError:
    try:
        # Fallback: try relative import from package directory (development mode)
        from . import _manus_sdk
        lib = _manus_sdk.lib
        ffi = _manus_sdk.ffi
    except ImportError as e:
        # The compiled bindings need the cffi runtime (_cffi_backend). If cffi
        # itself isn't installed, importing _manus_sdk fails even though the
        # prebuilt binaries are present - fail loudly with the actual fix
        # instead of suggesting a rebuild that wouldn't help.
        try:
            import cffi  # noqa: F401
        except ModuleNotFoundError as cffi_err:
            if cffi_err.name != 'cffi':
                # Something inside cffi is broken, not merely missing -
                # propagate the real error with its chain intact.
                raise
            raise ImportError(
                "The Manus Python SDK requires the 'cffi' package, which is not installed.\n"
                "Install it with:\n"
                "    python -m pip install cffi\n"
                "and then run your script again."
            ) from None
        import warnings
        os_dir, arch_dir = _get_platform_dir()
        warnings.warn(
            f"CFFI bindings not found for {os_dir}/{arch_dir}. "
            f"Expected location: {_platform_dir}. "
            f"Original error: {e}. "
            "Run 'python setup.py build_ext --inplace' or check your installation.",
            stacklevel=2
        )

# Import minimal wrapper (just callback handling)
from .manus_wrapper import ManusSDK

# Import auto-generated enums from generated/ folder
try:
    from .generated._enums import *
except ImportError:
    import warnings
    warnings.warn("Auto-generated enums not found. Run 'python manus_sdk/build_ffi.py' to generate them.")

__version__ = "0.1.0"

__all__ = [
    # Core CFFI objects
    'lib',
    'ffi',
    # Minimal wrapper
    'ManusSDK',
]
