# ADR 012: React Native (Expo) for the Mobile Client

## Status

Accepted (2026-08-16)

## Context

PudimJobs needs a mobile client that mirrors the Angular web UI for use on a
phone. Requirements:

- Android-first, with iOS as a later target
- Reuse the existing FastAPI backend over HTTPS `/api` (JWT auth)
- Parity with the web: job search, job detail, CV editor (PDF/DOCX import and
  PDF export), application kanban, sources (+ per-source auth), alerts,
  notifications, and the admin panel
- i18n parity: the same `en` / `pt-BR` dictionary as the web
- A token held in the OS keychain, not plain storage

Options considered:

1. **Expo (managed React Native)** — TypeScript, fast iteration via Expo Go,
   first-class access to secure-store, document picker, file-system, sharing,
   and localization without custom native code
2. **Bare React Native CLI** — full native control, but every capability above
   requires manual native module wiring and native builds
3. **Flutter** — good mobile DX but a second language/runtime and no reuse of
   the web's TypeScript types or i18n dictionary
4. **PWA / WebView wrapper** — trivial to ship, but poor native UX (offline,
   notifications, keychain), which defeats the purpose

## Decision

Use **React Native via Expo (SDK 57)** with TypeScript, React Navigation
(drawer + native stack), TanStack Query for server state, Zustand persisted to
`expo-secure-store` for the session, react-hook-form + zod for forms, and
Lucide (react-native-svg) for icons. The i18n dictionary is **generated** from
the web frontend (`frontend/src/app/services/i18n.service.ts`) so web and
mobile strings never drift.

## Consequences

### Positive

- **Fast iteration** — Expo Go + hot reload for the Android-first workflow
- **API parity by construction** — the typed `src/api/*` layer mirrors the
  FastAPI routers/schemas 1:1 and is reviewed against them
- **Single i18n source** — `mobile/scripts/extract-dictionary.js` regenerates
  `mobile/src/i18n/dictionary.ts` from the Angular dictionary
- **Design-token parity** — `src/theme/tokens.ts` ports `styles.scss` 1:1,
  including dark mode
- **Secure by default** — JWT + profile live in the Android/iOS keychain
- **CI-able** — typecheck, lint, Jest, and an Android bundle export all run
  headlessly (`.github/workflows/mobile-ci.yml`)

### Negative / Risks

- **Expo coupling** — SDK upgrades and config plugins (e.g.
  `expo-build-properties`) gate native behavior; bleeding-edge native modules
  may need a development build rather than Expo Go
- **Android-only today** — iOS config exists but is untested
- **No offline-first persistence** — unlike the web PWA, the app relies on the
  in-memory React Query cache and requires connectivity
- **Untested on real devices** — multipart CV upload, PDF share, and the
  cleartext-HTTP dev backend need device smoke tests before release

## Alternatives Not Selected

| Option | Reason for Rejection |
| ------ | ------------------- |
| Bare React Native CLI | All required native modules (secure-store, document picker, file system, sharing, localization) would have to be wired manually; slower iteration |
| Flutter | Second language/runtime; no reuse of TypeScript types or the web i18n dictionary |
| PWA / WebView wrapper | Poor native UX (offline, notifications, keychain) — defeats the mobile-client purpose |
