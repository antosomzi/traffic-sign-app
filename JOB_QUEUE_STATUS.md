## Overview
This document explains how the job queue and status tracking work in the Traffic Sign ML Pipeline application. It covers the lifecycle of a job, the attributes stored for each job, and how status and phase updates are managed and retrieved.

---

## 1. Job Lifecycle & Queueing

### a. Upload & Job Creation
- When a user uploads a file, a new job is created with a unique `job_id` (UUID4 hex).
- The file is saved and a background thread is started to handle extraction and validation.
- The job's progress and status are tracked in Redis under the key: `extraction:<job_id>`.

### b. Extraction & Pipeline
- The extraction process runs in a background thread.
- If extraction and validation succeed, a Celery task is queued to run the ML pipeline (if Celery is available).
- The job status is updated throughout the process.

---

## 2. Job Attributes (Redis Progress Object)
Each job's status is stored as a JSON object in Redis. Example attributes:

| Attribute         | Type    | Description                                                      |
|-------------------|---------|------------------------------------------------------------------|
| status            | string  | Main status: `reading`, `preparing`, `running`, `done`, `error`  |
| phase             | string  | Sub-phase: `reading`, `writing`, `extracting`, `running`         |
| progress_percent  | int     | Progress percent (0-100)                                         |
| total_files       | int     | Total files to extract                                           |
| extracted_files   | int     | Number of files extracted                                        |
| extract_size      | int     | Size in bytes of extracted data                                  |
| recording_id      | string  | Recording ID (from archive root folder)                          |
| error_msg         | string  | Error message if status is `error`                               |
| error_details     | object  | Additional error details                                         |

---

## 3. Status & Phase Updates
- The backend updates the Redis progress object at each key step:
  - After reading the file: `status=preparing`, `phase=reading`, `progress_percent=0-15`
  - After writing to disk: `phase=writing`, `progress_percent=15-30`
  - During extraction: `status=running`, `phase=running`, `progress_percent=30-100`
  - On success: `status=done`, `progress_percent=100`
  - On error: `status=error`, `error_msg` set
- Updates are made using `RedisProgressService.set_extraction_progress(job_id, progress_dict)`

---

## 4. Retrieving Status
- The frontend polls `/extract_status/<job_id>` to get the current job status.
- The route reads the Redis object and returns a JSON with the current status, phase, percent, and any error or result info.
- Example response:
```json
{
  "status": "preparing",
  "phase": "writing",
  "percent": 20,
  "message": "Writing file to disk..."
}
```

---

## 5. Modifying Status
- Only the backend modifies job status, via the extraction thread and pipeline task.
- Use `RedisProgressService.update_extraction_progress(job_id, **kwargs)` to update specific fields.
- On error, set `status` to `error` and provide `error_msg` and optionally `error_details`.

---

## 6. Error Handling
- If an error occurs at any stage, the status is set to `error` and the error message is included in the Redis object.
- The frontend displays this error to the user and stops polling.

---

## 7. Example: Status Progression
1. **Start**: `{status: 'reading', phase: 'reading', progress_percent: 0}`
2. **Writing**: `{status: 'preparing', phase: 'writing', progress_percent: 15}`
3. **Extracting**: `{status: 'preparing', phase: 'extracting', progress_percent: 30}`
4. **Running**: `{status: 'running', total_files: 100, extracted_files: 50, percent: 65}`
5. **Done**: `{status: 'done', percent: 100, recording_id: '2024_05_20_23_32_53_415'}`
6. **Error**: `{status: 'error', error_msg: 'Recording already exists.'}`

---

## 8. References
- See `services/redis_service.py` for Redis logic
- See `routes/upload_routes.py` for upload and status endpoints
- See `services/extraction_service.py` for extraction and status update logic
# 9. Transition to Celery & Pipeline Task Queue

### When is Extraction 'done'?
- The extraction/background thread sets the job status to `done` in Redis when:
  - The archive is successfully extracted and validated
  - The recording is atomically moved to the final destination
  - The status file is created and the extracted size is computed
- At this point, the frontend will see `{status: 'done', ...}` in `/extract_status/<job_id>`.

### How is the Celery Task Queued?
- If Celery is available, the backend immediately queues a pipeline task after extraction is successful:
  - `run_pipeline_task.delay(recording_id)` is called in the extraction thread
  - This adds a new task to the Celery queue (using Redis as broker)
- The Celery worker picks up the task asynchronously and runs the ML pipeline for the given `recording_id`.

### How are Status and Results Linked?
- The extraction job and the Celery pipeline task are linked by the `recording_id`:
  - Extraction status is tracked by `job_id` (unique per upload)
  - Pipeline status and results are tracked by the `status.json` file in the recording folder (and possibly by Celery task state if needed)
- The frontend can poll `/status` or check the `status.json` to see pipeline progress after extraction is done.

### Summary of Flow
1. User uploads file → extraction job starts (tracked by `job_id`)
2. Extraction completes → status set to `done` in Redis
3. Celery task is queued for ML pipeline (using `recording_id`)
4. Celery worker processes the task asynchronously
5. Pipeline results and status are written to the recording folder
6. User can download results or check status via the web interface
# Job Queue & Status Management in Traffic Sign ML Pipeline
