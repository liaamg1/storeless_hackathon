# ReStore frontend

Vue 3, TypeScript, Vite and Vue Router, with Lucide icons (`@lucide/vue`). The navy,
blue and neutral palette is an Ericsson-inspired hackathon concept; no official
Ericsson assets or logo are used. The redesign changes only frontend code.

## Run and verify

```sh
npm install
npm run dev
npm test
npm run build
npm run preview
```

Use Node 22.18+ or Node 24. `npm test` runs six file-management tests using Node's
built-in test/assert modules and TypeScript stripping. `npm run build` runs
`vue-tsc -b` and Vite's production build. No component or test framework was added.

The API defaults to `http://localhost:8000`; set `VITE_API_URL` to override it.
The backend permits the existing frontend origin `http://localhost:5173`.
Production hosting must return `index.html` for frontend paths so direct links,
refresh, and browser history work. API requests keep using their existing origin.
For the Docker setup, rebuild only the frontend after UI changes:

```sh
docker compose up -d --build --no-deps frontend
```

## Navigation and workflows

| Route            | Purpose                                                                |
| ---------------- | ---------------------------------------------------------------------- |
| `/overview`      | File counts, recent files, recent recording jobs, duplicate savings    |
| `/files`         | Central workspace: filter, sort, page through files and open details   |
| `/search`        | Search PDF/PPTX content and video transcripts with the existing API    |
| `/slides`        | PDF/PPTX rendering, cached slide comparison and review filters         |
| `/duplicates`    | Scan exact duplicates, inspect expandable groups and potential savings |
| `/extract`       | Existing PDF upload, metadata, page accordion and page navigation      |
| `/transcription` | Existing MP4 upload, job polling, readable transcripts and downloads   |
| `/storage`       | Select a file and display its existing storage comparison              |

`/` opens Overview. Unknown routes retain the Files fallback. The sidebar collapses
on desktop and becomes a native modal navigation drawer below 900px. The header
opens the unified upload dialog. Ctrl/Cmd+K navigates to Search and focuses its
input. Dialogs support keyboard navigation, focus trapping and Escape dismissal.

Files are searched by filename, filtered by type/status, sorted by name/size/date,
and paged in groups of 12. File names are truncated in tables with full names in
tooltips and the details drawer. The drawer has the full selectable SHA-256 hash,
a clipboard action and links to existing results. There are no bulk controls or
deletion actions. Recording lists have a filename filter and pages of eight.

Unified upload dispatches PDFs to `POST /files/upload` and MP4s to
`POST /videos/upload`. It shows the actual operation state, never an invented
progress percentage. PDF upload returns extracted pages; video upload returns a
job and transcription continues in the background. Existing route-specific
upload forms remain functional. Upload failures keep the dialog open for retry;
success navigates to the result and shows a dismissible notification.

Existing links remain supported:

- `/extract?file=4` opens saved document text.
- `/extract?file=4&page=2` opens, focuses and scrolls to that page.
- `/transcription?file=7` follows the existing job and opens the saved transcript.
- `/transcription?file=7&segment=12` highlights and focuses a search passage.
- `/transcription?file=7&view=status` expands the processing information.
- `/storage?file=7` opens the existing per-file storage comparison.

The transcript appears before secondary recording information. Timestamps are
optional in the reader; the compact text download stays readable. Processing and
storage information can be expanded without leaving the result. Search text is
always interpolated as text, never inserted with `v-html`.

## Data scope and unavailable states

- File metadata comes from `GET /files`; recording/job states use the existing
  video APIs. A failed status request does not prevent browsing file metadata.
- The file-list API does not expose PDF processing state. PDFs show **Available**,
  not an invented completed status. Opening details retrieves the actual extraction
  state through the existing pages endpoint. Missing recording status is **Unknown**.
- Overview's potential savings KPI is explicitly **exact duplicate copies**, from
  `GET /duplicates`. It is not combined with optimized-output savings, which could
  overlap. Failed measurements display unavailable rather than fabricated numbers.
- Storage Savings reuses `GET /files/{id}/storage-savings`. Original uploads remain
  retained. Missing images/outputs keep the backend's unavailable/not-generated states.
- Search filters apply to the existing API's returned result set (up to 20 matches),
  and the UI states that scope. They do not imply server-side exhaustive filtering.
- Files and video lists are fetched in full and filtered/paged locally. This fits
  the hackathon API; larger collections would benefit from future server paging.
- No backend endpoints, PostgreSQL schema, upload validation, transcription worker,
  extraction logic, or API contracts were changed for this redesign.

## Component ownership

- `components/layout/`: shared app shell, sidebar and header.
- `components/shared/`: status badges and empty states.
- `components/files/`: table, filters, details drawer, unified upload and PDF readers.
- `components/search/`, `duplicates/`, `transcription/`, `storage/`: existing feature UIs.
- `composables/useWorkspace.ts`: independent file/video loading with partial failures.
- `utils/files.ts`: typed file classification, filtering, sorting and destinations.
- `composables/useDocument.ts` and `useTranscription.ts`: existing extraction state and
  sequential job polling, including cancellation on unmount and terminal states.
- `services/` and `types/`: existing API requests and response contracts.
- `style.css`: shared tokens, compact controls, application layout and responsive rules.
- `router/index.ts`: route registration, page titles and retained deep links.

To add a page, register the route with its title in `router/index.ts`, then add an
item to the relevant group in `AppSidebar.vue`.

## Redesign verification

Executed TypeScript/production build checks and the six Node unit tests. Headless
Chromium workflow checks also exercised navigation/active state, sidebar collapse,
filter combinations, sorting, pagination, long filenames, metadata drawers,
PDF/MP4 uploads, upload errors/retry, video polling, transcript download, optional
timestamps, mixed search/filtering, matching page/segment links, duplicate scans,
refresh/deep links, loading/empty/error states and mobile navigation.

Controlled API responses were used for upload and error paths, without modifying
application data. Separate read-only checks against the live API covered actual
files, extraction results, transcript downloads, clipboard copying, search,
duplicates, storage comparisons, and all seven routes at 320px and 390px. Existing
file metadata was identical before and after these checks. Browser tooling was
installed temporarily outside the repository; it is not an application dependency.

## Slide Comparison

`/slides` is the presentation workspace. It uploads PDFs/PPTX, polls existing
background jobs, shows exact/similar/unique summaries, filters and pages slide
cards, and compares cached thumbnails side by side. Candidate selection changes
the displayed pair's classification; a matching pHash alone is never labelled Exact.
Deep links use `/slides?file=<id>`. Existing PDFs can be analyzed without re-upload.

`services/presentations.ts`, `types/presentation.ts` and `usePresentations.ts`
separate API communication/state from `SlideComparisonView.vue` and
`components/presentations/SlideComparisonCard.vue`. Files now fetch actual
presentation statuses when available, recognize PPTX, and route its drawer action
to Slide Comparison. PDF files retain their extracted-text action and gain a
Compare slides action. Whole-file duplicate detection remains unchanged.

The root README documents migration, LibreOffice setup, thresholds and the precise
meaning of exact and heuristic matches. No deletion or byte-savings estimate is
performed by slide comparison.
