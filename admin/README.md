# Admin Frontend (Foundation)

This folder contains the minimal internal admin frontend app for upcoming Phase 20 support UI work.

## Run locally

```bash
cd admin
npm install
npm run dev
```

## Build

```bash
npm run build
npm run preview
```

## Backend API base URL

Set `VITE_API_BASE_URL` in `admin/.env` (see `admin/.env.example`).

Example:

```bash
VITE_API_BASE_URL=http://localhost:8000
```
