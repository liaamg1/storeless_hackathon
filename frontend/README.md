# ReStore frontend

Vue 3, TypeScript, Vite, and Vue Router. See the [project README](../README.md) for
backend setup, API documentation, and feature limitations.

Run `npm install` and `npm run dev` from this directory. The API defaults to
`http://localhost:8000`; override it with `VITE_API_URL`. Run `npm run build` for
TypeScript checks and a production build. `npm run preview` serves that build.

## Navigation and feature ownership

| Route | View | Feature |
| --- | --- | --- |
| `/files` | `views/FilesView.vue` | Retrieve, refresh, and open saved files |
| `/extract` | `views/PdfExtractionView.vue` | Upload PDFs and view saved metadata/page text |
| `/search` | `views/DocumentSearchView.vue` | Search saved text and open matching pages |
| `/duplicates` | `views/DuplicatesView.vue` | Scan stored hashes and review grouped files/potential savings |
| `/transcription` | `views/VideoTranscriptionView.vue` | Upload MP4s, follow jobs, reopen/download saved transcripts |

`/` redirects to `/files`. Unknown paths also redirect to `/files`.

`router/index.ts` defines the routes using HTML5 history. `main.ts` installs the
router. `App.vue` contains the shared header, `AppNavigation`, and `RouterView`.
Navigation uses real `RouterLink` anchors; Vue Router applies the active-link
class and `aria-current="page"` automatically.

Opening a saved file navigates to `/extract?file=4`. Search results navigate to
`/extract?file=4&page=2`. The extraction view watches these query parameters so
initial navigation, refresh, and browser back/forward all load the selected saved
document. The same page viewer marks, scrolls to, and focuses the matching page.
Returning to Files reloads the list, including newly uploaded PDFs. Search form
state is local to the search page and resets when leaving that page.

Vite development and preview servers support direct URLs. When deploying the
production `dist/` directory, configure the frontend web server to serve
`index.html` for frontend routes such as `/files`, `/extract`, `/search`, `/duplicates`, and `/transcription`.
Keep backend API traffic directed to its existing API origin. This fallback is
required for direct links and refresh with HTML5 history.

## Where changes belong

- `components/AppNavigation.vue`: navigation labels, links, and active/hover styles.
- `components/files/`: existing upload, file table, metadata, and extracted-page components.
- `components/search/`: existing search form, request states, and result display.
- `components/duplicates/`: summary statistics and grouped file tables.
- `components/transcription/`: video picker, backend job stages, and transcript viewer.
- `composables/useTranscription.ts`: saved recordings, upload state, and polling lifecycle.
- `services/transcription.ts` and `types/transcription.ts`: typed video/job/transcript APIs.
- `utils/formatTimestamp.ts`: millisecond timestamp display.
- `views/DuplicatesView.vue`: scan on entry, manual refresh, loading/empty/error states.
- `services/duplicates.ts` and `types/duplicate.ts`: typed duplicate API requests/responses.
- `utils/formatBytes.ts`: decimal byte-unit formatting for duplicate results.
- `composables/useFiles.ts`: file list loading and refresh state.
- `composables/useDocument.ts`: upload requests and saved-document state, independent of routing.
- `services/api.ts` and `services/search.ts`: existing HTTP requests and API errors.
- `types/`: typed API responses.
- `style.css`: shared layout and typography.

Views coordinate navigation. Components receive typed props and emit actions;
composables own reactive state. API services remain independent of Vue Router.
Snippets must remain ordinary text interpolation, never `v-html`.

## Add another feature tab

1. Create a focused view under `src/views/`, reusing components and services.
2. Register its path, name, and component in `src/router/index.ts`.
3. Add a named `RouterLink` in `src/components/AppNavigation.vue`.

The shared layout and active-tab indicator then work without changes to `App.vue`.

## Verification

Run `npm run build` to execute `vue-tsc -b` and Vite's production build. There is
currently no frontend unit-test framework. Browser checks should cover root
redirection, all navigation links and active states, direct URLs, refresh,
back/forward, file retrieval states, upload feedback, search feedback, and links
from files/search to the selected extracted page.

Verified with the production build in headless Chromium using controlled API
responses: root and unknown-route redirects, links and active states, direct URLs,
refresh, back/forward, file loading/empty/error states, upload success/error/loading,
search results/empty/error states, matching-page focus, query history, missing files,
and a 320px-wide layout. These browser checks used temporary tooling outside the
repository and did not change the backend or PostgreSQL.

The Duplicates page reads `GET /duplicates`; it does not reprocess PDFs or alter
files. Summary savings are potential. Refresh errors hide old estimates rather than
showing them as successful scan results.

Duplicates browser checks also compared the displayed groups and summary against
a live PostgreSQL-backed API response and confirmed that manual scans issue fresh
GET requests. Controlled responses exercised empty results,
failures, and recovery. Existing file metadata was identical before and after the
live scans, and the original tabs passed their production-browser regressions.

Video selections use `/transcription?file=12`. Opening a saved recording reads its
existing job and transcript; it never creates another job. Polling is sequential,
stops on terminal states or unmount, and offers Retry status after a temporary
request error. The backend starts its transcription worker automatically;
see the project README for supervision and optional standalone-worker settings. MP4 entries in Files
open this viewer instead of the PDF page. Download fetches the stored plain-text
export, so no media processing runs during download.
