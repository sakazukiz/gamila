# Android Port Audit — NFS Underground 2

Audit date: 2026-10-31  
Branch: `build/android-arm64-fix`

## Scope

This audit covers the Android packaging and launch adapter, SDL/native entry path, Xbox guest-memory layout, and the CI environment used to build and smoke-test the app. It does **not** certify gameplay, graphics fidelity, audio, controller behavior, or performance on the Poco X7 Pro; those require the original game data and a test on the physical device.

## Runtime path

1. Gradle builds the Android application and invokes the root CMake project with the Android NDK.
2. The Android build adds the SDL2 source tree from `third_party/SDL` and builds the game runtime as `libmain.so`.
3. `LauncherActivity` opens the Android Storage Access Framework folder picker. The chosen folder must directly contain `default.xbe`; the importer copies the selected tree into the app-private `files/game` directory.
4. `START GAME` starts the private `org.libsdl.app.SDLActivity`. SDL loads `libmain.so` and invokes `SDL_main`.
5. `game_main` resolves `$filesDir/game/default.xbe`, loads the XBE, calls `xbox_MemoryLayoutInit`, initializes the kernel bridge and devices, then calls the XBE entry point.

The CI-only native smoke path uses an explicit launcher intent extra to enter the same private SDL activity from inside the app. The normal release/start-game flow does not require an exported SDL activity.

## Environment and dependencies

The GitHub Actions environment is explicitly provisioned with:

- Ubuntu 24.04 host
- Temurin JDK 17
- Gradle 8.9
- Android platform 35 and Build Tools 35.0.0
- Android NDK 27.3.13750724
- CMake 3.22.1 and Ninja
- Host regression dependencies: `libsdl2-dev` and `libepoxy-dev`
- Python 3 and `patch` to apply the tracked source patch to the reassembled source archive

The Android APK is built with `arm64-v8a` for the target device and `x86_64` for the emulator smoke test. The latter is a CI test ABI, not a replacement for ARM64.

## Memory-layout findings and changes

The Android crash log provided for this project shows a SIGSEGV at native PC `0x011BCE88`, in `sub_0021C52A+248`. Disassembly of the matching build identifies the faulting instruction as a load through the guest-memory base at guest VA `0x8001003C`. That is the `e_lfanew` field in the synthetic Xbox kernel PE header at `0x80010000`.

The log does not contain the fault address or register state needed to prove which pointer/range was invalid. Therefore, a failed contiguous mapping is a credible failure path, not a proven sole root cause.

The runtime hardening patch changes that path from best-effort to fail-fast:

- Reserve a single host virtual-address span large enough for the guest RAM mirrors and fixed Xbox apertures before SDL/runtime allocations can claim those addresses.
- Carve exact guest-VA ranges out of that reservation and require fixed mappings for the contiguous physical window, NV2A, MCPX, flash, and tiled surface aperture.
- Remove the one-page fake-kernel fallback that could let initialization continue while the rest of the contiguous window remained unmapped.
- Construct and read back the fake MZ/PE header and its `e_lfanew`/section-count fields before guest execution.
- Verify tiled/contiguous aliasing by writing through one view and reading through the other.
- Retain NV2A worker handles, request shutdown, and join workers before releasing their memory.
- Emit Android logcat markers for SDL entry, game-data resolution, each critical mapping, fake-kernel-header validation, and final memory-layout readiness.

## Automated checks

The CI workflow now has independent stages for:

1. Source archive integrity and deterministic Android integration patches.
2. Host POSIX memory-layout regression tests.
3. Android NDK/Gradle APK build.
4. APK ABI/library/package verification.
5. Android API 35 emulator install and launcher-to-SDL native smoke test.

The memory-layout regression checks the synthetic XBE, the fake kernel PE header at `0x8001003C`, all critical apertures, tiled/contiguous aliasing, every configured RAM mirror, extended guest VMA reservation, and shutdown/reinitialization.

The host regression is compiled on Linux with Android-specific source conditionals enabled and a test-only stub for Android logging. It exercises the POSIX mapping implementation; it is not a substitute for a full NDK/ARM64 run. The APK build and emulator smoke test separately exercise the Android Gradle/NDK toolchain and runtime loader.

## Limits of CI evidence

The public CI job intentionally does not contain proprietary NFSU2 disc data. Without the user's extracted game directory, CI can confirm the expected `GAME_DATA_MISSING` guard but cannot run the original XBE through the intro, menus, career, or races.

The x86_64 Android emulator uses SwiftShader. It can validate application lifecycle and native loading, but cannot establish Mali/Dimensity rendering correctness, controller mapping, audio, frame pacing, or thermal behavior on the Poco X7 Pro.

A successful CI run therefore means **build + memory regression + Android native startup smoke passed**. It does not mean the game is fully playable. The remaining proof is an ARM64 run on the target phone with the complete game data, followed by analysis of the new logcat markers if the guest still faults.
