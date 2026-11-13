# Storeless

## Long video transcription

The worker reads the temporary mono 16 kHz WAV in short windows, rather than
loading the full recording into memory. Audio, voice detection and model feature
buffers are bounded by window duration; only transcript text accumulates. The
original MP4 is streamed to disk on upload and is retained after processing.

Optional settings in `backend/.env` (defaults shown):

```dotenv
WHISPER_CHUNK_SECONDS=60
WHISPER_CPU_THREADS=2
```

Chunk duration must be 1–120 seconds. Windows include up to two seconds of context
on either side, and transcript timestamps are shifted back to the original
recording. The model is reused, with one inference worker and two CPU threads by
default; FFmpeg decoding uses one thread. Larger or longer recordings take more
time without requiring whole-recording audio/feature buffers in RAM.

Completed windows produce `transcription_progress` log entries with the job ID,
actual processed milliseconds, and total milliseconds. No transcript text is
written to logs. A job is completed only after all windows have been transcribed
and its transcript has been saved atomically.

Apply backend changes or environment changes with:

```sh
docker compose up -d --build
```

Follow real processing progress with:

```sh
docker compose logs -f backend
```

The existing startup recovery marks jobs interrupted by a shutdown as failed;
restarting a container alone does not mark an incomplete transcript successful.

## Slide Similarity & Duplicate Detection

Open **Slide Comparison** in the sidebar, or follow the link from **Duplicates**.
Upload PDF or PPTX presentations, then select one to view its matching slides
side by side with slides from other analyzed presentations. The Files drawer
opens PPTX slide results and offers **Compare slides** for PDFs. The global
upload dialog also accepts PPTX; its existing PDF upload workflow still extracts
text and now queues slide analysis automatically.

Existing PDFs appear in the presentation selector. Choose **Analyze slides** to
index a previously uploaded file once; it must still exist on disk. Queued and
processing jobs are polled until completion, with failures and a Retry analysis
action shown explicitly. Rendering is handled by the existing background worker;
a presentation may wait while that worker finishes a recording. Completed slide
images/hashes are reused rather than regenerated on comparison or refresh.

### Comparison rules

- PDF pages are rendered with PyMuPDF. PPTX files are converted locally by
  LibreOffice Impress in headless mode with a temporary, isolated user profile.
  `.ppt`, macro-enabled and encrypted presentations are not supported.
- Every page is letterboxed onto a white **960 × 720 RGB canvas**. A **480 × 360**
  thumbnail is saved for previews; the full image can be opened from the card.
  Different PDF/PPTX metadata does not affect the normalized visual rendering.
- **Exact Match:** SHA-256 of the full normalized RGB pixels plus
  whitespace-normalized extracted text is identical. Case, numbers and labels
  in the extracted text are retained. This means identical normalized rendering
  and text, not identical original PowerPoint XML or necessarily identical hidden
  presentation metadata. Pixel equality alone cannot promote changed text to exact.
- **Similar — Review Required:** a 64-bit perceptual hash matches closely enough.
  The hash uses a low-frequency 8 × 8 DCT of a 32 × 32 grayscale render, implemented
  using the existing NumPy dependency. The score is
  `100 × (1 − Hamming distance / 64)`. Similarity defaults to **90%**; configure
  `SLIDE_SIMILARITY_THRESHOLD` from 0 to 100 in `backend/.env` and restart the backend.
  A 100% perceptual score alone is still only Similar when the exact hashes differ.
- **Unique:** no slide in another completed presentation meets either rule.
  Slides are never matched against their own source presentation.
- Summary exact/similar/unique counts classify each selected slide once, preferring
  Exact if any exact candidate exists. A candidate selector exposes all its matching
  slides and their actual pair classifications. Workspace totals count completed
  presentations/slides. Review changed numbers, text, technical diagrams and colors;
  perceptual similarity is a heuristic and does not establish equivalent information.

No AI models, embeddings, vector database or cloud conversion service are used.
Fonts and the LibreOffice version can affect PPTX layout, so process compared decks
in the same environment. The fixed render/hash recipe is versioned internally;
changing it requires deliberate reindexing of previously cached slides.

### Storage, configuration and setup

Original files are retained unchanged. Generated images live under
`UPLOAD_DIR/slides/<file-id>/<analysis-attempt>/`. Hashes, paths, timestamps and
page text reuse `document_pages`, with its existing file relationship. Jobs use
`processing_jobs` with type `presentation_analysis`. Metadata is committed only
after every page succeeds; failure removes only that attempt's generated files.

Repeated slides identify **potential reuse opportunities**. No byte savings are
calculated: cached preview images are analysis artifacts, not a concrete storage
replacement for the original presentation. Nothing is deleted or deduplicated on disk.

The Docker backend installs LibreOffice Impress. For local Python execution,
install LibreOffice Impress and ensure `libreoffice` is on PATH (or set
`LIBREOFFICE_BINARY`). Optional environment settings:

```dotenv
SLIDE_SIMILARITY_THRESHOLD=90
PRESENTATION_MAX_SLIDES=500
PRESENTATION_RENDER_TIMEOUT_SECONDS=120
LIBREOFFICE_BINARY=libreoffice
```

Presentation uploads reuse `MAX_UPLOAD_BYTES` (the existing PDF upload limit).
PPTX packages are additionally limited to 10,000 ZIP members and 512 MB of declared
uncompressed content. Processing is bounded to one rendered page in memory at a time.

For an existing database, apply the additive migration before starting the new code:

```sh
docker compose up -d postgres
docker compose exec -T postgres psql -v ON_ERROR_STOP=1 -U my -d restore < database/migrations/006_slide_comparison.sql
docker compose up -d --build
```

Do not remove volumes. Fresh databases include the columns through `01_schema.sql`.
The migration is repeatable and does not alter existing text, file records or videos.

### API and verification

- `POST /presentations/upload`: streamed PDF/PPTX upload; returns a queued record (202).
- `GET /presentations` and `GET /presentations/{id}`: saved files and actual job states.
- `POST /presentations/{id}/analyze`: queue an existing PDF/PPTX or retry a failed
  attempt. Completed and already-queued work is reused, not duplicated.
- `GET /presentations/{id}/comparison`: current cached cross-presentation matches,
  classifications, pair scores and summaries. Originals are not reopened.
- `GET /presentations/slides/{id}/image?thumbnail=true`: stored preview; use
  `thumbnail=false` for full resolution. Only committed generated images can be served.

Tests generate isolated PDF/PPTX fixtures. Database/API tests require
`TEST_DATABASE_URL` and create/drop only their own random schemas. The real PPTX
conversion test requires LibreOffice; the complete suite can run inside the backend
image with test dependencies. Frontend checks: `npm --prefix frontend test` and
`npm --prefix frontend run build`.

Verified for this feature: **210 backend tests passed** inside the LibreOffice/FFmpeg
image against isolated PostgreSQL schemas, **6 frontend tests passed**, and the
frontend production build succeeded. Browser checks used real isolated PDF/PPTX
uploads to verify background conversion, exact/similar/unique counts, image serving,
filters, candidate selection, paging, caching, Files/Duplicates navigation, PPTX
search labels, deep links, and 320px/390px layouts. A final read-only check of the
running app confirmed existing file metadata, extracted text and transcripts
were preserved. No test fixtures were uploaded into the development database.

## MP4 visual transcripts

Open a completed recording under **Video Transcription** and select **Visual
Transcript**. Images appear above the speech associated with them; select an
image to open it at its saved resolution. **Transcript** retains the existing
readable text, search links, and text download. Existing recordings have an
**Extract visuals** button; newly transcribed recordings queue visual analysis
automatically. Refreshing reuses saved results, and failed analysis can be retried
without retranscribing speech or changing the original recording.

The existing single background worker handles `video_visuals` jobs after speech
transcription. FFmpeg decodes incrementally into fixed-size RGB frame buffers;
only representative JPEG files and bounded metadata are retained. Images are
letterboxed to 1280 × 720 and compressed at JPEG quality 80. Low-detail/blank
frames are discarded. Consecutive near-duplicates are skipped using the existing
64-bit perceptual hash, and returning to an earlier visual reuses its image file.
Images live under `UPLOAD_DIR/visuals/<file-id>/<attempt>/`; the additive
`video_frames` table records intervals, hashes, file sizes and internal paths.
The API serves only completed images inside the generated-visuals directory.

Optional `backend/.env` settings (restart the backend after editing):

```dotenv
VISUAL_SAMPLE_INTERVAL_SECONDS=5
VISUAL_HASH_DISTANCE=6
VISUAL_MAX_FRAMES=300
```

The interval accepts 1–60 seconds; hash distance accepts 0–64 differing bits
(lower retains more changes). The positive frame cap bounds stored intervals
and image metadata even during long demonstrations. Once the cap is reached,
subsequent speech remains visible without images. `MEDIA_TIMEOUT_SECONDS`
(default 3600) also limits a visual-analysis attempt. The worker processes one
job at a time; it never loads an entire MP4 into RAM. Visual analysis has its
own status, so speech remains readable when image extraction fails or a worker
restart interrupts it. Failed attempts clean up their generated images.

Each speech segment is assigned once to the image interval with the greatest
positive overlap; equal overlaps select the earlier image. Segments crossing
boundaries are never copied into multiple sections. Uncovered speech is retained,
and visuals displayed during silence remain visible. Timestamps are relative to
the beginning of the recording and reflect sampled boundaries: a change shorter
than the sampling interval can be missed. This is a visual-change heuristic,
not slide recognition: cameras, animations and screen demonstrations can produce
extra images, small text changes can be missed, and low-detail useful content
may be discarded. No PDF/PPTX source matching or new AI model is involved.

Potential storage savings now includes actual JPEG bytes from disk plus the
exact text-download bytes, counting a reused image once. While visual processing
is pending, failed, or an output image is missing, the total is unavailable.
Original uploads remain retained and unchanged.

For existing installations, apply this repeatable migration before running the
new backend (do not remove database volumes):

```sh
docker compose up -d postgres
docker compose exec -T postgres psql -v ON_ERROR_STOP=1 -U my -d restore < database/migrations/007_video_visuals.sql
docker compose up -d --build
```

API additions:

- `GET /videos/{id}/visual-transcript`: persisted visual status and ordered
  image references, timestamps and associated speech, with no filesystem paths.
- `POST /videos/{id}/visual-transcript`: queue older recordings or retry failed
  visual analysis; queued, processing and completed requests are idempotent.
- `GET /videos/{id}/visuals/{frame_id}/image`: safely retrieve a committed JPEG.

Tests in `backend/tests/test_video_visuals.py` cover static and distinct screens,
blank recordings, near duplicates and revisited images, corrupted media, bounded
reads, timestamp boundaries and gaps, silent sections, automatic queueing,
image retrieval, real byte measurements, failure cleanup and restart recovery.
The real decoder test requires FFmpeg; database tests use the disposable schema
fixture described above. Run the backend suite plus the existing frontend tests
and production build before deployment.

Verified for visual transcripts: **228 backend tests passed**, **6 frontend tests
passed**, and the frontend production build succeeded. Chromium checks against
an isolated API/database exercised real FFmpeg-generated images, speech-only
fallback, visuals during silence, legacy analysis and failed-job retry, image
expansion, storage measurements, refresh, and 320px/390px layouts. The additive
migration was applied to the local Docker app without resetting volumes; existing
file metadata, extracted page text and speech segments matched their pre-migration
fingerprints.

### Visual transcript timestamps and downloads

**Show timestamps** controls the visual intervals and speech timestamps. The
choice is shared with the regular Transcript view. With timestamps hidden,
speech under each image reads as a continuous paragraph.

**Download with pictures (.html)** saves one self-contained HTML document with
embedded JPEGs and matching text. Open it offline in a browser or use the
browser's Print action. The export respects the timestamp checkbox and requires
completed visual processing; missing or unsafe image files return an error before
the download begins. Recordings without images can download a text-only HTML
document. The existing plain-text download remains available.

`GET /videos/{id}/visual-transcript/download?timestamps=false` returns the HTML
attachment; use `timestamps=true` to include times. Image encoding is streamed
in fixed chunks. HTML/base64 adds formatting overhead; the existing storage
comparison continues measuring the underlying text and JPEG content, without
counting this optional export format twice. No additional migration or dependency
is required.

Verified for this update: **55 backend tests** covering exports, visual processing
and transcription, **6 frontend tests**, the production build, and Chromium checks
of actual downloads, offline images, both timestamp settings, shared preferences,
speech-only fallback, and 320px/390px controls.
