# Windows releases

The baseline is the user-supplied MiniCAD-Windows-x64-v0.3.12 package. The complete single-volume ZIP and its SHA-256 checksum are tracked on the windows-v0.3.12-baseline branch under releases/windows/v0.3.12. The v0.3.12 GitHub Release links to them. Release-asset upload failed with HTTP 401; repository upload is available.

The uploaded .z01, .z02 and .zip volumes were combined. Filename encoding metadata was normalized when repacking; all file contents passed CRC verification. The executable and frontend SHA-256 values match the supplied build-info.json. This verification does not establish native Windows runtime behavior.

The package contains MiniCAD.exe, its runtime, bundled DWG engine, compiled frontend, licenses and instructions. It does not contain the editable application source. The release tag records archival metadata, not a reproducible v0.3.12 source tree. Existing web sources are not the Windows v0.3.12 baseline.

Future updates must preserve this release, use a new Windows version, and include a ZIP and checksum in GitHub Releases and download links in chat. Obtain matching source before rebuilding; do not replace the packaged UI with the older web frontend.
