# Windows v0.3.13 text search extension

This is an additive patch for the exact archived Windows v0.3.12 ZIP. It does not rebuild MiniCAD.exe or replace the original UI with the older web app. Original executable, backend, native DWG engine, original CSS and all other packaged files remain byte-identical. Only the frontend entry module, HTML and build metadata are modified; a search module, stylesheet and usage note are added.

The integration uses original visible entities (including nested blocks), the original camera commit function and original selection renderer. Ctrl+F/Cmd+F opens search; typing locates the first matching text object; Enter/Shift+Enter and buttons cycle through matching objects; Escape closes search. Hidden layers are excluded. Korean, case-insensitive Latin text, Unicode normalization and CAD Unicode escapes are supported. Text inside a block is centered individually and its containing block is selected. Editing, deleting, printing and measurement implementations are unchanged.

Build from the exact archived baseline:

```sh
python windows-patches/text-search/build.py /path/to/MiniCAD-Windows-x64-v0.3.12.zip /path/to/MiniCAD-Windows-x64-v0.3.13.zip
```

The builder rejects an unexpected baseline hash, checks ZIP CRCs, checks its integration anchor, and verifies the only changed original entries are the expected three. It also emits a SHA-256 sidecar. The resulting package is a complete Windows distribution; users must extract all files into a new directory and run MiniCAD.exe.

Validation: `browser_test.py <extracted _internal/frontend/dist>` runs the actual patched frontend in Chromium against a controlled drawing API. It covers Ctrl+F focus, Korean/English text, nested blocks, hidden layers, camera movement, previous/next/wrap, empty/no-match states, close/reopen, Unicode, and presence of the original Windows controls. No JavaScript errors were observed. This does not replace native Windows WebView2 testing; the native executable and printer were not run in this environment. Inherited v0.3.12 engine checks in build-info.json are historical, not newly executed checks.
