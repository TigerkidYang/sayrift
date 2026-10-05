# Sayrift 0.2.0 — source preview

Sayrift is a voice dictation, translation and voice-editing app for Windows and Android.
This first public release contains source code under the [MIT license](../LICENSE).
Third-party works retain their own licenses; see [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md).

## Scope

- Windows: Glass interface, global shortcuts, local history and optional audio retry, dictionary, usage and costs.
- Android: edge handle alongside your existing keyboard, three voice modes, text history, dictionary and setup guidance.
- Own OpenRouter key; no account, subscription, offline inference or device sync.
- The layered hotword-library experiment is not included.

The public repository starts from a reviewed source snapshot. Earlier private development history,
personal research, local paths and generated speech fixtures are not published. Evaluation text and
offline unit tests remain available. See [evaluation instructions](../evals/README.md) to use your own recordings.

## Building and distribution

Windows and Android debug build instructions are in the READMEs. These are developer builds.
No official EXE or APK is attached to this source preview. Before distributing binaries, complete the
corresponding-source, dependency-notice and library-replacement checklist in the third-party notices.
Android release builds require explicit signing credentials; see [signing](../android/signing.md).
Keep signing keys outside Git. Debug and production certificates are different upgrade identities.

## Limits

- Preview software: app-specific insertion and accessibility behavior need broader device testing.
- Windows 11 is the desktop target. Android 10+ is declared; Android 13+ has better input integration.
- Android clipboard fallback is subject to system restrictions; no physical secure-erasure guarantee is made.
- Costs may be incurred before a cancelled request reaches its provider; local cancellation cannot undo billing.
- History is local plaintext SQLite storage. Provider privacy filtering is not a blanket zero-retention guarantee.
- Source publication is not a claim that every earlier private test or experimental feature is reproducible here.

Report issues using non-sensitive sample text. See [security and privacy](../SECURITY.md).
