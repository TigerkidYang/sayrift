# Sayrift 0.2.0 preview: compatibility and upgrades

[English overview](../README.md) · [中文概览](../README.zh-CN.md) · [Build and test instructions](../CONTRIBUTING.md)

Sayrift is the new public name for local-typeless. The 0.2.0 preview covers Windows and Android. The first publication is an MIT-licensed source preview. It includes no official EXE/APK downloads; binary distribution requires additional dependency and signing verification.

## Platform coverage

| Platform | Scope and limits |
| --- | --- |
| Windows 11 | Working desktop app: Dictate, Translate, Ask, Glass UI, local history with optional audio retry, dictionary, usage and cost views, settings, tray, and installer. Insertion depends on the target app and its privileges. |
| Android 10–12 | Declared minimum is Android 10 (API 29). Text insertion falls back to accessibility text actions; on failure a result card offers explicit copy. Fields hidden from accessibility may not work. The minimum SDK declaration is not evidence of device validation on every supported version. |
| Android 13+ | Best integration: an accessibility input connection can insert text alongside the active keyboard, including some fields whose accessibility tree is unavailable. App-specific limits still apply. |
| Personally tested Android setup | Xiaomi 15, Android 16 / HyperOS 3, Gboard. Recorded checks include WeChat, Xiaohongshu, East Money, ChatGPT, and the app's own fields. This does not establish compatibility with every field, version, keyboard, or phone. |
| iOS, macOS, Linux desktop | No supported app in this preview. |

The Android interface is currently primarily Chinese; Windows offers Chinese and English with dark, light, and system appearance options. Both platforms use cloud models through OpenRouter and require internet access and the user's own key. There is no offline inference or cross-device history/dictionary sync.

### Input behavior

Windows uses global shortcuts and clipboard-based insertion. Elevated windows can block insertion from a normal user process, and custom controls may not accept it. Failed insertion can fall back to a result card. Clipboard restoration is conditional on the clipboard not having been changed by another application.

Android uses an accessibility service for the edge handle, focused-field detection, selection, and insertion; it does not replace your keyboard. The handle is intentionally hidden in password fields. If the focused field changes while a request runs, the result can be shown in a card instead. Ask can only edit a selection the app can read.

On Android, grant microphone permission and follow the notification and accessibility setup. A sideloaded app may require allowing restricted settings before accessibility can be enabled. On Xiaomi / HyperOS, follow the guide's autostart and unrestricted battery steps; a background restriction can stop the service even when its system switch still appears enabled. See the [Android README](../android/README.md) for setup details.

## Names that change, identifiers that stay

The display name and public launch commands change to Sayrift. Existing data and internal identifiers are deliberately retained so a branding change does not create a fresh profile.

| Item | 0.2.0 behavior |
| --- | --- |
| Public desktop commands | `uv run sayrift` and `uv run sayrift-gui`; the latter is the windowless launcher. |
| Legacy source launch aliases | `uv run local-typeless` and `uv run local-typeless-gui` remain compatibility aliases. These are command entry points, not a promise that every old executable path remains present. |
| Windows installer filename | `sayrift-Setup-0.2.0.exe`. |
| Python import/source package | Still `local_typeless`, under `src/local_typeless/`. Do not rewrite imports to `sayrift`. |
| Default Windows data directory | Still `%APPDATA%\local-typeless`, including `config.toml` and `history.sqlite`. No manual folder rename is required. |
| Configuration environment variables | `SAYRIFT_CONFIG` takes precedence over the legacy `LOCAL_TYPELESS_CONFIG`. If neither is set, use `%APPDATA%\local-typeless\config.toml`. |
| Windows model credential | Still `OPENROUTER_API_KEY`, read from the process or Windows user environment. It is not a TOML setting. |
| Android application ID / namespace | Still `app.localtypeless.android`; Kotlin packages, service component IDs, and existing storage identifiers are retained for upgrade continuity. |
| Android model credential | The user's key is entered in the app and encrypted using Android Keystore. The rename does not require a new key. |

An override selects the Windows **configuration file**, and the app uses `history.sqlite` beside that file. Changing the override does not migrate an existing database, so it can make the app show a different history. Prefer `SAYRIFT_CONFIG` for new scripts, and check both variables if settings or history appear to be missing. Existing design documents, diagnostic identifiers, and research files may still say local-typeless.

### Upgrading Windows

Keep the existing data directory. Use the Sayrift installer for an installation upgrade; changing the application name alone should not require exporting or recreating history and settings. Source users should run `uv sync --locked` after updating so the new command entry points are installed.

Old taskbar pins and hand-made shortcuts may still point at the previous launcher. If one stops working or keeps the old name/icon, launch Sayrift from its current shortcut and re-pin it. Update scripts that hard-code an executable path. Compatibility aliases in a source environment do not repair an external taskbar shortcut.

Windows uninstall offers a choice about removing local data. Read that choice carefully if you want to keep history and settings for another installation.

### Upgrading Android

An in-place Android update needs the same application ID, a compatible version code, and **the same signing identity** as the installed app. Retaining `app.localtypeless.android` is only one part of that requirement.

Older personal builds used a debug certificate, including their release variants. New release builds require explicit signing credentials and do not silently use the debug certificate. Debug keystores can differ between machines, so rebuilding elsewhere may produce an APK that cannot update an existing installation. See [signing](../android/signing.md).

Keep the original personal signing certificate/key when continuing that installation. Do not uninstall just to work around a signature mismatch if you need the current history, settings, and encrypted key: uninstalling removes app data and its Keystore material. The first source preview does not publish a production-signed APK.

## Data retained on each device

| Data | Windows | Android |
| --- | --- | --- |
| History | Unencrypted SQLite at `%APPDATA%\local-typeless\history.sqlite` by default, or beside a custom config file; transcripts, results, metadata, and optional audio. Audio is enabled by default for retry. | Unencrypted SQLite in app-private storage (`history.db`); transcripts, results, and metadata. No history audio or audio retry. |
| Temporary audio | Recording is encoded for upload; retained history audio follows the history settings. | Recording writes `dictation.ogg` in the app cache. Normal stop/cancel deletes it after reading or discarding it; a crash or failed cleanup can leave a temporary file. |
| Retention | Configurable period or no history; audio storage can be disabled separately. | Configurable period or no history. |
| Usage and costs | Separate records survive history deletion or disabling history. | Separate records survive history deletion or disabling history. |
| API key | Environment variable; Sayrift does not encrypt the Windows environment. | Saved key encrypted with an Android Keystore key; this does not encrypt the history database. |

Local storage describes where history lives, not where inference happens. Audio, text, and relevant context are sent to OpenRouter and model providers. The default `data_collection = "deny"` flag requests exclusion of data-collecting/training providers; it does not guarantee zero retention. Windows' separate `zdr` option is off by default and can restrict which endpoints are available.

The personal dictionary is included on both platforms. The layered hotword library remains a separate experiment and is not integrated into this preview.

## Build and verification boundaries

Windows development uses Python 3.12 with `uv sync --locked`, followed by pytest and Ruff. Android uses the Gradle wrapper with `core:test app:assembleDebug`; the tested JDK is 21, emitted JVM bytecode targets 17, and compile/target SDK is 35.

Default unit tests use mocks and do not call paid APIs. Passing these checks does not prove compatibility with a phone, keyboard, or target application. Desktop end-to-end tests, live dictation, and model benchmarks are separate checks that can access the microphone, take focus, or call paid APIs. See [CONTRIBUTING.md](../CONTRIBUTING.md) before running them.
