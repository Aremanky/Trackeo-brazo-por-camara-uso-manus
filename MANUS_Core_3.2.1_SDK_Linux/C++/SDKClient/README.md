# MANUS SDKClient

An interactive terminal client for the MANUS SDK: explore everything MANUS
Core offers - devices, users, skeletons, trackers, gestures, ergonomics,
calibration, licensing, timecode - and use the source as a reference for your
own integration.

## Where do I find how to do X?

Everything you need to learn the MANUS SDK is in **`sdk/`** - plain C++
modules with no UI code, written to be copied into your own project:

| Module | Shows how to |
|---|---|
| `sdk/Calibration` | run the glove calibration steps, save/load .mcal calibration files |
| `sdk/Connection` | initialize the SDK (integrated/local/remote), set a coordinate system, scan for and connect to MANUS Core |
| `sdk/Devices` | vibrate glove fingers (haptics), pair/unpair gloves - including to a specific dongle |
| `sdk/ErrorCodes` | turn `SDKReturnCode` values into readable text |
| `sdk/Firmware` | request a dongle/glove firmware update |
| `sdk/LandscapeCache` | receive the landscape stream (devices, users, trackers, timecode, gestures) |
| `sdk/License` | apply a .lic file to a dongle, retrieve the newest license online |
| `sdk/SkeletonsRetargeted` | build a skeleton setup (nodes + chains), load it, receive animated skeletons |
| `sdk/SkeletonsTemporary` | share skeleton setups with DevTools, save/load .mskl files |
| `sdk/SkeletonsRaw` | receive per-glove raw hand data, wrist motion source, pinch/casing compensation |
| `sdk/Streams` | receive the SDK log, gesture, ergonomics and raw-device-data streams |
| `sdk/Timecode` | interpret Core's timecode state (frame rates, Genlock) |
| `sdk/Trackers` | receive live tracker poses, assign trackers & roles, offsets, timeouts, tracking-system settings, send (test) tracker data into Core |
| `sdk/Users` | create/rename/remove users, assign dongles & gloves, auto-assignment |

`ui/` (FTXUI screens) and `app/` (shell) never call the SDK directly - a build
step (`cmake/CheckLayers.cmake`) enforces this, so the `sdk/` modules stay
self-contained.

## Build

Requires CMake ≥ 3.16 and a C++17 compiler (MSVC on Windows, GCC/Clang on Linux).

From inside this folder:

```
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build --config Release
```

The MANUS SDK headers and binaries are taken from the platform SDK folders;
override with `-DMANUS_SDK_DIR=...` if needed.

On Linux the build targets both amd64 and aarch64: CMake picks
`lib/<arch>/libManusSDK-<arch>.so` for the target processor. The SDK library
needs these runtime packages (Ubuntu names):
`libzmq5 libcurl4 libusb-1.0-0 libudev1 libgomp1 zlib1g`
and `LD_LIBRARY_PATH` (or an rpath) pointing at the SDK's `lib/<arch>` folder.

## Run

- `SDKClient` - the interactive client: pick a connection mode
  (integrated/local/remote), then navigate the screens from the menu.

Terminals: any ANSI/VT-capable terminal (Windows Terminal, conhost on
Windows 10+, common Linux terminals).

## Third-party

- `third_party/ftxui` - [FTXUI](https://github.com/ArthurSonzogni/FTXUI)
  **v6.1.9** (MIT license), vendored unmodified apart from removing
  `.git`/`.github`. To update: replace the folder with a fresh release
  checkout and update the version here and in `CMakeLists.txt`.
