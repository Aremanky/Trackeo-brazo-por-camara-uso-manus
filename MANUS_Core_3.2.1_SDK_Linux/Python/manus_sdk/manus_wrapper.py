"""
Manus SDK Python Wrapper
Only handles callback registration - everything else uses CFFI directly
"""
from typing import Callable

try:
    from _manus_sdk import ffi, lib
except ImportError:
    # Missing cffi runtime is the most common cause - point at the real fix.
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
    print("Warning: CFFI bindings not built yet. Run 'python setup.py build_ext --inplace' first.")
    ffi = None
    lib = None


class ManusSDK:
    """
    Minimal SDK wrapper for callback management.
    
    For all other SDK functions, use lib.CoreSdk_* directly.
    For enums and constants, import from manus_sdk._enums
    
    Example:
        from manus_sdk import lib, ManusSDK, SDKReturnCode
        
        # Direct CFFI calls
        result = lib.CoreSdk_InitializeCore()
        
        # Use wrapper only for callbacks
        sdk = ManusSDK()
        sdk.register_raw_skeleton_callback(my_callback)
    """
    
    # Store callbacks to prevent garbage collection
    _callback_storage = []
    
    def __init__(self):
        if lib is None:
            raise RuntimeError("CFFI bindings not available. Build them first with 'python setup.py build_ext --inplace'")

    def register_raw_skeleton_callback(self, callback: Callable) -> int:
        """
        Register callback for raw skeleton stream data.
        
        Args:
            callback: Function to call when skeleton data arrives.
                     Signature: callback(stream_info: cdata<SkeletonStreamInfo*>)
        
        Returns:
            SDKReturnCode value (0 = Success)
        
        Example:
            def on_skeleton(stream_info):
                print(f"Skeletons: {stream_info.skeletonsCount}")
            
            sdk.register_raw_skeleton_callback(on_skeleton)
        """
        @ffi.def_extern()
        def python_raw_skeleton_callback(stream_info):
            callback(stream_info)
        
        ManusSDK._callback_storage.append(python_raw_skeleton_callback)
        result = lib.CoreSdk_RegisterCallbackForRawSkeletonStream(lib.python_raw_skeleton_callback)
        return result

    def register_skeleton_callback(self, callback: Callable) -> int:
        """Register callback for skeleton stream data."""
        @ffi.def_extern()
        def python_skeleton_callback(stream_info):
            callback(stream_info)
        
        ManusSDK._callback_storage.append(python_skeleton_callback)
        result = lib.CoreSdk_RegisterCallbackForSkeletonStream(lib.python_skeleton_callback)
        return result

    def register_landscape_callback(self, callback: Callable) -> int:
        """Register callback for landscape updates (device changes)."""
        @ffi.def_extern()
        def python_landscape_callback(landscape):
            callback(landscape)
        
        ManusSDK._callback_storage.append(python_landscape_callback)
        result = lib.CoreSdk_RegisterCallbackForLandscapeStream(lib.python_landscape_callback)
        return result

    def register_ergonomics_callback(self, callback: Callable) -> int:
        """Register callback for ergonomics data."""
        @ffi.def_extern()
        def python_ergonomics_callback(ergonomics):
            callback(ergonomics)
        
        ManusSDK._callback_storage.append(python_ergonomics_callback)
        result = lib.CoreSdk_RegisterCallbackForErgonomicsStream(lib.python_ergonomics_callback)
        return result

    def register_raw_device_data_callback(self, callback: Callable) -> int:
        """Register callback for raw device sensor data."""
        @ffi.def_extern()
        def python_raw_device_data_callback(raw_device_info):
            callback(raw_device_info)
        
        ManusSDK._callback_storage.append(python_raw_device_data_callback)
        result = lib.CoreSdk_RegisterCallbackForRawDeviceDataStream(lib.python_raw_device_data_callback)
        return result

    def register_system_callback(self, callback: Callable) -> int:
        """Register callback for system messages."""
        @ffi.def_extern()
        def python_system_callback(system_message):
            callback(system_message)
        
        ManusSDK._callback_storage.append(python_system_callback)
        result = lib.CoreSdk_RegisterCallbackForSystemStream(lib.python_system_callback)
        return result

    def register_connected_callback(self, callback: Callable) -> int:
        """Register callback for connection events."""
        @ffi.def_extern()
        def python_connected_callback(host):
            callback(host)
        
        ManusSDK._callback_storage.append(python_connected_callback)
        result = lib.CoreSdk_RegisterCallbackForOnConnect(lib.python_connected_callback)
        return result

    def register_disconnected_callback(self, callback: Callable) -> int:
        """Register callback for disconnection events."""
        @ffi.def_extern()
        def python_disconnected_callback(host):
            callback(host)
        
        ManusSDK._callback_storage.append(python_disconnected_callback)
        result = lib.CoreSdk_RegisterCallbackForOnDisconnect(lib.python_disconnected_callback)
        return result

    def register_log_callback(self, callback: Callable) -> int:
        """Register callback for SDK logging."""
        @ffi.def_extern()
        def python_log_callback(severity, log_message, length):
            callback(severity, log_message, length)
        
        ManusSDK._callback_storage.append(python_log_callback)
        result = lib.CoreSdk_RegisterCallbackForOnLog(lib.python_log_callback)
        return result

    def register_tracker_callback(self, callback: Callable) -> int:
        """Register callback for tracker stream data."""
        @ffi.def_extern()
        def python_tracker_callback(stream_info):
            callback(stream_info)

        ManusSDK._callback_storage.append(python_tracker_callback)
        result = lib.CoreSdk_RegisterCallbackForTrackerStream(lib.python_tracker_callback)
        return result


__all__ = ['ManusSDK', 'ffi', 'lib']
