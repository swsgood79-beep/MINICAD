# MiniCAD release baseline

The user's current product is MiniCAD Windows x64 v0.3.12, supplied as a split ZIP on 2026-11-02. It is archived as the GitHub release `v0.3.12`.

- Preserve existing Windows v0.3.12 features when making changes.
- The web app source in this repository is an older, different baseline. Do not substitute it for the Windows UI or ship it as an updated Windows release.
- The v0.3.12 archive contains executables and compiled frontend assets, not the original application source. Do not claim the repository source reproduces it. Verify source compatibility against the archived build metadata before rebuilding.
- For future completed Windows changes, the user requests GitHub updates and a downloadable ZIP in the conversation. Publish versioned Windows assets through GitHub Releases with checksums; provide download links in chat. Do not interpret Windows upload requests as GitHub Pages deployment.
- Preserve the v0.3.12 release as a baseline; use a new version for modified releases.

The v0.3.13 update is an authorized additive patch of the compiled v0.3.12 frontend, not a rebuild from missing original sources. Its maintainable extension and verified-baseline packaging script live in windows-patches/text-search. Preserve that route for compatible frontend updates; obtain matching original source for backend changes.
