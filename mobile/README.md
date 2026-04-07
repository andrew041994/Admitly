# Admitly Mobile (Phase 1 Foundation)

Expo + React Native mobile foundation for the user-facing Admitly app.

## Quick start

```bash
cd mobile
npm install
npm run start
```

## Environment

Set the API URL with Expo public env vars:

```bash
EXPO_PUBLIC_API_BASE_URL=http://localhost:8000 npm run start
```

Fallback config is defined in `app.json` under `expo.extra.apiBaseUrl`.

## Included in Phase 1

- Expo TypeScript app shell
- EAS build scaffolding (`eas.json`)
- Root navigation for boot/signed-out/signed-in states
- Session bootstrap scaffold with AsyncStorage
- API client and env configuration scaffolding
- Admitly black/gold theme tokens and reusable UI primitives
- Branded placeholder screens for upcoming phases

## EAS readiness

The app includes package IDs and a baseline `eas.json` profile set (`development`, `preview`, `production`) so it can be extended for real CI/CD build pipelines in later phases.
