# Sayrift

**Voice input for Windows and Android.** Dictate, translate, or ask for an edit, with your own OpenRouter key.

English · [简体中文](README.zh-CN.md)

![Sayrift Windows home screen with demo data](docs/images/windows-home.png)

**0.2.2** · Formerly local-typeless. Download an installer below, or build from source with your own OpenRouter key.

- [Windows 11 installer](https://github.com/TigerkidYang/sayrift/releases/download/v0.2.2/sayrift-Setup-0.2.2.exe)
- [Android APK](https://github.com/TigerkidYang/sayrift/releases/download/v0.2.2/sayrift-0.2.2-android.apk)
- [Release notes, checksums and dependency sources](https://github.com/TigerkidYang/sayrift/releases/tag/v0.2.2)

Windows builds are currently unsigned. The Android APK is signed with the Sayrift release certificate; it cannot directly replace earlier personal debug-signed installations. Do not uninstall an existing installation just to bypass a signature mismatch; see [upgrade compatibility](docs/compatibility.md).

| Platform | Current status |
| --- | --- |
| Windows 11 | Working desktop app with global shortcuts, a voice bar, and a system tray. |
| Android 10+ | Preview with an edge handle alongside your existing keyboard. Android 13+ has the best text-field integration. Personally tested on Xiaomi 15, Android 16 / HyperOS 3, with Gboard. |

There is no iOS app. macOS and Linux desktop apps are not supported.

## Three ways to use your voice

| Mode | What it does |
| --- | --- |
| **Dictate** | Turns speech into text, cleaning up fillers, spoken corrections, punctuation, and lists. |
| **Translate** | Turns speech into text in your chosen target language. |
| **Ask** | Edits selected text with a spoken instruction, writes text at the cursor, or shows an answer card. Selection editing depends on the target app exposing its selection. |

Both apps include a Glass interface, local history, a personal dictionary for names and terminology, and usage and cost views. Windows also offers audio retry, model-level cost details, and CSV export. Android keeps text history without audio retry. History and dictionaries are separate on each device; there is no sync.

A layered hotword library is being explored separately and is **not included** in this release.

### New in 0.2.2

Dictation now handles long explanations, conditional branches and nested choices more clearly,
while preserving tentative wording, corrections and instructions such as “don't change the code yet.”
The shared Windows/Android prompt was compared with official Typeless outputs and tested on 43
synthetic cases using both text models. See the [release notes](docs/release-notes.md) for results and limits.

## Windows quick start

Download and run the installer, then follow the first-run guide. No Python or terminal is needed for the installed app.

For a source checkout, use Python 3.12 and uv:

```powershell
uv sync --locked
uv run sayrift
```

`uv run sayrift-gui` starts the same app without a console window. To build the installer:

```powershell
uv run python tools/build_installer.py
```

This produces `dist\sayrift-Setup-0.2.2.exe`. Installation is per user and does not require administrator rights.

1. Add your OpenRouter key as the **user environment variable** `OPENROUTER_API_KEY`. Do not put it in a configuration file.
2. Open Sayrift and follow the first-run guide to check the key, microphone, and shortcuts. The guide can re-read the user environment after you add the key.
3. Focus a text field, start a recording, and speak after the recording cue.

| Action | Default shortcut |
| --- | --- |
| Dictate | Tap **Right Alt** to start and again to finish, or hold it while speaking and release to finish. |
| Translate | **Right Alt + Right Shift**. |
| Ask | **Right Alt + Space**. Select text first to request an edit. |
| Finish / cancel | Tap **Right Alt** to finish a toggled recording; **Esc** or **×** cancels it. |

Change shortcuts and translation targets in Settings. Closing the main window leaves Sayrift in the tray; double-click the tray icon to reopen it, or use its menu to quit.

For proxy configuration, use Settings → Advanced. Otherwise, the app checks proxy environment variables and then the Windows system proxy. Some text fields and administrator windows may reject insertion; a result card lets you recover the text. See [compatibility](docs/compatibility.md) for limitations and upgrade notes.

## Android quick start

Download the release APK above. Developers can also follow the [Android build instructions](android/README.md) and [signing guide](android/signing.md).

1. Install the APK and open Sayrift. The current Android interface is primarily Chinese.
2. Enter your own OpenRouter key in the guide. It is encrypted using Android Keystore.
3. Follow the microphone, notification, background-running, and accessibility setup. Accessibility enables the edge handle and text insertion while you keep your usual keyboard. On Xiaomi / HyperOS, allow autostart and unrestricted battery use as directed by the guide.
4. Focus a supported text field and tap the edge handle to record. Tap **✓** to finish or **×** to cancel. Long-press the handle to choose Dictate, Translate, or Ask.

Android 10–12 uses more limited text insertion fallbacks. Behavior depends on the phone, keyboard, and target app; password fields intentionally hide the handle. [Compatibility details](docs/compatibility.md) explain these limits and the signing requirement for upgrades.

## Data and privacy

Sayrift needs an internet connection. **Audio and text are submitted to OpenRouter and the selected model providers** for transcription, cleanup, translation, or Ask. Requests can also include dictionary terms, app context, and selected text when editing.

- **Provider routing:** by default, Sayrift asks OpenRouter to exclude providers that collect data or use it for training (`data_collection = "deny"`). This is not a guarantee of zero retention. Windows also has a separate optional `zdr` setting, disabled by default.
- **Windows:** history is a local, unencrypted SQLite database, by default at `%APPDATA%\local-typeless\history.sqlite`. It includes transcripts and results, plus audio for retry by default. You can choose a retention period, turn off audio storage, or disable history.
- **Android:** history is local, unencrypted SQLite text and metadata; recordings are not saved in history. Recording uses a temporary cache file, deleted on normal stop or cancel. A crash or interrupted cleanup can leave that file behind.
- **Keys:** Windows reads `OPENROUTER_API_KEY` from the environment; Android encrypts the saved key using Keystore. History does not receive the same app-level encryption.
- **Usage:** deleting or disabling history does not remove the separate usage and cost records, which contain metadata rather than transcript text or audio.

Model calls are billed to your OpenRouter account. Cost and response time depend on usage, models, providers, and network conditions. Local cost views use the data reported by the service and may be incomplete.

## Development and project notes

- [Contributing](CONTRIBUTING.md): setup, tests, builds, and change conventions.
- [Compatibility](docs/compatibility.md): platform limits, retained identifiers, and upgrading from local-typeless.
- [Configuration example](config.example.toml) · [Architecture](docs/architecture.md) · [Manual checks](docs/manual-tests.md).

Sayrift is an independent project inspired by Typeless. Some design and research documents still use the former name or describe experiments; they are not a list of shipped features.

**License:** [MIT](LICENSE) for Sayrift code and original assets. Third-party works retain their [own licenses](THIRD_PARTY_NOTICES.md).
