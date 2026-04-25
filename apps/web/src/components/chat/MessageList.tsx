import { useEffect, useRef } from "react";
import { ShieldCheck } from "lucide-react";
import type { ChatMessage, Widget } from "@/api/schemas";
import { MessageBubble } from "./MessageBubble";
import {
  ContactFormWidget,
  type ContactField,
} from "@/components/widgets/ContactFormWidget";
import { DocumentUploadWidget } from "@/components/widgets/DocumentUploadWidget";
import { EditableFieldCard } from "@/components/widgets/EditableFieldCard";
import { SelfieCamera } from "@/components/widgets/SelfieCamera";
import { VerdictCard } from "@/components/widgets/VerdictCard";

export type WidgetHandlers = {
  onContact: (email: string, mobile: string) => Promise<void>;
  onUploadFile: (docType: "aadhaar" | "pan", file: File) => void;
  onOpenCamera: (target: "aadhaar" | "pan" | "selfie") => void;
  onConfirm: (docType: "aadhaar" | "pan", fields: Record<string, string>) => void;
  onSelfie: (blob: Blob) => void;
  onRestart: () => void;
};

export function MessageList({
  messages,
  handlers,
  busy,
}: {
  messages: ChatMessage[];
  handlers: WidgetHandlers;
  busy?: boolean;
}) {
  const endRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, busy]);

  const empty = messages.length === 0;

  return (
    <div className="scroll-thin flex-1 overflow-y-auto px-4 py-6">
      {empty && (
        <div className="mx-auto flex h-full max-w-md flex-col items-center justify-center gap-3 text-center">
          <div className="grid h-14 w-14 place-items-center rounded-2xl bg-primary/10 text-primary ring-1 ring-primary/15">
            <ShieldCheck className="h-7 w-7" aria-hidden />
          </div>
          <div>
            <div className="text-base font-semibold tracking-tight">
              Verify your identity
            </div>
            <p className="mt-1 text-sm text-muted-foreground">
              I'll guide you through KYC step by step. Say <em>hi</em> to begin
              — chat in English or Hindi.
            </p>
          </div>
        </div>
      )}

      <div className="space-y-4">
        {messages.map((m, i) => (
          <div key={i} className="space-y-3">
            <MessageBubble msg={m} />
            {m.widget && (
              <div className="animate-msg-in pl-10">
                <WidgetRenderer
                  widget={m.widget}
                  handlers={handlers}
                  busy={!!busy}
                />
              </div>
            )}
          </div>
        ))}
        {busy && <TypingIndicator />}
      </div>

      <div ref={endRef} />
    </div>
  );
}

function TypingIndicator() {
  return (
    <div
      className="animate-msg-in flex items-end gap-2.5"
      role="status"
      aria-label="Assistant is thinking"
    >
      <div className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-primary/10 text-primary ring-1 ring-primary/15">
        <ShieldCheck className="h-4 w-4" aria-hidden />
      </div>
      <div className="rounded-2xl rounded-bl-md border border-hairline bg-card px-4 py-3 shadow-sm">
        <div className="flex items-center gap-1">
          <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-muted-foreground/60 [animation-delay:-200ms]" />
          <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-muted-foreground/60 [animation-delay:-100ms]" />
          <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-muted-foreground/60" />
        </div>
      </div>
    </div>
  );
}

function WidgetRenderer({
  widget,
  handlers,
  busy,
}: {
  widget: Widget;
  handlers: WidgetHandlers;
  busy: boolean;
}) {
  if (widget.type === "contact_form" && widget.fields) {
    return (
      <ContactFormWidget
        fields={widget.fields as ContactField[]}
        onSubmit={(email, mobile) => handlers.onContact(email, mobile)}
      />
    );
  }
  if (widget.type === "upload" && widget.doc_type) {
    const dt = widget.doc_type as "aadhaar" | "pan";
    return (
      <DocumentUploadWidget
        docType={dt}
        accept={widget.accept ?? ["image/jpeg", "image/png", "application/pdf"]}
        onFile={(f) => handlers.onUploadFile(dt, f)}
        onOpenCamera={() => handlers.onOpenCamera(dt)}
      />
    );
  }
  if (widget.type === "editable_card" && widget.doc_type && widget.fields) {
    const dt = widget.doc_type as "aadhaar" | "pan";
    return (
      <EditableFieldCard
        docType={dt}
        fields={widget.fields}
        onConfirm={(vals) => handlers.onConfirm(dt, vals)}
      />
    );
  }
  if (widget.type === "selfie_camera") {
    return (
      <SelfieCamera
        busy={busy}
        onCapture={(blob) => handlers.onSelfie(blob)}
      />
    );
  }
  if (widget.type === "verdict") {
    return (
      <VerdictCard
        verdict={{
          decision: widget.decision ?? "flagged",
          decision_reason: widget.decision_reason ?? "",
          checks: (widget.checks ?? []) as never,
          flags: widget.flags ?? [],
          recommendations: widget.recommendations ?? [],
          ip_check: widget.ip_check ?? null,
          face_check: widget.face_check ?? null,
          selfie_url: widget.selfie_url ?? null,
          aadhaar_face_url: widget.aadhaar_face_url ?? null,
        }}
      />
    );
  }
  return null;
}
