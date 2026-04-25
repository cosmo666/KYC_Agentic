import { getClientIP } from "@/hooks/useClientIP";
import { ChatResponseSchema, type ChatResponse } from "./schemas";

const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

/** Build a Headers object with X-Real-IP merged in if we know the user's
 * public IP. Backend uses this to drive geolocation instead of the docker
 * bridge IP it would otherwise see. */
function withClientIP(extra?: HeadersInit): Headers {
  const h = new Headers(extra);
  const ip = getClientIP();
  if (ip) h.set("X-Real-IP", ip);
  return h;
}

async function handle<T>(
  r: Response,
  schema: { parse: (d: unknown) => T },
): Promise<T> {
  if (!r.ok) {
    const text = await r.text();
    throw new Error(`${r.status}: ${text}`);
  }
  return schema.parse(await r.json());
}

export async function sendChat(
  text: string,
  sessionId: string | null,
): Promise<ChatResponse> {
  const r = await fetch(`${API_URL}/chat`, {
    method: "POST",
    headers: withClientIP({ "Content-Type": "application/json" }),
    body: JSON.stringify({ text, session_id: sessionId }),
  });
  return handle(r, ChatResponseSchema);
}

export async function uploadDoc(
  sessionId: string,
  docType: "aadhaar" | "pan",
  file: File | Blob,
): Promise<ChatResponse> {
  const fd = new FormData();
  fd.append("session_id", sessionId);
  fd.append("doc_type", docType);
  fd.append("file", file, (file as File).name ?? `${docType}.jpg`);
  const r = await fetch(`${API_URL}/upload`, {
    method: "POST",
    headers: withClientIP(),
    body: fd,
  });
  return handle(r, ChatResponseSchema);
}

export async function captureImage(
  sessionId: string,
  target: "selfie" | "aadhaar" | "pan",
  blob: Blob,
): Promise<ChatResponse> {
  const fd = new FormData();
  fd.append("session_id", sessionId);
  fd.append("target", target);
  fd.append("file", blob, `${target}.jpg`);
  const r = await fetch(`${API_URL}/capture`, {
    method: "POST",
    headers: withClientIP(),
    body: fd,
  });
  return handle(r, ChatResponseSchema);
}

export async function confirmDoc(
  sessionId: string,
  docType: "aadhaar" | "pan",
  fields: Record<string, string>,
): Promise<ChatResponse> {
  const r = await fetch(`${API_URL}/confirm`, {
    method: "POST",
    headers: withClientIP({ "Content-Type": "application/json" }),
    body: JSON.stringify({
      session_id: sessionId,
      doc_type: docType,
      fields,
    }),
  });
  return handle(r, ChatResponseSchema);
}

export async function getSession(sessionId: string): Promise<ChatResponse> {
  const r = await fetch(`${API_URL}/session/${sessionId}`, {
    headers: withClientIP(),
  });
  return handle(r, ChatResponseSchema);
}

export async function initSession(): Promise<ChatResponse> {
  const r = await fetch(`${API_URL}/session/init`, {
    method: "POST",
    headers: withClientIP(),
  });
  return handle(r, ChatResponseSchema);
}

export async function submitContact(
  sessionId: string,
  email: string,
  mobile: string,
): Promise<ChatResponse> {
  const r = await fetch(`${API_URL}/session/contact`, {
    method: "POST",
    headers: withClientIP({ "Content-Type": "application/json" }),
    body: JSON.stringify({ session_id: sessionId, email, mobile }),
  });
  return handle(r, ChatResponseSchema);
}
