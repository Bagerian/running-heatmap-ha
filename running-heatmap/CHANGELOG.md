# Changelog

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
