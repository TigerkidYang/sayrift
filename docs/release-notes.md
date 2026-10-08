# Sayrift 0.2.2

2026-10-08 · Regular release for Windows 11 and Android. Download the
[Windows installer or Android APK](https://github.com/TigerkidYang/sayrift/releases/tag/v0.2.2).

## What's improved

- Long dictation separates background, examples and the speaker's intended outcome into paragraphs.
- Mutually exclusive actions become readable branches; explicitly enumerated sub-options retain their parent/child structure.
- Informal lists and spoken restarts are cleaned up more consistently, without changing choosing into writing or assessing into implementing.
- Questions, tentative wording, conditions and closing restrictions remain part of the dictated message. Requests are transcribed, not executed.
- Chinese script handling, note lists and contextual homophone cleanup are more consistent.

These changes include all prompt improvements since 0.2.1 and apply to both platforms. Default models,
hotkeys, storage locations, app identity and history formats are unchanged. No new account or setup is required
when upgrading an existing configured public release.

## Upgrade

Exit Sayrift, then run the Windows installer over the existing installation. Keep the existing data directory.
The Windows EXE remains unsigned. Android uses the same public release certificate as 0.2.1 and increases
versionCode from 3 to 4, so install the APK over public 0.2.1 without uninstalling. Earlier personal debug
builds have a different signing identity; see [compatibility](compatibility.md).

## Evaluation and remaining limits

The final shared prompt passed **129/129 checks on each text model**: 43 synthetic inputs repeated three
times. The latest eight official-client audio comparisons cover short instructions, explanations, branches
and nested choices. Sayrift's final audio pipeline satisfied seven of those eight cases; one short `PR`
was recognized as `P2`. Quotation marks and the placement of a sub-option's caveat also remain variable.
These are bounded observations, not a claim of perfect Typeless equivalence.

See the [comparison report](typeless-history-comparison-2026-10-08.md),
[paired outputs](../evals/polish/typeless-2026-10-08.json) and [binary verification](release-0.2.2.md).
Private history, generated audio and credentials are not included in the release.

## Earlier: Sayrift 0.2.1

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
