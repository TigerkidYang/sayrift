# Sayrift 0.2.1

Download the [Windows installer or Android APK](https://github.com/TigerkidYang/sayrift/releases/tag/v0.2.1). This is the first downloadable release; 0.2.0 was a source-only preview.

## Included

- Windows: global shortcuts for dictation, translation and Ask; Glass interface, voice bar, local history with optional audio retry, dictionary, usage and cost views.
- Android: an edge handle alongside your existing keyboard, the same three voice modes, text history, dictionary and setup guidance.
- Your own OpenRouter key. Audio and relevant text/context go to OpenRouter and its selected providers; usage is billed to your account. No offline inference, device sync or account subscription.
- Local-history retention and request-cancellation fixes from the reviewed source preview.

The layered hotword experiment is not included.

## Installation and updates

Windows installation is per user and does not require Python. The EXE is currently **unsigned** and may show a Windows reputation warning. The old local data directory is retained.

The Android APK is an optimized, non-debug release signed with Sayrift's public release identity. Its certificate fingerprint and verification instructions are in [Android signing](../android/signing.md). This certificate differs from earlier personal debug builds, so it cannot directly update those installations. **Do not uninstall an old build to bypass a signature mismatch if you need its data.**

The download page includes SHA-256 checksums and dependency source materials. Windows libraries and the graphical setup can be replaced independently; see [library replacement](windows-library-replacement.md). Sayrift is MIT-licensed; third-party components retain their own licenses.

## Verification and limits

Release builds are checked with offline unit tests, packaging inspection and Android signature verification. See [binary build evidence](binary-release.md) for the precise results. These checks do not replace device tests of microphone access, input fields, accessibility or upgrades.

Windows 11 is the desktop target. Android 10+ is declared, with better input integration on Android 13+. The Android UI is primarily Chinese. Some applications may reject insertion; recover the text from the result card.

History uses local plaintext SQLite storage. Database deletion does not guarantee physical secure erasure. Provider privacy routing is not a zero-retention guarantee, and cancellation cannot undo a provider charge already incurred.

Report problems with non-sensitive sample data; use [private vulnerability reporting](https://github.com/TigerkidYang/sayrift/security/advisories/new) for security findings.

## Earlier release

[0.2.0](https://github.com/TigerkidYang/sayrift/releases/tag/v0.2.0) remains available as the initial reviewed MIT source snapshot, without binaries. Private development history, personal research, local configuration and generated speech fixtures are not part of the public repository.
