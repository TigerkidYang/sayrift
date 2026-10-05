# Security and privacy

Sayrift handles microphone audio, dictated text, optional selected text, and a user's OpenRouter key. Audio and request context are sent to OpenRouter and its selected providers. Local storage does not make inference offline.

## Reporting

Do not post API keys, personal recordings, database files, or unredacted logs in public issues. Use GitHub's private vulnerability reporting when it is available on the published repository. If no private channel is available, ask the maintainer for one without including the vulnerability details or personal data.

Include the affected version, platform, a minimal reproduction using synthetic content, and expected versus observed behavior. There is no promised response time during the preview stage.

## Current boundaries

- Windows reads the API key from the user environment; Android stores it encrypted using Android Keystore. Neither design protects against a compromised device or another process running with sufficient access.
- History is local SQLite storage, not an encrypted vault. Windows may store the original audio for retry; disable audio/history storage when appropriate.
- Deleting a history entry removes it from the application's normal view. Secure erasure from database free pages, backups and storage devices is not guaranteed.
- OpenRouter's default privacy routing is not a blanket guarantee of zero retention. Provider/account policies still apply.
- Android normally inserts through the accessibility input connection on Android 13+. When direct insertion fails, a result card offers an explicit sensitive-marked copy action; automatic clipboard replacement is not used. The service requires broad system permission to integrate with other apps.
- Debug builds can use mock endpoints and synthetic audio. Distribute reviewed release builds, and never commit a key or development device configuration.

Preview limits are tracked in [the release notes](docs/release-notes.md).
