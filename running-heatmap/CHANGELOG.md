# Changelog

## [1.0.4] - 2026-06-25

### Fixed
- Admin panel button on the heatmap now works correctly through Home Assistant's
  ingress proxy (previously opened a 404 page). The server now reads the
  `X-Ingress-Path` header and injects a `<base>` tag so all links resolve to
  the correct URL regardless of how HA routes the request.
- All API calls in the admin UI now use relative URLs, making them ingress-safe.

---

## [1.0.3] - 2026-06-25

### Added
- **⚙ Activity Admin** button at the bottom of the layer panel on the heatmap
  page, linking directly to the admin UI without needing to change the URL.

---

## [1.0.2] - 2026-06-25

### Changed
- Admin UI moved from port 8001 to the same port 8000 as the heatmap viewer,
  accessible at `/admin`. This makes it reachable through Home Assistant's
  ingress panel without needing to open a separate port.
- Removed the separate admin server process; both UIs are now served by a
  single server.

---

## [1.0.1] - 2026-06-25

### Fixed
- Removed deprecated `build.yaml` file; build parameters are now specified
  directly in the `Dockerfile` as recommended by Home Assistant.
- Removed deprecated `armhf` and `armv7` architecture values from `config.yaml`.
- Fixed base Docker image name (`ghcr.io/home-assistant/base-python:3.13-alpine3.23`).

---

## [1.0.0] - 2026-06-25

### Added
- Initial release of the Running Heatmap Home Assistant add-on.
- Interactive heatmap viewer with 11 layer types (frequency, pace, heart rate,
  elevation, recency, and more) and 5 switchable basemaps.
- Support for Strava bulk export and intervals.icu activity sync.
- Activity admin UI to exclude/include specific activities and re-import
  missing intervals.icu activities.
- **⟳ Sync all from intervals.icu** button to fetch full activity history
  (fixes missing activities from before the first sync).
- Persistent data storage under `/share/running_heatmap/`.
- Home Assistant ingress support (heatmap accessible directly in the HA sidebar).

---

## [1.0.5] - 2026-06-27

### Fixed
- **Admin panel now lists activities** — config was not being passed correctly
  to the admin server; it now loads directly from the generated config file.
- **Sync no longer requires a restart** — added a ▶ Regenerate heatmap button
  in the admin panel that rebuilds the heatmap tiles in the background without
  restarting the add-on. A progress bar shows while it runs.
- **Explained GPS-less activity gap** — activities without GPS data (indoor
  runs, treadmill, gym workouts) are downloaded to the cache but cannot be
  drawn on the map. The activity count difference between "downloaded" and
  "shown on map" is normal and expected. The admin panel now shows a GPS
  column so you can see which activities have no location data.

### Changed
- Admin panel redesigned with clearer action buttons, better status messages,
  and a hint bar explaining the sync → regenerate workflow.
- Sync success message now says "click Regenerate heatmap" instead of
  "restart the add-on".

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
