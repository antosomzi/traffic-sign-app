# Status Page Polling (2025 update)

This note documents the full polling workflow for the recording status page after the November 2025 refactor.

## 1. Backend routes
- `GET /status`
  - Defined in `routes/status_routes.py`.
  - Calls `_collect_recordings()` to hydrate the list of recordings. That helper:
    - Lists every folder under `recordings/`.
    - Reads `status.json` (when present) to capture `status`, `message`, and `timestamp`.
    - Inspects `result_pipeline_stable/s*/` folders to detect which pipeline steps have dropped outputs (e.g. `output.json`, `supports.csv`).
    - Compares output timestamps with the run timestamp to tell whether a step belongs to the current run.
    - Marks whether the final CSVs exist to decide if the recording is completed.
    - Returns the assembled list sorted by timestamp (most recent first).
    - Produces the JSON payload consumed by both endpoints. Example shape per recording:

      ```json
      {
        "id": "2024_05_20_23_32_53_415_v2",
        "status": "processing",
        "message": "Stage s4 running...",
        "timestamp": "2025-11-14T10:12:30.123456",
        "show_steps": true,
        "steps": [
          { "name": "s0_detection", "done": true },
          { "name": "s1_small_sign_filter", "done": true },
          { "name": "s2_tracking", "done": true },
          { "name": "s3_small_track_filter", "done": true },
          { "name": "s4_classification", "done": false },
          { "name": "s5_frames_gps_coordinates_extraction", "done": false },
          { "name": "s6_localization", "done": false },
          { "name": "s7_export_csv", "done": false }
        ]
      }
      ```
  - Renders `templates/status.html`, passing the recordings list as template context and embedding a JSON copy inside `<script id="recordings-data">` for the initial JS state.
- `GET /status/data`
  - Also in `routes/status_routes.py`.
  - Uses the **same** `_collect_recordings()` helper to return `{"recordings": [...]}` as JSON.
  - Each recording payload includes:
    - `id`, `status`, `message`, `timestamp`.
    - `show_steps` (bool) indicating whether we should display step progress (only when processing and we have outputs).
    - `steps`: an ordered array of `{ "name": step_name, "done": bool }` mirroring `STEP_NAMES`.
  - This endpoint is what the browser polls; it avoids re-rendering the full Jinja template and keeps both HTML and JSON views in sync.

## 2. Frontend flow (in `templates/status.html`)
1. **Initial render**
  - The Flask server renders the HTML with Jinja, so the user immediately sees the current status even if JavaScript is disabled. (We still serve the full HTML first for fast first paint and SSR.)
  - A `<script type="application/json">` block exposes the same data for JavaScript.
2. **Bootstrapping**
  - JS reads the embedded JSON (`initialRecordings`) and stores it in `currentRecordings`.
  - References to DOM nodes are cached (`recordingsList`, `emptyState`, `refreshButton`).
3. **Polling loop**
  - `scheduleStatusPolling()` checks if any recording is `processing` or `validated`. If yes, it sets a 10s timeout that triggers `fetchStatuses()`; if not, polling stays idle.
  - `fetchStatuses()` performs `fetch('/status/data', { Accept: 'application/json' })`, parses the JSON, updates `currentRecordings`, and re-renders the card list with `renderRecordings()`.
  - The JSON payload always contains **all** recordings; we refresh the full list each time instead of requesting only the items currently processing.
  - Polling is paused while a fetch is in flight to avoid overlaps (`isFetchingStatuses` guard) and automatically re-armed afterwards.
4. **Rendering updates**
  - `renderRecordings()` regenerates the cards using the same markup structure as the initial Jinja render. It fills status badges, timestamps, step lists, download button, etc.
  - To prevent HTML injection when building strings, helper `escapeHtml()` sanitises dynamic fields before inserting into `innerHTML`.
  - After the DOM is replaced, `attachActionListeners()` walks through the new buttons and reattaches the click listeners so that delete/rerun still work on the freshly rendered elements.
  - When `show_steps` is true, the JS loops through the `steps` array and renders each `{name, done}` pair to depict which stage has completed.
5. **Manual refresh**
  - Clicking the 🔄 button calls `handleManualRefresh()`: pauses polling, runs `fetchStatuses({ manual: true })`, shows a short “⏳ Refreshing...” state on the button, then resumes polling.
6. **User actions**
  - Delete and rerun buttons pause the poll, show the confirmation modal, call their respective routes (`DELETE /delete/<recording_id>` and `POST /rerun/<recording_id>`), then refresh the list via `fetchStatuses()` and resume the poll.

## 3. Why this approach?
- Eliminates full-page reloads every 10 seconds (no more flicker or scroll reset).
- Keeps server logic DRY: both the HTML page and the JSON poll share `_collect_recordings()`.
- Maintains the same UX surface area (cards, modals, buttons) while quietly updating data.
- Provides safe DOM updates by sanitising strings before injecting HTML.
- Sticks with Jinja for server-side rendering so the same template can be reused for the initial response while the JSON feed powers the live updates.

### Why do we still use Jinja if we return JSON?
- Jinja is the templating engine Flask uses to produce the first HTML payload; this ensures the status page is readable even if JS fails and keeps route `/status` compatible with the rest of the app.
- The JSON endpoint is complementary: it lets the browser refresh the same data without re-rendering the template on the server, but it is not responsible for initial layout.
- By keeping both, we benefit from SSR (fast initial render, SEO-friendly) and CSR (smooth incremental updates) without reimplementing the entire UI purely in client-side code.

## 4. Key code locations
- `routes/status_routes.py` — both routes and data aggregation helper.
- `templates/status.html` — look for the functions `fetchStatuses`, `renderRecordings`, `scheduleStatusPolling`, and `escapeHtml`.

That’s the entire flow: server renders once, client polls `/status/data` only when something is running, cards update in place, and manual actions pause/resume the loop as needed.
