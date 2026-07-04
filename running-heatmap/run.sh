#!/usr/bin/with-contenv bashio

# ─── Read options from Home Assistant ───────────────────────────────────────
INTERVALS_ICU_API_KEY=$(bashio::config 'intervals_icu_api_key' 2>/dev/null || echo "")
INTERVALS_ICU_ATHLETE_ID=$(bashio::config 'intervals_icu_athlete_id' 2>/dev/null || echo "")
STADIA_API_KEY=$(bashio::config 'stadia_api_key' 2>/dev/null || echo "")
HOME_LAT=$(bashio::config 'home_lat' 2>/dev/null || echo "0.0")
HOME_LON=$(bashio::config 'home_lon' 2>/dev/null || echo "0.0")
RADIUS_KM=$(bashio::config 'radius_km' 2>/dev/null || echo "0")

export INTERVALS_ICU_API_KEY="${INTERVALS_ICU_API_KEY}"
export INTERVALS_ICU_ATHLETE_ID="${INTERVALS_ICU_ATHLETE_ID}"
export STADIA_API_KEY="${STADIA_API_KEY}"

# ─── Set up persistent data directories ─────────────────────────────────────
DATA_DIR="/share/running_heatmap"
STRAVA_DIR="${DATA_DIR}/strava_export"
CACHE_DIR="${DATA_DIR}/cache"
OUTPUT_DIR="${DATA_DIR}/outputs"

export HEATMAP_OUTPUT_DIR="${OUTPUT_DIR}"
export HEATMAP_CACHE_DIR="${CACHE_DIR}"
export HEATMAP_STRAVA_DIR="${STRAVA_DIR}"
export HEATMAP_ICU_CACHE_DIR="${CACHE_DIR}/intervals_icu"
export HEATMAP_MAIN_PY="/app/main_ha.py"
export HEATMAP_YES=1

mkdir -p "${STRAVA_DIR}" "${CACHE_DIR}" "${OUTPUT_DIR}"

bashio::log.info "=========================================="
bashio::log.info " Running Heatmap Add-on"
bashio::log.info "=========================================="
bashio::log.info "Strava export : ${STRAVA_DIR}"
bashio::log.info "Cache         : ${CACHE_DIR}"
bashio::log.info "Output        : ${OUTPUT_DIR}"

# ─── Generate main_ha.py ────────────────────────────────────────────────────
HOME_LINES=""
RADIUS_LINE=""

if [ -n "${HOME_LAT}" ] && [ "${HOME_LAT}" != "0.0" ] && \
   [ -n "${HOME_LON}" ] && [ "${HOME_LON}" != "0.0" ]; then
    HOME_LINES="    home_lat=${HOME_LAT},
    home_lon=${HOME_LON},"
fi

if [ -n "${RADIUS_KM}" ] && [ "${RADIUS_KM}" != "0" ]; then
    RADIUS_LINE="    radius_km=${RADIUS_KM},"
fi

cat > /app/main_ha.py << PYEOF
import logging
from heatmap import configure_logging, run
from heatmap.config import ActivityType, Config

config = Config(
    activities_dir="${STRAVA_DIR}",
    intervals_icu_cache_dir="${CACHE_DIR}/intervals_icu",
    activity_type_profiles={
        "runs":       [ActivityType.RUN],
        "trail_runs": [ActivityType.TRAIL_RUN],
        "hikes":      [ActivityType.HIKE],
        "all":        [ActivityType.RUN, ActivityType.TRAIL_RUN, ActivityType.HIKE],
    },
${HOME_LINES}
${RADIUS_LINE}
)

if __name__ == "__main__":
    configure_logging(level=logging.INFO)
    run(config)
PYEOF

bashio::log.info "Config written to /app/main_ha.py"

# ─── Create placeholder page if no heatmap exists yet ───────────────────────
if [ ! -f "${OUTPUT_DIR}/heatmap.html" ]; then
    bashio::log.info "No heatmap yet — creating placeholder page"
    cat > "${OUTPUT_DIR}/heatmap.html" << 'HTMLEOF'
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Running Heatmap – Generating…</title>
<meta http-equiv="refresh" content="30">
<style>
  body { font-family: -apple-system, sans-serif; max-width: 600px; margin: 80px auto;
         padding: 20px; background: #1a1a2e; color: #eee; line-height: 1.7; text-align: center; }
  h1 { color: #e94560; }
  .spinner { font-size: 48px; animation: spin 2s linear infinite; display: inline-block; }
  @keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
  p { color: #aaa; }
  code { background: #16213e; padding: 2px 8px; border-radius: 4px; color: #7df; }
</style>
</head>
<body>
<div class="spinner">🗺️</div>
<h1>Generating your heatmap…</h1>
<p>This page will refresh automatically every 30 seconds.<br>
Tile rendering takes <strong>10–20 minutes</strong> on first run — please be patient.</p>
<p>You can watch progress in the add-on <strong>Log</strong> tab in Home Assistant.</p>
</body>
</html>
HTMLEOF
fi

# ─── START WEB SERVER FIRST ─────────────────────────────────────────────────
# HA kills the add-on if the web server doesn't respond within ~60 seconds.
# We start it immediately so HA is happy, then sync + render in the background.
bashio::log.info "Starting web server on port 8000..."
cd /app && uv run python -m heatmap.serve --port 8000 --directory "${OUTPUT_DIR}" &
SERVE_PID=$!
bashio::log.info "Web server started (PID ${SERVE_PID})"

# Give the server a moment to bind its port
sleep 3

# ─── SYNC + RENDER IN BACKGROUND ────────────────────────────────────────────
(
    # Full intervals.icu sync (year-by-year chunks)
    if [ -n "${INTERVALS_ICU_API_KEY}" ] && [ -n "${INTERVALS_ICU_ATHLETE_ID}" ]; then
        bashio::log.info "Background: syncing from intervals.icu (2010 → today)..."
        cd /app && uv run python - << PYEOF
import os, logging
from pathlib import Path
from heatmap import configure_logging
from heatmap.sources import intervals_icu
configure_logging()
result = intervals_icu.sync(
    Path("${CACHE_DIR}/intervals_icu"),
    athlete_id=os.environ["INTERVALS_ICU_ATHLETE_ID"],
    api_key=os.environ["INTERVALS_ICU_API_KEY"],
    date_from="2010-01-01",
    date_to=__import__("datetime").date.today().isoformat(),
)
print(f"Sync complete: {result.downloaded} new activities downloaded")
PYEOF
        bashio::log.info "Background: sync done."
    else
        bashio::log.info "Background: no intervals.icu credentials — skipping sync."
    fi

    # Render tiles (skip re-sync since we just did it above)
    bashio::log.info "Background: rendering heatmap tiles (this takes 10-20 min on first run)..."
    export HEATMAP_SKIP_SYNC=1
    cd /app && uv run python /app/main_ha.py
    EXIT_CODE=$?

    if [ $EXIT_CODE -eq 0 ]; then
        bashio::log.info "Background: heatmap generation complete! Refresh the heatmap page."
    else
        bashio::log.warning "Background: heatmap generation failed (exit code ${EXIT_CODE})."
        bashio::log.warning "Check credentials and try Regenerate in the admin panel."
    fi
) &

bashio::log.info "Ready! Heatmap is rendering in the background."
bashio::log.info "The heatmap page will auto-refresh when done."

# Keep container alive — wait for the web server
wait $SERVE_PID
