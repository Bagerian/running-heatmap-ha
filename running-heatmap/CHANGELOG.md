# Changelog

## [1.0.14] - 2026-07-05

### Added
- Added an option in the Activity Admin to directly upload Strava data (ZIP export or activities.csv).

### Fixed
- The Activity Admin page no longer throws a file not found error if the Strava `activities.csv` is missing. The UI now gracefully loads even without Strava data.

---

## [1.0.13] - 2026-07-04

### Fixed
- Fixed 404 error on the Activity Admin page. The file `serve.py` now correctly handles API routes and the admin portal.

