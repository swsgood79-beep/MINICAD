# v0.3.13 validation

- All ZIP entries pass CRC verification.
- MiniCAD.exe and original backend/runtime/DWG engine files are byte-identical to v0.3.12.
- Changed original entries: frontend entry JavaScript, frontend index.html, build-info.json. Search JavaScript, CSS and usage notes are added.
- Actual packaged frontend passes Chromium checks with a controlled drawing fixture: Ctrl+F, focus, Korean/English, nested blocks, hidden-layer exclusion, camera movement, next/previous/wrap, empty/no results, closing/reopening, Unicode normalization and CAD escapes.
- Original OFFSET, performance settings, small-text settings and print settings remain present; OFFSET keyboard cancellation still works.
- No JavaScript runtime errors during the browser check.
- Native Windows WebView2 execution and physical printer behavior were not tested here.
