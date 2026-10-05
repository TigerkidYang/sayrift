#!/usr/bin/env bash
# Emulator helpers for the Android app (Git Bash on Windows).
#
#   tools/android_emu.sh boot       start the headless emulator (AVD "lt35") and wait for it. Run it as a
#                                    background task: the emulator dies with the shell that started it.
#   tools/android_emu.sh install    build, then reinstall safely and set up for testing:
#                                    mock OpenRouter via files/dev.json, test audio, permissions, accessibility
#   tools/android_emu.sh shot NAME  screenshot to $SHOTS/NAME.png
#   tools/android_emu.sh phone      build the release APK (R8, ~2.5 MB) and install it on the USB-connected phone,
#                                    keeping its data (key, history); no test config is written
#
# The emulator (35.x, -no-window) crashes when an app is reinstalled while its accessibility overlay is
# attached, so "install" switches the service off first. The mock server: tools/android_mock_openrouter.py.
set -euo pipefail
export MSYS_NO_PATHCONV=1
SDK="${ANDROID_HOME:-${ANDROID_SDK_ROOT:-${LOCALAPPDATA:-$HOME}/Android/Sdk}}"
ADB="${ADB:-$SDK/platform-tools/adb.exe}"
P=app.localtypeless.android
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SHOTS="${SHOTS:-$ROOT/android/build/shots}"
GRADLE_TMP="${SAYRIFT_BUILD_TMP:-$HOME/.gradle/sayrift-tmp}"
mkdir -p "$GRADLE_TMP"
GRADLE_TMP="$(cygpath -w "$GRADLE_TMP")"
# Emulator commands must never fall back to a connected physical phone.
EMU=("$ADB" -e)

case "${1:-}" in
boot)
  export ANDROID_HOME="$(cygpath -w "$SDK")" ANDROID_SDK_ROOT="$(cygpath -w "$SDK")"
  "$SDK/emulator/emulator.exe" -avd lt35 -no-window -no-audio -no-snapshot -no-boot-anim -gpu swangle_indirect \
    -memory 3072 >"${TMP:-/tmp}/emulator.log" 2>&1 &
  "${EMU[@]}" wait-for-device
  until [ "$("${EMU[@]}" shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')" = "1" ]; do sleep 2; done
  echo "booted"
  ;;
install)
  TEST_AUDIO="${SAYRIFT_TEST_AUDIO:-$ROOT/evals/asr/audio/zh_disfluent.ogg}"
  if [ ! -f "$TEST_AUDIO" ]; then
    echo "Set SAYRIFT_TEST_AUDIO to your own OGG/Opus clip; see evals/README.md. No device changes made." >&2
    exit 2
  fi
  (cd "$ROOT/android" && TEMP="$GRADLE_TMP" TMP="$GRADLE_TMP" ./gradlew :app:assembleDebug -q)
  services="$("${EMU[@]}" shell settings get secure enabled_accessibility_services | tr -d '\r')"
  others=""
  IFS=: read -ra components <<< "$services"
  for component in "${components[@]}"; do
    case "$component" in
      ""|null|"$P/"*) ;;
      *) others="${others:+$others:}$component" ;;
    esac
  done
  if [ -n "$others" ]; then
    "${EMU[@]}" shell settings put secure enabled_accessibility_services "$others"
  else
    "${EMU[@]}" shell settings delete secure enabled_accessibility_services >/dev/null
  fi
  sleep 1
  "${EMU[@]}" install -r "$(cygpath -w "$ROOT/android/app/build/outputs/apk/debug/app-debug.apk")" | tail -1
  mkdir -p "$ROOT/android/build"
  echo '{"api_base": "http://10.0.2.2:8765/api/v1", "api_key": "test-key", "use_test_audio": true}' >"$ROOT/android/build/dev.json"
  "${EMU[@]}" push "$(cygpath -w "$ROOT/android/build/dev.json")" /data/local/tmp/dev.json >/dev/null
  "${EMU[@]}" push "$(cygpath -w "$TEST_AUDIO")" /data/local/tmp/test-audio.ogg >/dev/null
  "${EMU[@]}" shell "run-as $P mkdir -p files && run-as $P cp /data/local/tmp/dev.json files/ && run-as $P cp /data/local/tmp/test-audio.ogg files/"
  "${EMU[@]}" shell pm grant $P android.permission.RECORD_AUDIO
  "${EMU[@]}" shell pm grant $P android.permission.POST_NOTIFICATIONS
  "${EMU[@]}" shell settings put secure enabled_accessibility_services "${others:+$others:}$P/$P.VoiceAccessibilityService"
  "${EMU[@]}" shell settings put secure accessibility_enabled 1
  echo "installed and set up"
  ;;
phone)
  (cd "$ROOT/android" && TEMP="$GRADLE_TMP" TMP="$GRADLE_TMP" ./gradlew :app:assembleRelease -q)
  "$ADB" -d install -r "$(cygpath -w "$ROOT/android/app/build/outputs/apk/release/app-release.apk")" | tail -1
  echo "installed on the phone (confirm on the phone if HyperOS asks)"
  ;;
shot)
  mkdir -p "$SHOTS"
  "${EMU[@]}" exec-out screencap -p >"$SHOTS/${2:-shot}.png"
  echo "$SHOTS/${2:-shot}.png"
  ;;
*)
  sed -n '2,14p' "$0"
  exit 1
  ;;
esac
