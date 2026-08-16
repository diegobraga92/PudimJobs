# PudimJobs Mobile (React Native / Android)

A React Native client for PudimJobs that mirrors the Angular web UI
(`frontend/`). Android-first; built with **Expo SDK 57**.

## Status

| Area                                                                                        | Status  |
| ------------------------------------------------------------------------------------------- | ------- |
| Scaffold, design tokens, i18n, auth, drawer shell                                           | ✅ Done |
| Login screen                                                                                | ✅ Done |
| Jobs list + job detail (search, add, hide, pipeline badges, tailor, parse)                  | ✅ Done |
| Applications kanban (5 columns, move status, delete)                                        | ✅ Done |
| Master CV editor (edit/preview, import PDF/DOCX, export PDF, version history, tailored CVs) | ✅ Done |
| Sources (CRUD + per-source auth panel)                                                      | ✅ Done |
| Alerts (CRUD + active toggle)                                                               | ✅ Done |
| Notifications (list, mark read / all read)                                                  | ✅ Done |
| Admin panel (overview, sources, quality, DLQ, audit, LLM tabs)                              | ✅ Done |

Remaining polish: e2e smoke test on a device/emulator against a running backend,
and the Android release build (EAS).

## Stack

- **Expo SDK 57** (React Native 0.86, React 19, TypeScript strict)
- **React Navigation 7** — native-stack + drawer (mirrors the web sidebar)
- **TanStack Query** for server state; **Zustand** (persisted to the keychain
  via `expo-secure-store`) for the session
- **react-hook-form + zod** for forms
- **react-native-svg / lucide-react-native** icons (same Lucide set as the web)
- **expo-document-picker / expo-file-system / expo-sharing** for CV import & PDF
- Design tokens ported 1:1 from `frontend/src/styles.scss` (light + dark)
- i18n dictionary **generated** from the web frontend (en/pt-BR) — see below

## Getting started

```bash
cd mobile
npm install

# Point the app at your backend:
cp .env.example .env   # set EXPO_PUBLIC_API_URL to your LAN IP if needed

npm run android        # or: npm start
```

The API base URL defaults to `http://10.0.2.2:8000` (Android emulator →
host). Override with `EXPO_PUBLIC_API_URL` for a physical device.

### Backend reachability

The FastAPI backend is **not exposed on a host port** in `docker-compose.yml`
by default. For mobile development we added an optional binding:

```yaml
backend:
  ports:
    - '${PJ_BACKEND_PORT:-8000}:8000'
```

Native apps don't need CORS (that's browser-only). Note that the backend's CORS
allow-list defaults to `localhost:4200/9400` — if you open the API's Swagger UI
at `http://<LAN-IP>:8000/docs` from a browser on another host, add that origin
to `PJ_CORS_ORIGINS` in `.env`.

### Auth & smoke testing

- The dev seed user is **`admin@pudimjobs.dev` / `admin123`** (see
  `backend/app/seed.py`) — an `admin` role, so the Admin panel is visible.
- JWTs expire after **24 hours** (`access_token_expire_minutes`). When a token
  expires the app clears the session and shows a "session expired" notice on
  the login screen.
- Login is rate-limited to 5/minute; hitting the limit shows a "too many
  attempts" message instead of a misleading "invalid credentials" error.

## Regenerating the i18n dictionary

Strings are extracted verbatim from the Angular frontend so web and mobile
never drift:

```bash
node mobile/scripts/extract-dictionary.js   # run from the repo root
```

## Checks

```bash
npm run typecheck   # tsc --noEmit
npm run lint        # eslint .
npm test            # jest
npm run format      # prettier --write .   (format:check = verify only)
npx expo export --platform android   # validate the production bundle
```

These checks (typecheck, lint, test, Android bundle export) run in CI via
`.github/workflows/mobile-ci.yml`.

## App icons

The launcher icon, splash logo, and Android adaptive icons are generated from
the web brand mark (`frontend/src/assets/icons/icon-512.svg`) by
`mobile/scripts/generate-icons.js` (uses `sharp`):

```bash
node mobile/scripts/generate-icons.js   # run from the repo root
```

## Layout

```
mobile/
├── App.tsx                  # providers + root navigator
├── src/
│   ├── api/                 # axios client + typed endpoints (mirrors the web services)
│   ├── components/          # ui kit, icons, toast, confirm, onboarding, layout
│   ├── hooks/               # TanStack Query hooks per domain
│   ├── i18n/                # generated dictionary + provider
│   ├── navigation/          # auth stack, drawer, jobs stack
│   ├── screens/             # Login, Jobs, JobDetail (+ admin/, all web screens)
│   ├── store/               # zustand session (keychain-backed)
│   ├── theme/               # design tokens + dark mode provider
│   ├── types/               # API types (mirrors the web services 1:1)
│   └── utils/               # dates, list parsing, PDF share
└── scripts/
    ├── extract-dictionary.js   # regenerate i18n from the web dictionary
    └── generate-icons.js       # regenerate app icons from the web brand mark
```
