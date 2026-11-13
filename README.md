# ReStore

ReStore is a local document storage demo with PDF text extraction, document search,
exact duplicate detection, and local video transcription for the Ericsson Hackathon. Select a
PDF, upload it, and view its embedded text page by page. The original PDF is saved
locally; metadata, SHA-256, and extracted pages are stored in PostgreSQL. Choose
**View text** in the saved files table to reopen a document. The selected file ID
is kept in the URL (`/extract?file=4`, or `/extract?file=4&page=2` for a search result), so
refreshing the browser restores the saved document and selected page. Search the
stored text with the **Search documents** form, then choose **View page** to jump
to a matching page in the same viewer. Open **Duplicates** to review matching
file hashes and potential storage savings without changing any stored files.
Use **Video Transcription** to upload an MP4, follow actual processing stages, and
read or download its saved timestamped transcript.

## Data flow and source layout

```text
Vue upload form → POST /files/upload → upload service
  → streamed filesystem storage + SHA-256
  → PyMuPDF page extraction
  → one PostgreSQL transaction (metadata + pages)
Vue → GET /search?q=... → search service → PostgreSQL full-text search
  → ranked page excerpts → View page → existing document viewer
Vue → GET /files/{id}/pages → saved document and page text
Vue → GET /duplicates → grouped SHA-256/size metadata → potential savings
Vue → POST /videos/upload → validation + file/job transaction → HTTP 202
Worker → PostgreSQL queue → FFmpeg WAV → faster-whisper → transcript transaction
Vue → poll GET /jobs/{id} → completed transcript → text download
```

The processor uses [PyMuPDF's text extraction API](https://pymupdf.readthedocs.io/en/latest/recipes-text.html).
Pages without embedded text are stored as empty strings, preserving page numbers.

| File or directory | Responsibility |
| --- | --- |
| `backend/main.py`, `backend/database.py` | Compatibility imports for existing startup and connection code |
| `backend/app/main.py` | FastAPI setup, CORS, health route, router registration |
| `backend/app/core/config.py` | Load backend `.env`, upload directory, size limit |
| `backend/app/core/database.py` | psycopg connection factory |
| `backend/app/api/files.py` | HTTP routes, status codes, response schemas |
| `backend/app/services/file_service.py` | Upload validation, buffered storage, hashing, orchestration, cleanup |
| `backend/app/processors/pdf_processor.py` | Typed page extraction independent of HTTP and PostgreSQL |
| `backend/app/repositories/file_repository.py` | SQL, ordered retrieval, atomic document persistence |
| `backend/app/schemas/file.py` | Pydantic file API responses |
| `backend/app/api/search.py` | Search parameter validation and safe HTTP errors |
| `backend/app/services/search_service.py` | Normalize/validate search text and build the search response |
| `backend/app/repositories/search_repository.py` | Parameterized full-text matching, ranking, bounded excerpts |
| `backend/app/schemas/search.py` | Typed search results and returned count |
| `backend/app/api/duplicates.py` | Read-only duplicate endpoint and private error handling |
| `backend/app/repositories/duplicate_repository.py` | One SQL query for valid SHA-256/size groups and ordered files |
| `backend/app/services/duplicate_service.py` | Integer savings calculations and summary statistics |
| `backend/app/schemas/duplicate.py` | Duplicate file, group, summary, and response schemas |
| `backend/tests/test_duplicates.py` | Isolated duplicate-query, API, savings, and preservation tests |
| `backend/app/api/transcription.py` | Video upload, saved recordings, job status, transcript/download HTTP routes |
| `backend/app/services/transcription_service.py` | Upload coordination and staged video processing |
| `backend/app/services/transcript_export.py` | Human-readable timestamp and stored transcript export |
| `backend/app/processors/audio_extractor.py` | FFprobe validation and FFmpeg mono 16 kHz WAV extraction |
| `backend/app/processors/speech_recognizer.py` | Cached CPU/GPU-configurable faster-whisper model and typed segments |
| `backend/app/repositories/transcription_repository.py` | Queue claims, job updates, video metadata, atomic transcript persistence |
| `backend/app/schemas/transcription.py` | Typed video, job, and transcript API responses |
| `backend/app/worker.py` | Single-worker queue loop, exclusivity, and interrupted-job recovery |
| `backend/app/core/transcription_worker.py` | API-owned worker startup, supervision, and bounded shutdown |
| `backend/dev.py` | Development launcher watching only application source |
| `backend/tests/` | Processor, upload, API, migration, persistence, worker, and rollback tests |
| `database/01_schema.sql` | Full schema for fresh installations |
| `database/migrations/001_pdf_extraction.sql` | Additive PDF extraction migration |
| `database/migrations/002_document_search.sql` | GIN index over existing and future extracted page text |
| `database/migrations/003_remove_sample_data.sql` | Remove only the original unbacked sample metadata |
| `database/migrations/004_video_transcription.sql` | Additive video metadata, processing jobs, and transcript segments |
| `frontend/src/App.vue` | Shared application header, navigation, and router view |
| `frontend/src/components/AppNavigation.vue` | Files, PDF Extraction, Document Search, Duplicates, and Video Transcription links |
| `frontend/src/router/index.ts` | Named routes, root redirect, and browser history |
| `frontend/src/views/FilesView.vue` | File list loading, refresh, and links to saved documents |
| `frontend/src/views/PdfExtractionView.vue` | Upload, document viewing, and route query selection |
| `frontend/src/views/DocumentSearchView.vue` | Search and navigation to matching document pages |
| `frontend/src/views/DuplicatesView.vue` | Initial scan, manual refresh, and request states |
| `frontend/src/views/VideoTranscriptionView.vue` | Video page, route-based selection, upload actions, and download |
| `frontend/src/components/transcription/` | MP4 picker, actual job stage display, and selectable transcript text |
| `frontend/src/composables/useTranscription.ts` | Saved recordings, upload state, status polling/retry/cleanup |
| `frontend/src/services/transcription.ts` | Typed video/job/transcript and text-download requests |
| `frontend/src/types/transcription.ts` | Video, job, and timestamped transcript interfaces |
| `frontend/src/utils/formatTimestamp.ts` | Millisecond timestamps for the viewer |
| `frontend/src/components/duplicates/` | Summary and grouped matching file metadata |
| `frontend/src/services/duplicates.ts` | Typed GET request to the duplicates endpoint |
| `frontend/src/types/duplicate.ts` | Duplicate API interfaces |
| `frontend/src/utils/formatBytes.ts` | Shared decimal byte-unit display for duplicate results |
| `frontend/src/components/files/` | Upload form, saved files table, document details, selected page display |
| `frontend/src/components/search/DocumentSearch.vue` | Search form, local state, cancellation and stale-response protection |
| `frontend/src/components/search/SearchResults.vue` | Safe text snippets and page selection actions |
| `frontend/src/composables/useFiles.ts` | File list and refresh state |
| `frontend/src/composables/useDocument.ts` | Upload state and saved document retrieval |
| `frontend/src/services/api.ts` | Shared typed HTTP helper, file API calls and errors |
| `frontend/src/services/search.ts` | URL-encoded search API requests |
| `frontend/src/types/search.ts` | Search response and result interfaces |
| `frontend/src/types/` | Shared file and document response interfaces |
| `frontend/src/style.css` | Simple shared layout and typography |

API handlers contain no SQL or PDF parsing. Components receive typed props and
emit actions; requests stay in the service. No global state library is needed.

## Setup

Use Python 3.10+, Node.js 22.12+ (or another version supported by Vite 8), Docker,
and Docker Compose. Run commands from the repository root unless shown otherwise.

### 1. PostgreSQL

```bash
docker compose up -d
```

Compose exposes PostgreSQL 18 on **localhost:5433**, avoiding the separate local
PostgreSQL instance on port 5432. Local credentials are user `my`, password
`mypass`, database `restore`.

Apply the migration to the existing database:

```bash
docker compose exec -T postgres psql -v ON_ERROR_STOP=1 -U my -d restore < database/migrations/001_pdf_extraction.sql
docker compose exec -T postgres psql -v ON_ERROR_STOP=1 -U my -d restore < database/migrations/002_document_search.sql
docker compose exec -T postgres psql -v ON_ERROR_STOP=1 -U my -d restore < database/migrations/003_remove_sample_data.sql
docker compose exec -T postgres psql -v ON_ERROR_STOP=1 -U my -d restore < database/migrations/004_video_transcription.sql
```

The migration adds nullable `files.storage_path` and creates `document_pages`
with a foreign key, positive page numbers, and a unique `(file_id, page_number)`
pair. It can be rerun safely. Existing rows remain intact with a null storage path.
Fresh volumes also receive this schema through `01_schema.sql`. Initialization
scripts do not run again on existing volumes, so run the migration explicitly.
The second migration adds `idx_document_pages_fts`, a GIN expression index on
`to_tsvector('simple', extracted_text)`. It indexes already stored text and is
updated automatically by PostgreSQL for future uploads. No PDF re-upload or
reprocessing is required. It can also be rerun safely. The regular index build may
briefly block writes; run it while uploads are idle for this local demo.
Do not remove the volume to update the schema.

### 2. Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
```

If `backend/.env` does not already exist, copy `backend/.env.example` to it.
For an existing `.env`, retain its settings and ensure the database port is 5433:

```dotenv
DATABASE_URL=postgresql://my:mypass@localhost:5433/restore
UPLOAD_DIR=uploads
MAX_UPLOAD_BYTES=25000000
```

Relative upload directories resolve from `backend/`. The default limit is
25,000,000 bytes. Original names are stored as metadata; filesystem names are
unique and cannot be controlled by the client. Uploads and `.env` are gitignored.
Back up the upload directory along with the database if results need to survive
moving the project. `requirements.txt` contains runtime dependencies;
`requirements-dev.txt` adds pytest and HTTPX.

Start the API from `backend/`:

```bash
python dev.py
```

The API is at `http://localhost:8000`; interactive documentation is at `/docs`.
`GET /health` remains available.

### 3. Frontend

In a separate terminal:

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173` (redirects to `/files`). Use the **Files**,
**PDF Extraction**, **Document Search**, **Duplicates**, and **Video Transcription** tabs to open each feature. Saved files
and search results open the viewer at `/extract?file=...&page=...`. See the
[frontend README](frontend/README.md) for routing, production history fallback,
and instructions for adding a feature tab. The frontend defaults to `http://localhost:8000`;
set `VITE_API_URL` in the frontend environment to change it. If changing the
frontend origin, update the backend CORS allowlist as well.

## API

### Upload a PDF

```bash
curl -F 'file=@/path/to/network_training.pdf' http://localhost:8000/files/upload
```

`POST /files/upload` accepts multipart field `file` and returns HTTP 201 only
after storage, extraction, and the database transaction complete:

```json
{"id":4,"filename":"network_training.pdf","size_bytes":250000,"page_count":3,"status":"completed"}
```

Validation checks the extension, actual PDF signature, and PyMuPDF's parsed
content rather than trusting MIME type alone. Empty or unreadable/corrupted PDFs
return 400, unsupported formats return 415, and files exceeding the configured
limit return 413. Storage, database, and unexpected errors return a generic 500.
Failed uploads remove only their own local file, and failed database writes roll
back both metadata and pages. Internal error logs omit document contents.

### Retrieve saved pages

```bash
curl http://localhost:8000/files/4/pages
```

`GET /files/{file_id}/pages` returns ordered pages:

```json
{
  "file_id":4,
  "filename":"network_training.pdf",
  "size_bytes":250000,
  "page_count":3,
  "status":"completed",
  "pages":[
    {"page_number":1,"text":"Introduction..."},
    {"page_number":2,"text":"Main components..."},
    {"page_number":3,"text":"Conclusion..."}
  ]
}
```

Unknown file IDs return 404. Files without extracted pages return HTTP 200
with `status: "not_processed"`, `page_count: 0`, and `pages: []`. Upload their
original PDF to create a processed document. A successfully processed image-only
PDF has `status: "completed"` and empty text for each page.

### List files

```bash
curl http://localhost:8000/files
```

`GET /files` returns all records ordered by ID, including the existing metadata
and `uploaded_at` timestamp. New uploads appear in the same list.

### Search saved document pages

```bash
curl --get --data-urlencode 'q=network architecture' --data 'limit=20' http://localhost:8000/search
curl --get --data-urlencode 'q="network architecture"' http://localhost:8000/search
curl --get --data-urlencode 'q=network -security' http://localhost:8000/search
```

`GET /search?q=...&limit=20` searches the text already in PostgreSQL. The query must
contain 1–200 characters and at least one non-whitespace character. Null characters
are rejected. The default limit is 20 matching pages and the allowed range is
1–100. Missing/invalid parameters return 422. No matches, punctuation-only queries,
and searches before any documents have pages return a successful empty result.
Unexpected database errors return a generic 500 without internal details.

Example response (scores depend on actual page text):

```json
{
  "query": "network architecture",
  "returned_count": 1,
  "results": [{
    "file_id": 4,
    "filename": "network_training.pdf",
    "page_number": 3,
    "snippet": "The network architecture connects the components...",
    "relevance": 0.2
  }]
}
```

`returned_count` is the number of results in this response after applying the
limit. It is not a total across all matching pages. Matches are ranked by the raw
PostgreSQL `ts_rank_cd` cover-density score, descending. Higher scores favor more
and closer occurrences of the terms; this is not a confidence percentage or a
normalized 0–1 score. Equal scores are ordered by file ID and page number.

Search uses PostgreSQL's [web-search query syntax](https://www.postgresql.org/docs/18/textsearch-controls.html):

| Query | Meaning |
| --- | --- |
| `network architecture` | Both terms on the same page, in any order |
| `"network architecture"` | The adjacent phrase on the same page |
| `network -security` | Match network, excluding pages containing security |
| `network OR storage` | Match either term |

The `simple` configuration is explicit in the index, matching, ranking, and
snippet generation. Matching is case-insensitive and extra whitespace is
normalized. There is no language-specific stemming: `network` and `networks`
are different terms. Punctuation follows PostgreSQL tokenization; this is not a
substring, fuzzy, wildcard, or semantic search. Phrase matching follows token
positions, not literal substring equality. Terms do not match across page
boundaries, and image-only pages have no searchable text.

The repository uses `to_tsvector`, `websearch_to_tsquery`, `ts_rank_cd`, and
`ts_headline` with parameterized SQL. Snippets contain at most 35 words (subject
to PostgreSQL's excerpt selection) and are additionally capped at 500 characters.
No highlighting markup is added. Source text remains untrusted and Vue renders
snippets with ordinary text interpolation, never `v-html`.

The search panel supports Enter or button submission, clearing, loading, empty,
and error states. Blank queries do not issue requests. New searches cancel older
requests, and a request version prevents stale responses from replacing newer
results. Selecting a result loads the existing document viewer, scrolls to the
page, and moves keyboard focus to it. The selected page is marked visually and
its URL survives refresh. Missing documents/pages show an understandable error.

### Exact duplicate detection

Open the **Duplicates** tab at `/duplicates`. It scans on entry; **Scan for
Duplicates** refreshes the results from the API. The button does not rehash files
or reprocess PDFs. Existing upload behavior remains unchanged: each upload keeps
its own metadata, original PDF, and extracted pages.

```bash
curl http://localhost:8000/duplicates
```

`GET /duplicates` reads the existing `files` table and returns HTTP 200 with groups
and summary statistics. No migration, new table, or dependency is required. The
query is appropriate for the current demo data volume; an index can be evaluated
later against measured workloads.

Illustrative response for two identical uploaded PDFs:

```json
{
  "summary": {
    "duplicate_groups": 1,
    "redundant_copies": 1,
    "potential_savings_bytes": 12000000
  },
  "groups": [{
    "sha256": "15905c7c97ba0c814314af3f2e165943212ae93b4049acefefe9402ecef481d6",
    "file_size_bytes": 12000000,
    "file_count": 2,
    "potential_savings_bytes": 12000000,
    "files": [
      {"id": 1, "filename": "training.pdf", "size_bytes": 12000000, "uploaded_at": "2026-11-11T13:28:21Z"},
      {"id": 2, "filename": "training (1).pdf", "size_bytes": 12000000, "uploaded_at": "2026-11-11T13:28:21Z"}
    ]
  }]
}
```

For real uploads, the existing upload service computes SHA-256 from the actual
bytes. The scan groups distinct file IDs with the same hash **and** byte size,
regardless of filename. Hashes must contain exactly 64 hexadecimal characters;
uppercase hex is normalized to lowercase. Missing/malformed hashes, negative
sizes, and obvious repeated-character placeholder hashes are excluded.

Fresh installations contain no sample files. For existing databases, apply the
idempotent cleanup migration:

```bash
docker compose exec -T postgres psql -v ON_ERROR_STOP=1 -U my -d restore < database/migrations/003_remove_sample_data.sql
```

It removes only the three original seed signatures when they have neither a
storage path nor extracted pages. Real uploaded files are preserved, including
uploads with the same filenames. Scans trust stored metadata and do not reread
original bytes.

Groups are ordered by normalized hash and size. Files within each
group are ordered by upload date ascending, then ID; missing dates come last and
display as Unknown. Unique files are not included. No matches return HTTP 200,
`groups: []`, and zero for every summary field. Database errors return a generic
500 and are displayed as errors, never as a successful zero-duplicate scan.

Potential savings use integer byte arithmetic:

```text
redundant_copies = sum(file_count - 1 for each group)
group_potential_savings_bytes = (file_count - 1) * file_size_bytes
total_potential_savings_bytes = sum(group_potential_savings_bytes)
```

For three identical 10 MB files, keeping one copy gives **20 MB potential** savings.
The UI converts byte counts to decimal KB/MB/GB for display only. These estimates
assume every copy occupies separate physical storage; deduplicated/shared storage
may yield smaller real savings. Nothing has been reclaimed, and no files or
records are deleted, modified, or automatically merged.

This feature detects byte-identical content based on SHA-256 metadata. It does not
compare visual appearance: two PDFs with the same visible slides but different
metadata or encoding may have different bytes and hashes. A hash match is strong
evidence, not permission to delete either file. Future slide-level or semantic
duplicate detection would compare rendered pages or meaning instead of whole-file
bytes; neither is part of this feature.

### Video upload and transcription

The **Video Transcription** tab at `/transcription` uploads MP4 recordings, shows
the current PostgreSQL job status, and displays saved timestamped speech. It is
independent of PDF extraction. Video rows also appear in Files, where **View
transcript** opens the video page. A selection such as `/transcription?file=12`
survives refresh and browser history navigation. Opening an existing recording
never queues another transcription.

#### Dependencies and configuration

Install FFmpeg **and FFprobe** on Linux, for example on Ubuntu/Debian:

```bash
sudo apt-get update
sudo apt-get install ffmpeg
ffmpeg -version
ffprobe -version
```

With the backend virtual environment activated, install runtime dependencies:

```bash
pip install -r requirements.txt
```

This includes `faster-whisper==1.2.1`. Models run locally; no cloud transcription
service is used. See [faster-whisper's usage documentation](https://github.com/SYSTRAN/faster-whisper#usage)
for available models and supported device/compute types.

Settings in `backend/.env` (defaults shown):

```dotenv
MAX_VIDEO_UPLOAD_BYTES=200000000
MEDIA_TIMEOUT_SECONDS=3600
WHISPER_MODEL=tiny
WHISPER_DEVICE=cpu
WHISPER_COMPUTE_TYPE=int8
WHISPER_LANGUAGE=auto
WHISPER_DOWNLOAD_ROOT=.cache/whisper
```

The tiny multilingual model and CPU `int8` settings keep development requirements
small. Set `WHISPER_LANGUAGE=en`, `sv`, or another supported language code to force
a language; empty or `auto` enables detection. `WHISPER_MODEL` may also be a local
converted model directory. A model is reused for all jobs within the worker process.
Restart the worker after changing settings.

The first use may download model files, requiring internet access and disk space.
The cache defaults to `backend/.cache/whisper` and is gitignored. After caching,
models can run offline; `HF_HUB_OFFLINE=1` prevents download attempts when the
required files are available locally. Never add downloaded models to Git.

Tools are resolved from `FFMPEG_BINARY`/`FFPROBE_BINARY` overrides, system PATH, or
executables beside the current Python interpreter (such as `.venv/bin/ffmpeg`).
Set overrides to absolute executable paths if using a standalone installation.
The development workspace has standalone binaries in `backend/.venv/bin` and a
cached tiny model; those environment artifacts are not part of the repository.
Other installations must install tools and download/cache their model themselves.

#### Database migration

Apply the additive migration to the existing database; do not reset the volume:

```bash
docker compose exec -T postgres psql -v ON_ERROR_STOP=1 -U my -d restore < database/migrations/004_video_transcription.sql
```

It adds nullable `files.file_type`, `duration_ms`, and `transcript_language` without
changing existing file metadata. It creates `processing_jobs` and
`transcript_segments`, foreign keys, status/timestamp checks, and indexes. One
transcription job is allowed per uploaded file; duplicate uploads are separate
files. Millisecond timestamps must be nonnegative with `end_ms >= start_ms`.
Fresh installations get the same schema via `01_schema.sql`. Reapplying the
migration is safe.

#### Run API and frontend (worker starts automatically)

Run the backend and frontend in separate terminals. The API starts and supervises
the existing transcription worker automatically, using the same virtual environment,
`.env`, database, and upload directory. No third terminal is required.

```bash
# Terminal 1, from backend/
source .venv/bin/activate
python dev.py
```

```bash
# Terminal 2, from frontend/
npm run dev
```

`python dev.py` enables Uvicorn reload **only for `backend/app/`**, avoiding reloads
and long filename lists from changes inside `.venv`, model caches, uploads, and
tests. The equivalent CLI is `uvicorn main:app --reload --reload-dir app`.
The existing `uvicorn main:app --reload` command also starts the worker automatically,
but its default broad watch directory may include virtual-environment Python files.

The FastAPI lifespan owns the worker process and closes it on shutdown. If the
worker exits unexpectedly, the API logs its return code and restarts it after a
short delay. It stays outside the API event loop, so uploads/status requests do not
wait for inference. Previously queued jobs are picked up automatically.

For a separately managed worker, set `AUTO_START_TRANSCRIPTION_WORKER=false` in
`backend/.env`, then run `python -m app.worker` in its own terminal. This opt-out is
also used by automated tests so they never consume development jobs. Standalone
`python -m app.worker --once` processes at most one job; stop/disable the automatic
worker first. A supervised worker waits if another worker already holds the
PostgreSQL lock, preventing duplicate processing while allowing a safe handoff.

Upload an MP4 with speech through the tab or API:

```bash
curl -F 'file=@/path/to/meeting.mp4' http://localhost:8000/videos/upload
```

The upload streams bytes through the existing buffering/SHA-256 helper, saves a
unique `.mp4` path, validates video/audio streams with FFprobe, then atomically
creates metadata and a job. It returns **202 Accepted** before transcription:

```json
{"file_id":12,"job_id":7,"filename":"meeting.mp4","status":"queued"}
```

Empty/corrupted recordings and recordings without audio return 400. Unsupported
extensions return 415, uploads over the configured byte limit return 413, missing
FFprobe returns 503, and storage/database failures return a generic 500. Failed
uploads clean up only the new uncommitted file. Once a job is queued, processing
failures preserve the original MP4.

#### Job lifecycle and progress

The worker claims a queued row with a transaction and `FOR UPDATE SKIP LOCKED`,
then commits the claim before slow processing. Actual stages are:

```text
queued → validating_video → extracting_audio → transcribing_audio → saving_transcript → completed
```

FFmpeg extracts the first audio stream as mono 16 kHz WAV. The worker fully
consumes faster-whisper's segment iterator before saving results; returning an
iterator alone does not mean inference has completed. Segment seconds are rounded
to integer milliseconds. The transaction inserts all segments, saves detected
language, and marks the job completed together. Insertion failures roll back the
entire transcript and the job is marked failed. No speech is a valid completed
transcript with zero segments.

```bash
curl http://localhost:8000/jobs/7
```

Example status:

```json
{
  "id":7,"file_id":12,"status":"processing",
  "current_step":"transcribing_audio","error_message":null,
  "created_at":"2026-11-11T12:00:00Z",
  "started_at":"2026-11-11T12:00:01Z","completed_at":null
}
```

The UI polls every 1.5 seconds after each response while queued/processing. It
shows backend stages rather than fake percentages. Temporary polling failures
stop polling and offer **Retry status**, which reads the same job without
retranscribing. Polling stops on completion, failure, selection change, or leaving
the page. Upload uses an indeterminate uploading/validating message because the
current fetch-based transport does not expose upload-byte progress.

One local worker is permitted per database using a session advisory lock. At
startup, it marks previously processing jobs as failed/interrupted before handling
queued work; completed/queued jobs are preserved. API shutdown gives its worker up to ten seconds to finish the current job,
then terminates the worker process group if necessary. A standalone worker finishes
its current job on graceful shutdown. Forced termination or a database outage can leave a processing status
until the worker restarts; the API restarts a crashed worker automatically, but
there is no job heartbeat watchdog. After a failure the
original is retained; re-upload explicitly to create another attempt. There is no
automatic retry or retranscription on opening results.

#### Saved transcripts and download

```bash
curl http://localhost:8000/videos
curl http://localhost:8000/videos/12
curl http://localhost:8000/videos/12/transcript
curl -o transcript.txt http://localhost:8000/videos/12/transcript/download
```

`GET /videos` supplies the saved-recordings list. `GET /videos/{id}` returns its
metadata and job ID. Missing recordings/jobs return 404. Transcript and download
requests return **409 Conflict** with status, current step, and a safe message
while queued/processing/failed; they never pretend an incomplete job is an empty
completed transcript. Successful transcript responses contain filename, duration,
detected language, completed status, and chronologically ordered segments:

```json
{
  "file_id":12,"filename":"meeting.mp4","duration_ms":720000,
  "language":"en","status":"completed",
  "segments":[{"id":1,"start_ms":3000,"end_ms":8000,"text":"Welcome to the meeting."}]
}
```

The download is UTF-8 plain text generated from stored segments with timestamp
ranges (`00:00:03.000 – 00:00:08.000`). It never opens the original media or runs
Whisper again. Temporary WAV files are removed on normal success/failure. An abrupt
process kill may leave an OS temporary directory named `restore-audio-*`; it is
not part of original-file storage and can be cleaned up once no worker uses it.

#### Manual speech check and limitations

Record a short MP4 saying a known sentence, upload it, and observe real job stages.
After completion, compare recognized words and timestamps with the recording,
download the `.txt`, refresh the page, and reopen the same saved recording. No new
job should appear. Accuracy varies with model size, language, noise, accents, and
recording quality; the tiny model is intended for development rather than a
quality guarantee.

Verification included an actual MP4 made from the faster-whisper project's public
[JFK speech fixture](https://github.com/SYSTRAN/faster-whisper/tree/master/tests/data),
real FFmpeg/FFprobe, the tiny CPU model, PostgreSQL persistence, browser polling,
and text download. Recognized output contained the expected words from that short
fixture. This does not establish accuracy on other recordings. Automated pytest
tests use model doubles and do not download a model on each run.

Original videos remain on local disk; spoken text does not preserve diagrams,
slides, or all visual information. Slide extraction, speaker identification,
translation, summarization, transcript search, and video deletion are not part of
this feature. Large recordings may take significant CPU time, temporary WAV disk
space, and transcript memory. File-byte limits do not bound decoded audio length;
FFmpeg conversion has a configurable timeout, but model inference has no separate
hard timeout. The worker and polling approach are for a local demo, not a
multi-machine production queue.

## Verification

Run backend tests from `backend/`:

```bash
source .venv/bin/activate
TEST_DATABASE_URL=postgresql://my:mypass@localhost:5433/restore pytest -q
```

The test role must be able to create schemas. Each integration test creates a
random `restore_test_*` schema, restricts its connection search path to that
schema, and drops only that schema afterward. Tests never truncate or delete the
team's development tables or upload directory. Without `TEST_DATABASE_URL`,
database integration tests are explicitly skipped; processor and error-path
tests still run. PDFs are generated programmatically rather than downloaded.

Tests cover real extraction, multiple/empty pages, invalid and encrypted PDFs,
upload validation and size limits, storage/database failure cleanup, collision
safety, SHA-256, metadata and page relationships, page ordering, transaction
rollback, existing endpoints, fresh schema setup, and repeatable additive migrations.
`backend/tests/test_search.py` additionally verifies real PostgreSQL matching,
case/whitespace normalization, phrases, OR/exclusions, ranks and stable ordering,
limits, joins, safe special characters, private errors, bounded snippets, index
use, migration preservation, and searchability of a new upload without reprocessing.
`backend/tests/test_duplicates.py` tests empty/unique files, two/three copies,
multiple groups, filenames versus content, invalid/missing/placeholder hashes,
matching hashes with different sizes, deterministic dates/IDs, exact integer
savings, safe sample-record cleanup, uploaded PDFs with actual hashes, error privacy, and
preservation of file metadata and stored bytes. Run that feature alone with
`TEST_DATABASE_URL=postgresql://my:mypass@localhost:5433/restore pytest -q tests/test_duplicates.py`
from `backend/`.

Video tests in `backend/tests/test_transcription.py` and
`test_transcription_processors.py` cover validation, actual-byte hashes, queue
creation/claiming, worker exclusivity and recovery, stages, atomic rollback,
ordering, transcript retrieval/export, missing resources, safe errors, model reuse,
iterator exhaustion, no speech, and cleanup. They do not download speech models.
`test_worker_lifecycle.py` verifies default worker startup from the API lifespan,
standalone opt-out, crash/startup retries, bounded process shutdown, and exclusion
of virtualenv/cache/upload directories from development reloading.
Real media tests run when FFmpeg/FFprobe are on PATH or `FFMPEG_BINARY` and
`FFPROBE_BINARY` are set; otherwise those tests explicitly skip. Activating the
workspace virtual environment exposes the installed local binaries.

Type-check and build the frontend:

```bash
cd frontend
npm run build
```

The implementation was also checked in headless Chromium using controlled API
responses for search loading/results, empty/error states, clear, stale responses,
HTML-as-text safety, selected-page navigation/focus, refresh restoration, missing
records/pages, and mobile overflow. Those browser checks were run with temporary
tooling outside the repository; no frontend test framework dependency was added.
The backend suite uses real PostgreSQL text-search and duplicate-group queries
independently of those controlled browser responses. Duplicates browser checks
also used a live PostgreSQL-backed API to compare displayed results, verify manual
refresh requests, and confirm existing file metadata stayed unchanged. Controlled
responses covered duplicate empty/error states and retry.

## Limitations

- PDF extraction supports PDF documents and transcription supports MP4 recordings.
  OCR is not implemented. Scanned/image-only
  pages have no selectable text, which the UI explains.
- Password-protected PDFs requiring a password are rejected. Corrupted PDFs that
  require repair are rejected rather than silently returning incomplete text.
- Extraction preserves page boundaries, but complex tables and column layouts
  may not retain their visual reading order.
- PDF processing is synchronous; large or complex PDFs take longer and extracted text
  is held in memory. The upload-byte limit does not bound expanded PDF complexity.
- Ordinary failures are cleaned up, but a process crash between filesystem writes
  and database commit can leave an orphan PDF. These are separate storage systems.
- There is no authentication. This application is intended for local demonstration.
- Search returns at most 100 pages without pagination or a full match count. There
  is no stemming, fuzzy matching, semantic retrieval, or OCR. Future improvements
  could add pagination and measured tuning for larger corpora.
- Video transcription uses a separate local worker and can take significant time.
  Its restart recovery and temporary-file limitations are described above.
- Duplicate uploads create separate documents; this feature only identifies
  potential savings. Actual deduplication, deletion, AI,
  background jobs, and cloud integrations are outside this feature.
