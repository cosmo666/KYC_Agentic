# React Frontend Conventions

## Stack

- **Vite 5** (NOT Create React App, NOT Next.js).
- **React 19** + **TypeScript 5.6**.
- **Tailwind 3** + **shadcn/ui primitives** in `src/components/ui/` (button, card, dialog, input, label, separator, textarea). HSL variables defined in `index.css`; light/dark via the `class` strategy.
- **Radix** primitives under the hood — `@radix-ui/react-dialog`, `react-tooltip`, `react-slot`, `react-separator`.
- **`react-easy-crop`** for the camera-capture crop UI.
- **`zod`** for validating every API response shape — see `src/api/schemas.ts`.
- **Native `fetch`** for HTTP — no Axios, no React Query.
- **Local state only** — `useState`, `useRef`, `useCallback`. No Redux, no Zustand, no React Context.
- **`sessionStorage`** for the session id (key `kyc.sessionId`). Cleared on Restart, lost on tab close — by design.
- **`lucide-react`** for icons.
- **Path alias `@/*` → `src/*`** (configured in `tsconfig.json` and `vite.config.ts`).

## Project structure

```text
apps/web/
├── Dockerfile                         # Multi-stage: node:20-alpine → nginx:alpine
├── nginx.conf                         # SPA fallback (try_files $uri /index.html)
├── index.html
├── package.json                       # Vite scripts: dev / build / preview / lint
├── postcss.config.js
├── tailwind.config.ts                 # shadcn-style HSL var theme; tailwindcss-animate plugin
├── tsconfig.json
├── vite.config.ts                     # @ alias, port 5173
└── src/
    ├── main.tsx                       # ReactDOM root + index.css
    ├── App.tsx                        # ChatShell + FaqDrawer
    ├── index.css                      # Tailwind layers + shadcn HSL vars (light + dark)
    ├── api/
    │   ├── client.ts                  # fetch helpers: sendChat, uploadDoc, captureImage, confirmDoc, getSession
    │   └── schemas.ts                 # zod schemas + inferred TS types
    ├── components/
    │   ├── chat/                      # ChatShell, MessageList, ChatInput, MessageBubble
    │   ├── widgets/                   # DocumentUploadWidget, EditableFieldCard, SelfieCamera, VerdictCard
    │   ├── camera/CameraCaptureModal.tsx
    │   ├── faq/FaqDrawer.tsx
    │   └── ui/                        # shadcn primitives
    ├── hooks/useSession.ts            # sessionStorage-backed session id
    └── lib/utils.ts                   # cn() helper (clsx + tailwind-merge)
```

## API integration (`src/api/client.ts`)

- **Base URL**: `import.meta.env.VITE_API_URL ?? "http://localhost:8000"`. The Docker build accepts `VITE_API_URL` as a build arg (see `apps/web/Dockerfile` and the compose `web` service).
- **All requests use `fetch`**; multipart (`uploadDoc`, `captureImage`) builds a `FormData`, JSON (`sendChat`, `confirmDoc`) sends `application/json`.
- **Every response is zod-parsed** through `handle(r, schema)` — never `await r.json()` directly without validating. If you add a new field on the server, update `schemas.ts` first or zod will throw.
- The 5 client functions match the 5 backend routes (`/chat`, `/upload`, `/confirm`, `/capture`, `/session/{id}`). Don't bypass `client.ts` from a component.

## State pattern

- **`ChatShell` owns the conversation.** Holds `messages` (array of `ChatMessage`), `busy` (in-flight indicator), and the optional `cameraTarget` for the modal. Uses the `useSession()` hook for the persisted id.
- **`useSession`** is a thin sessionStorage wrapper: `{ sessionId, update(id), reset() }`. Restart clears it.
- **Server is the source of truth for flow state.** The FE never tracks `next_required` or step indices itself — it just renders whatever widget the assistant message carries. That keeps the FE oblivious to graph topology.
- **Refresh-rehydration**: on mount, if `sessionId` exists, `getSession(sessionId)` reloads the message thread from `/session/{id}`. A 4xx is silently swallowed (treated as a fresh start) — see `ChatShell.tsx`.
- **Camera target plumbing** uses a custom event (`window.dispatchEvent(new CustomEvent("kyc:open-camera", { detail: target }))`) because `MessageList` lives below `ChatShell` and needs to trigger the modal without prop-drilling. Acceptable for one event; if you add more inter-island events, switch to a small context.

## Widget rendering

The backend's `Widget` envelope has 4 types: `upload`, `editable_card`, `selfie_camera`, `verdict`. Each maps to one widget component:

| `widget.type` | Component | What it does |
|---|---|---|
| `upload` | `DocumentUploadWidget` | File picker + camera button; calls `onUploadFile(docType, file)` or `onOpenCamera(target)` |
| `editable_card` | `EditableFieldCard` | Form for the OCR'd fields; `onConfirm(docType, fields)` flushes to `/confirm` |
| `selfie_camera` | `SelfieCamera` | Inline `getUserMedia` + capture button; `onSelfie(blob)` flushes to `/capture` |
| `verdict` | `VerdictCard` | Renders `decision`, `decision_reason`, `flags`, `recommendations`, `checks` |

When adding a new widget type:

1. Add the literal to `WidgetType` in `apps/api/app/schemas/chat.py` AND the zod enum in `apps/web/src/api/schemas.ts` (in the same change).
2. Add the component under `src/components/widgets/`.
3. Wire it into `MessageList`'s widget switch and add a handler shape to `WidgetHandlers`.
4. Map the new `next_required` literal to the widget envelope in `orchestrator.STEP_WIDGETS` or `orchestrator.widget_for(...)`.

## Styling

- **Tailwind only.** No CSS modules, no styled-components, no inline `style={...}` for anything other than dynamic dimensions.
- **Use shadcn primitives from `components/ui/`.** They're already themed against the CSS variables in `index.css`. Don't reach for raw Radix unless a primitive is missing.
- **`cn()` helper** in `lib/utils.ts` merges class strings — use it instead of template-string concatenation when conditional classes are involved.
- **Mobile-first**: the user base is predominantly mobile. Test at 360px wide. The chat shell already caps at `max-w-2xl mx-auto`; don't break that container.
- **HSL variables** (`--background`, `--foreground`, `--primary`, …) are the source of truth for colour. Don't hard-code Tailwind palette colours (`bg-blue-500` etc.) for anything user-facing.

## Camera lifecycle

- `SelfieCamera` and `CameraCaptureModal` both call `navigator.mediaDevices.getUserMedia`. **Always stop tracks on unmount or capture** — `streamRef.current.getTracks().forEach(t => t.stop())`. Forgetting this leaves the camera light on after the user moves on.
- `CameraCaptureModal` uses `react-easy-crop` for the doc-upload-via-camera path; the cropped blob is what gets POSTed to `/capture`. Selfie capture is full-frame, no crop.
- Always present a **visible permission prompt** — never start the stream silently on page load.

## Internationalisation

- The assistant's reply text is generated server-side in the user's language (`en` / `hi` / `mixed`) — the FE just renders it.
- **UI chrome** (button labels, "Restart", "KYC Agent" header) is English-only today. If you localise, do it via a single dict under `src/lib/i18n.ts`; don't pull in `react-i18next` for a few strings.

## Accessibility

- Never use emoji-only status indicators in the verdict; pair them with text ("Approved", not just "✅").
- Drag-and-drop zones must also accept a standard file input click (the current `DocumentUploadWidget` does this — keep it that way).
- Dialogs (Radix `Dialog`) handle focus trapping for free; don't add custom focus management on top.

## Anti-patterns to avoid

- ❌ Hard-coding the API URL — use `import.meta.env.VITE_API_URL`. The Docker build wires this in.
- ❌ Storing extracted Aadhaar / PAN values in `localStorage` or `sessionStorage` — only the `sessionId` persists. PII vanishes on tab close by design.
- ❌ Forgetting to stop the webcam stream on unmount.
- ❌ Adding a router (`react-router-dom`) — the chat shell is the only route; the FAQ is a drawer overlay, not a navigation.
- ❌ Pulling in a new UI kit or icon set when shadcn + lucide already covers it.
- ❌ Calling `fetch` directly from a component — go through `src/api/client.ts`.
- ❌ Skipping zod validation on a response — if the schema breaks, you want a loud parse error, not undefined fields silently rendering.
- ❌ Tracking `next_required` in component state — the server owns flow, the client renders.
- ❌ Inlining colours (`#0b66ff`, `bg-blue-500`) — use the shadcn HSL vars.
