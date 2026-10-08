# MANUS SDK — Getting started

The MANUS SDK is our library that allows you to receive data from and interact with MANUS gloves. The SDK is compatible with both Windows and Linux and gives you complete freedom to integrate MANUS gloves into your application or platform.

This document is a quick tour of the package. The full documentation, including API reference and step-by-step guides, lives in the MANUS Knowledge Center:

- Getting started: https://docs.manus-meta.com/latest/Plugins/SDK/getting started/
- API reference: https://docs.manus-meta.com/latest/SDK/_manus_s_d_k_8h/

> **License requirement:** Using the SDK requires a MANUS license key with the `SDK` feature enabled.

## Package contents

- `C++` — The C++ SDK examples
    - `SDKClient` — The SDK Client example, a CMake project that includes the `ManusSDK` library. A full example demonstrating all SDK functionality: initialization, connection, pairing/un-pairing, glove calibration, skeleton loading/saving, and more.
    - `SDKMinimalClient` — The SDK Minimal Client example, including the `ManusSDK` library. A bare-bones example demonstrating the minimal amount of code needed to get the SDK connected and receiving glove data.
    - `SDKClient.sln` — Visual Studio solution that builds both examples (Windows package only)

- `Python` — The Python SDK and its examples
    - `manus_sdk` — The Python SDK package with pre-compiled extensions for Python 3.9 through 3.14 (no compilation needed)
    - `examples` — The Python examples: `minimal_client.py` and `sdk_client.py`
    - `QUICKSTART.md` — How to install the Python SDK and run the examples
    - `setup.py` and `tests`

- `ROS2 package` — The MANUS ROS2 package, a ROS2 wrapper around the SDK (Linux package only)

- `MANUS Core Dashboard (Windows build)` / `MANUS Core Dashboard (Linux build)` — A ready-to-run build of the MANUS Core Dashboard

- `Third-party notices` — License texts of the open-source components included in the ManusSDK binaries

- `Getting started.md` and `LICENSE`

## Quick start

### C++ on Windows

The SDK Client is a CMake project — see https://docs.manus-meta.com/latest/Plugins/SDK/C++/SDK Client/ for build instructions. Alternatively, the provided `C++/SDKClient.sln` opens both the SDK Client and the SDK Minimal Client in Visual Studio.

### C++ on Linux

A number of dependencies are required for compilation and execution. Both C++ project folders contain an `install-dependencies.sh` script that installs them. The SDK Client is built with CMake, the SDK Minimal Client with the provided Makefile. Please refer to the full Linux guide for exact installation instructions: https://docs.manus-meta.com/latest/Plugins/SDK/Linux/

### Python

See `Python/QUICKSTART.md`. In short, from inside the `Python` folder:

```bash
# Windows
py examples/minimal_client.py

# Linux
python3 examples/minimal_client.py
```

The full Python guide is at https://docs.manus-meta.com/latest/Plugins/SDK/Python/getting started/

### ROS2 (Linux package only)

See https://docs.manus-meta.com/latest/Plugins/SDK/ROS2/getting started/ for setup and usage of the ROS2 package.

## SDK Integrated vs Remote

The SDK can be used in two ways: integrated and remote.

The **integrated** SDK is fully integrated into your application and functions standalone, talking directly to the glove hardware without requiring a MANUS Core connection. This is useful for applications that want to deeply integrate MANUS glove devices, but requires manually handling glove calibration, pairing/un-pairing, and tracker data.

The SDK is used in **remote** mode when used in conjunction with MANUS Core. This is generally easier to implement because all glove management is handled by the MANUS Core Dashboard, and the SDK only needs to connect to MANUS Core and receive glove data. It is necessary when using multiple glove pairs and when using the built-in tracking system integrations (SteamVR, ART, Vicon).

Do be mindful that MANUS Core itself is only available on Windows: using the SDK in remote mode on Linux requires a separate machine running MANUS Core on Windows.

For more information, see https://docs.manus-meta.com/latest/Plugins/SDK/SDK Integrated/

## License

Use of this package is governed by the Manus Software License Agreement — see the `LICENSE` file in this folder. The ManusSDK binaries include open-source components; their license texts are provided in the `Third-party notices` folder.
