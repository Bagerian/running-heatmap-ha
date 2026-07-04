# Changelog

## [1.0.13] - 2026-07-04

### Fixed
- Fixed 404 error on the Activity Admin page. The file `serve.py` now correctly handles API routes and the admin portal.

---

## [1.0.6] - 2026-06-27

### Fixed
- **Admin panel HTTP 500 resolved** — the previous fix attempted to load config
  by importing `main_ha.py`, but that file runs the full heatmap generator when
  imported, causing it to crash and return 500. Config is now built directly
  from environment variables (`HEATMAP_STRAVA_DIR`, `HEATMAP_ICU_CACHE_DIR`)
  that are set by `run.sh` at startup — no file import needed.

---

## [1.0.12] - 2026-06-27

### Fixed
- **Add-on crashed on startup ("not progressing further")** — confirmed via logs
  that the sync and yearly-chunk fetching both worked correctly, but Home
  Assistant kills the add-on if its web server doesn't respond within roughly
  a minute of startup. Tile rendering alone takes 10-20+ minutes for 150+
  activities, so the add-on was always killed mid-render before the server
  even started.
- The web server now starts **immediately** on add-on startup (satisfying
  HA's health check), and intervals.icu sync + tile rendering now run in a
  background subprocess after the server is already up. A "Generating your
  heatmap…" placeholder page with auto-refresh is shown until the first
  render completes.
