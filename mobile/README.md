# PudimJobs Mobile (React Native / Android)

A React Native client for PudimJobs that mirrors the Angular web UI
(`frontend/`). Android-first; built with **Expo SDK 57**.

## Status

| Area | Status |
|------|--------|
| Scaffold, design tokens, i18n, auth, drawer shell | ✅ Done |
| Login screen | ✅ Done |
| Jobs list + job detail (search, add, hide, pipeline badges, tailor, parse) | ✅ Done |
| Applications kanban (5 columns, move status, delete) | ✅ Done |
| Master CV editor (edit/preview, import PDF/DOCX, export PDF, version history, tailored CVs) | ✅ Done |
| Sources (CRUD + per-source auth panel) | ✅ Done |
| Alerts (CRUD + active toggle) | ✅ Done |
| Notifications (list, mark read / all read) | ✅ Done |
| Admin panel (overview, sources, quality, DLQ, audit, LLM tabs) | ✅ Done |

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
    - "${PJ_BACKEND_PORT:-8000}:8000"
```

Native apps don't need CORS (that's browser-only).

## Regenerating the i18n dictionary

Strings are extracted verbatim from the Angular frontend so web and mobile
never drift:

```bash
node mobile/scripts/extract-dictionary.js   # run from the repo root
```

## Checks

```bash
npm run typecheck   # tsc --noEmit
npx eslint .        # lint
npx jest            # unit tests
npx expo export --platform android   # validate the production bundle
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
│   ├── screens/             # Login, Jobs, JobDetail (+ placeholders)
│   ├── store/               # zustand session (keychain-backed)
│   ├── theme/               # design tokens + dark mode provider
│   ├── types/               # API types (mirrors the web services 1:1)
│   └── utils/               # dates, list parsing, PDF share
└── scripts/extract-dictionary.js
```
