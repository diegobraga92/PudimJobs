# Frontend — PudimJobs

Angular 17 standalone-component application. Consumes the FastAPI backend under `/api`.

## Development server

Run `ng serve` for a dev server. Navigate to `http://localhost:4200/`. The application will automatically reload if you change any of the source files.

## Build

Run `ng build` to build the project. The build artifacts will be stored in the `dist/` directory.

## Design system

The UI is built on a token-driven design system defined in `src/styles.scss`:

- **Design tokens** — CSS custom properties for colors, typography, spacing, radii,
  shadows, transitions, and z-index (`--color-primary`, `--space-4`, `--radius-md`, …).
  Components consume tokens instead of hardcoding values so themes stay consistent.
- **Shared classes** — `.btn` (+ `.btn-primary`, `.btn-ghost`, `.btn-danger`, …),
  `.panel`, `.card`, `.tag`, `.badge`, `.input`, `.select`, `.textarea`, `.table`,
  `.alert`, `.empty-state`, `.skeleton`, `.modal-*`, `.toast`, plus spacing/flex utilities.
- **Icons** — `app-icon` (`src/app/shared/icons/`) renders inline stroke SVGs
  (Lucide-style paths, MIT). Add new icons by extending `icon-name.ts` and the
  `ICON_MARKUP` registry — no external icon package needed.
- **Toast notifications** — inject `ToastService` and call
  `success() / error() / warning() / info()`. The viewport is mounted once in `app-root`.
- **Confirm dialogs** — replace `window.confirm()` with
  `await confirmService.confirm({ title, message, confirmLabel, destructive })`.
- **Accessibility** — focus-visible rings, skip-to-content link, ARIA labels on
  interactive elements, `role="dialog"` modals with Escape handling.

### Themes

Dark mode is fully supported. A toggle lives in the sidebar footer; the choice
is persisted to `localStorage` (`pudimjobs_theme`) and falls back to the OS
`prefers-color-scheme`. All tokens in `src/styles.scss` have a
`[data-theme='dark']` override.

### Drag-and-drop pipeline

The application kanban uses Angular CDK drag & drop (`@angular/cdk`). Cards can
be dragged between the five columns; the new status is persisted through
`PUT /api/applications/:id` and reverted with a toast on failure.

### CV preview

The Master CV editor has an Edit / Preview toggle. Preview renders the live
form state as an A4-style document (`app-cv-preview`), so edits appear
instantly as they are typed.

### Admin tabs

The admin panel is organized into five lazy-loading tabs: Overview, Sources,
Quality, Dead-Letter Queue, and Audit Log.

### Pagination

The Jobs list paginates client-side (12 per page) with Previous/Next controls
and a "x–y of n" label. The API returns the full per-user list today; if the
backend later adds server-side pagination, swap `pagedJobs` for query params.

### Onboarding

New users with an empty Jobs list see a three-step welcome panel linking to
Sources, Master CV, and the Applications pipeline. Dismissing it stores a flag
in `localStorage`.

### Progressive Web App

The app is installable and works offline:
- `@angular/service-worker` registered via `provideServiceWorker` (production only)
- `ngsw-config.json` caches the app shell (prefetch) and API responses (freshness)
- `manifest.webmanifest` + SVG app icons enable "Add to Home Screen"

### Component style budget

`angular.json` enforces an `anyComponentStyle` budget (4 kB warning / 8 kB error).
Keep page shells' custom SCSS lean; move anything reusable into the shared classes
in `src/styles.scss`.

## Running unit tests

Run `ng test` to execute the unit tests via [Karma](https://karma-runner.github.io).

## Further help

To get more help on the Angular CLI use `ng help` or go check out the
[Angular CLI Overview and Command Reference](https://angular.io/cli) page.

