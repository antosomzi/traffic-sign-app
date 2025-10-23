# Status Page Polling Logic

This document explains how the polling mechanism works on the status page of the Traffic Sign ML Pipeline web application.

---

## 1. Overview
- The status page (`/status`) displays the progress and results of all uploaded recordings.
- It uses a polling mechanism to refresh the page and show real-time updates when jobs are in progress.

---

## 2. How Polling Works

### a. Backend (Flask)
- The `/status` route (see `routes/status_routes.py`) scans the recordings directory on the server.
- For each recording, it reads the `status.json` file to determine the current state (`validated`, `processing`, `completed`, `error`).
- The backend passes a list of all recordings and their statuses to the `status.html` template as the `recordings` variable.

### b. Frontend (Jinja2 + JavaScript)
- The `status.html` template renders the list of recordings and their statuses.
- At the bottom of the page, a JavaScript snippet checks if any recording is still in progress:
  ```js
  const recordings = {{ recordings|tojson|safe }};
  const hasProcessing = recordings.some(r => r.status === 'processing' || r.status === 'validated');
  if (hasProcessing) {
      setTimeout(() => {
          location.reload();
      }, 2000);
  }
  ```
- If at least one recording is in `processing` or `validated` state, the page automatically reloads every 2 seconds (polling).
- If all recordings are `completed` or `error`, the page does not auto-refresh.

---

## 3. Why This Approach?
- Polling ensures users see up-to-date progress and results without manual refresh.
- Polling is only active when there is something to monitor (an active or pending job).
- When all jobs are finished, polling stops, reducing server and network load.

---

## 4. What Triggers Polling?
- Uploading a new recording and starting a job (status becomes `validated` or `processing`).
- As long as at least one job is not finished, polling continues.
- When all jobs are done or failed, polling stops automatically.

---

## 5. Limitations & Improvements
- The current polling is page-based (full reload), not AJAX. This is simple but can be improved for smoother UX.
- For large numbers of jobs or users, consider switching to AJAX polling or WebSockets for more efficient updates.

---

## 6. References
- `routes/status_routes.py` (backend logic)
- `templates/status.html` (frontend logic)

---

**Summary:**
- The status page only polls (auto-refreshes) when there are jobs in progress.
- This is controlled by a simple JavaScript check on the job statuses passed from the backend.
- When all jobs are done, the page becomes static until a new job is started.
