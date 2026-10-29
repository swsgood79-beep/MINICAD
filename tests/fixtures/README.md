# DWG compatibility fixtures

Unmodified public sample_2000.dwg and sample_2018.dwg from GNU LibreDWG test/test-data, source revision `527592392c300bf058d2ed547206ab4960df624a`. Source: https://github.com/LibreDWG/libredwg/tree/527592392c300bf058d2ed547206ab4960df624a/test/test-data

COPYING contains the upstream GNU GPL v3 license. sample_expected.json is derived from upstream sample_2018.dxf and describes the known 100 mm horizontal line and radius 20 mm circle for numeric comparisons. No customer files are included.

`sample_database.json` is the same public 2018 fixture read with @mlightcad/libredwg-web 0.8.2's direct database API. Layer locks are corrected by handle against the raw `locked` bit; upstream's misspelled `plotflockedlag` access reports undefined as locked. This fixture validates fallback coordinates/units/closed polylines without assuming the customer's unavailable DWG file has been fixed.
