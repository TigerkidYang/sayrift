# Contributing to Sayrift

Sayrift 0.2.1 is a preview for Windows 11 and Android. Read [AGENTS.md](AGENTS.md) before changing the project, and [compatibility](docs/compatibility.md) before changing names, storage, or installation behavior. Sayrift code is licensed under [MIT](LICENSE); third-party materials retain their own terms.

## Working on a change

Start by checking the branch, worktrees, and uncommitted changes. Use a dedicated branch and a separate worktree for an independent change; concurrent contributors must not share a working tree. Preserve unrelated changes and keep commits scoped to one task.

Discuss new behavior against the product specification, distinguish experiments from shipped features, and update the relevant documentation. The layered hotword library is a separate experiment and is not part of the 0.2.0 preview.

## Windows development

Use Windows 11, Python 3.12, and uv. From the repository root:

```powershell
uv sync --locked
uv run sayrift
```

The windowless launcher is `uv run sayrift-gui`. The Python source package remains `local_typeless`; the public name is Sayrift. Put a real key only in the `OPENROUTER_API_KEY` environment variable when deliberately testing live model calls. Unit tests do not need a key.

Run the default checks:

```powershell
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

Pytest excludes tests marked `network` by default. Tests use fake clients or HTTP mocks and must not call paid APIs. Dependency installation may need internet access. Use `uv run ruff format <changed-files>` to format your own changes without rewriting unrelated files.

Build the Windows installer with:

```powershell
uv run python tools/build_installer.py
```

Expected output: `dist\sayrift-Setup-0.2.1.exe`. Building an installer does not publish a release.

## Android development

See the [Android README](android/README.md) for build details and device setup. The tested build environment uses **JDK 21**, with **Java/Kotlin JVM target 17**, **Android SDK 35** for compile/target SDK, and minimum SDK 29 (Android 10). JVM target 17 is not a claim that the tested Gradle process ran on JDK 17.

Set `JAVA_HOME` to your JDK and make the Android SDK available through `ANDROID_HOME` or an untracked `android/local.properties` containing `sdk.dir`. Use the checked-in Gradle wrapper. From the repository root in PowerShell:

```powershell
Set-Location android
.\gradlew.bat core:test app:assembleDebug
```

In a POSIX shell, the equivalent command from `android/` is:

```sh
./gradlew core:test app:assembleDebug
```

The debug APK is `android/app/build/outputs/apk/debug/app-debug.apk` relative to the repository root. `core:test` uses a local mock HTTP server and does not call OpenRouter. The build may download Gradle and dependencies; it does not install an APK on a phone.

The `release` build requires explicit signing credentials and never falls back to debug signing. See [Android signing](android/signing.md). Upgrading an existing installation requires its original signing identity. Never commit a signing key or credentials.

The Android `core` module copies the shared prompts from `src/local_typeless/prompts/` during the build. Test both platforms when changing those prompts or their contract.

## Implementation and validation

- Keep Python modules small and typed; follow the Ruff configuration. Isolate Win32 calls under `src/local_typeless/win/` and keep the pipeline independent of the UI.
- Only the Qt main thread may update widgets. Keyboard-hook callbacks must return promptly; network work belongs off the UI thread.
- Add focused regression tests for behavior changes. Document manual checks and their actual results; distinguish a build passing from a real device or app passing.
- For prompt changes, add a reproducing evaluation case first. Follow the repository's evaluation process with three runs each for the primary and fallback models, and record results with the change. Model defaults also require benchmark evidence.
- Benchmarks and desktop end-to-end tools can call paid APIs. They are separate from the default test suite. Choose models and repetitions deliberately, keep concurrency at six or below, and only run live checks within the authorized task scope.
- Desktop end-to-end tests can take focus and use the real clipboard. Coordinate before running them while someone is typing; preserve and restore the clipboard. Follow [the manual test checklist](docs/manual-tests.md) for real applications and input methods.

For documentation-only work, check factual claims, relative links, command syntax, and English/Chinese parity. Do not run live dictation just to validate prose.

## Data and review

Keep API keys, personal configuration, recordings, history databases, and signing material out of commits, logs, screenshots, and fixtures. Use synthetic text and demo data. Redact diagnostic material before sharing it.

The public snapshot does not include generated speech recordings. Use your own recordings as described in [evaluation instructions](evals/README.md), and keep them outside Git. Record provenance and permissions before proposing any shared audio fixtures.

Describe the problem, the resulting behavior, and the validation in the change summary. Include platform, Android version and keyboard where relevant, and any checks you could not perform. Write commit messages in English with a `Co-Authored-By` trailer for an actual co-author, as required by the repository. Do not push or publish without authorization.

Useful references: [configuration](config.example.toml), [architecture](docs/architecture.md), [product specification](docs/product-spec.md), [model evaluations](docs/models.md), and [evaluation rules](evals/README.md). Historical documents may contain earlier names, plans, or measurements; avoid presenting them as current compatibility or performance guarantees.
