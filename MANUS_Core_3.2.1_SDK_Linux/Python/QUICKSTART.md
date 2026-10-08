# Manus Python SDK - Quick Start

## Installation

This folder — the `Python/` folder of the MANUS SDK package — contains a ready-to-use distribution with pre-compiled extensions for Windows and Linux (x64 and ARM64).

## Running Examples

The examples are located in the `examples/` folder next to the `manus_sdk` package. All examples already have the correct path setup in their imports.

### Install dependencies
The SDK needs the `cffi` package installed for the Python version you will run the examples with:

```bash powershell
# Windows
py -m pip install cffi
```

```bash
# Linux
python3 -m pip install cffi
```

For more details, see: https://docs.manus-meta.com/latest/Plugins/SDK/Python/getting started/#step-2-install-dependencies

### Quick Start (Windows)
From this folder, run an example directly:

```bash powershell
# Simple example
py examples/minimal_client.py

# Or Full interactive client
py examples/sdk_client.py
```

### Quick Start (Linux)
From this folder:

```bash
# Simple example
python3 examples/minimal_client.py

# Or Full interactive client
python3 examples/sdk_client.py
```

### Example Controls SDK Client

**sdk_client.py controls:**
- `G` - Gloves & Ergonomics Data
- `S` - Skeleton Data
- `R` - Raw Skeleton Data
- `L` - Landscape Data
- `M` - System Messages
- `B` - Back to main menu
- `Q` - Quit

**Haptic feedback** (hold key to vibrate):
- `1-5` - Left hand fingers (pinky to thumb)
- `6-0` - Right hand fingers (thumb to pinky)

## Using in Your Project

```python
from manus_sdk import lib, ffi, ManusSDK
from manus_sdk.generated._enums import *

# Initialize SDK
result = lib.CoreSdk_InitializeCore()
if result != SDKReturnCode.Success:
    print(f"Failed to initialize: {result.name}")
    exit(1)

# Set up coordinate system
coord_system = ffi.new("CoordinateSystemVUH*")
coord_system.view = AxisView.XFromViewer
coord_system.up = AxisPolarity.PositiveZ
coord_system.handedness = Side.Right
coord_system.unitScale = 1.0
lib.CoreSdk_InitializeCoordinateSystemWithVUH(coord_system[0], False)

# Use ManusSDK wrapper for callbacks
sdk = ManusSDK()
sdk.register_raw_skeleton_callback(my_callback_function)

# Your code here...

# Shutdown
lib.CoreSdk_ShutDown()
```

## Package Contents

- `manus_sdk/` - Core SDK wrapper with CFFI bindings and compiled extensions
  - `__init__.py` - Platform-aware module loader (auto-detects OS and architecture)
  - `manus_wrapper.py` - Minimal callback wrapper
  - `generated/` - Auto-generated enums from C headers
  - `windows/x64/` - Windows x64 binaries
    - `_manus_sdk.cp39-win_amd64.pyd`, `_manus_sdk.cp310-win_amd64.pyd`, etc.
    - `ManusSDK.dll`
  - `linux/amd64/` - Linux x64 binaries
    - `_manus_sdk.cpython-39-x86_64-linux-gnu.so`, etc.
    - `libManusSDK-amd64.so`, `libManusSDK-integrated-amd64.so`
  - `linux/aarch64/` - Linux ARM64 binaries
    - `_manus_sdk.cpython-39-aarch64-linux-gnu.so`, etc.
    - `libManusSDK-aarch64.so`, `libManusSDK-integrated-aarch64.so`
- `examples/` - Example applications
  - `minimal_client.py` - Basic example with callbacks
  - `sdk_client.py` - Interactive menu-based client
- `setup.py` - Installation script

## Supported Platforms & Python Versions

The distribution includes pre-compiled extensions for:

| Platform | Architecture | Supported |
|----------|--------------|:---------:|
| Windows  | x64          | ✅ |
| Linux    | x64 (amd64)  | ✅ |
| Linux    | ARM64 (aarch64) | ✅ |

Python versions: **3.9, 3.10, 3.11, 3.12, 3.13, 3.14**

No compilation needed! The package auto-detects your platform and loads the correct binaries.

## Documentation

See [docs.manus-meta.com](https://docs.manus-meta.com) for detailed documentation on the SDK structure and API usage.
