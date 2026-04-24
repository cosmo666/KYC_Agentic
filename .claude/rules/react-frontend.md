# React Frontend Conventions

## Stack

- **React 19** via **Create React App** (`react-scripts 5.0.1`) — not Next.js, not Vite, no shadcn/ui (despite what the report says — the report describes the *intended* stack)
- **Plain CSS** in `App.css` and `index.css` — no Tailwind, no CSS modules, no styled-components
- **`fetch` API** for HTTP — no Axios, no React Query
- **Local component state** with `useState` / `useRef` — no Redux, no Zustand
- **Webcam capture** via the native `navigator.mediaDevices.getUserMedia` API + a `<video>` and `<canvas>` ref pair

## Project structure

```text
kyc-frontend/
├── public/
├── src/
│   ├── App.js          # Single-file SPA — chat panel, drag-drop upload, webcam, verdict
│   ├── App.css         # All component styles
│   ├── index.js        # ReactDOM root
│   └── index.css       # Global resets
├── package.json
└── README.md           # CRA boilerplate (project README is at the repo root)
```

## Single-file SPA — current state

The whole UI lives in `App.js` (~34 KB). This is intentional for the POC, but **don't let it grow much further** — split when it crosses ~600 lines. Suggested split when the time comes:

```text
src/
├── App.js                          # Stepper + routing between phases
├── api.js                          # All fetch calls in one place (currently inline in App.js)
├── hooks/
│   └── useWebcam.js                # Encapsulate getUserMedia + canvas snapshot
└── components/
    ├── DocumentUpload.js           # Drag-drop + file input + preview
    ├── ChatPanel.js                # Messages, input, suggestions
    ├── SelfieCapture.js            # Webcam preview + capture button
    └── KycVerdict.js               # Decision card + flag list
```

## API integration

- **Base URL**: hardcoded as `const API_URL = "http://127.0.0.1:8888"` in `App.js`. **This is wrong** — the backend actually runs on `9090` (per `backend/config.py`). Fix it to `http://127.0.0.1:9090` or read from an env var (`process.env.REACT_APP_API_URL`).
- **All requests use `fetch`** with `FormData` for multipart uploads.
- **Always handle the error path**: `if (!response.ok) throw new Error(errData?.detail || \`Server error (${response.status})\`)`.
- The frontend currently calls `POST /upload-doc` (root alias), `POST /chat/`, `POST /verify-face`, `POST /validate/`. If a route name changes in the backend, this file must change too.

## State pattern

- **Stepper-driven UI**: `currentStep` (1–4) controls which screen is visible (Aadhaar upload → PAN upload → selfie → review).
- **Results accumulate** in a `results` array (one entry per uploaded document).
- **Chat is independent** of the stepper — it stays open across steps so the user can ask questions at any time.
- **Webcam refs** (`videoRef`, `canvasRef`, `streamRef`) — always stop the stream (`streamRef.current.getTracks().forEach(t => t.stop())`) when the user navigates away or captures a selfie. Memory-leak prone if missed.

## Styling

- **`App.css` is the only stylesheet** for components. Keep selectors flat and class-based (`.upload-zone`, `.chat-panel`, etc.) — no nesting depth, no `:has()` tricks for the POC.
- **No design system / no shadcn/ui** despite the report. If you introduce one later, do it in a single PR and migrate components in batches.
- **Mobile-first**: test at 360px wide. The KYC users this targets are predominantly mobile-first.
- **Hindi/English support** — the assistant's text comes from the backend's `chat` response. The UI labels (`STEPS = [...]`) are English-only today; localise via a simple lookup dict before adding more languages.

## Accessibility

- Webcam capture must have a **visible permission prompt** — never start the stream silently on page load.
- Drag-and-drop zones must also accept a **standard file input click** (the current code does this — keep it that way).
- Verdict text should be **screen-reader friendly**: avoid emoji-only status indicators; pair them with text ("✅ Approved", not just "✅").

## Anti-patterns to avoid

- ❌ Mutating the `API_URL` per environment by hand — read from `REACT_APP_API_URL` env var so dev / staging / prod don't require code edits.
- ❌ Storing extracted Aadhaar / PAN values in `localStorage` or `sessionStorage` — keep them in component state only; they vanish on reload by design.
- ❌ Forgetting to stop the webcam stream — leads to the camera light staying on after the user moves on.
- ❌ Adding a router (`react-router`) for one or two screens — the stepper handles it.
- ❌ Pulling in a UI kit "just for one component" — every dependency is a 100KB+ bundle hit.
- ❌ Calling backend endpoints directly from deeply-nested components — funnel through a single `api.js` once the file is split.
