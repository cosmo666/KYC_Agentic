import { useEffect, useRef } from "react";
import type { ChatMessage, Widget } from "@/api/schemas";
import { MessageBubble } from "./MessageBubble";
import { DocumentUploadWidget } from "@/components/widgets/DocumentUploadWidget";
import { EditableFieldCard } from "@/components/widgets/EditableFieldCard";
import { SelfieCamera } from "@/components/widgets/SelfieCamera";
import { VerdictCard } from "@/components/widgets/VerdictCard";

export type WidgetHandlers = {
  onUploadFile: (docType: "aadhaar" | "pan", file: File) => void;
  onOpenCamera: (target: "aadhaar" | "pan" | "selfie") => void;
  onConfirm: (docType: "aadhaar" | "pan", fields: Record<string, string>) => void;
  onSelfie: (blob: Blob) => void;
  onRestart: () => void;
};

export function MessageList({
  messages,
  handlers,
}: {
  messages: ChatMessage[];
  handlers: WidgetHandlers;
}) {
  const endRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  return (
    <div className="flex-1 overflow-y-auto px-4 py-6 space-y-3">
      {messages.map((m, i) => (
        <div key={i} className="space-y-2">
          <MessageBubble msg={m} />
          {m.widget && <WidgetRenderer widget={m.widget} handlers={handlers} />}
        </div>
      ))}
      <div ref={endRef} />
    </div>
  );
}

function WidgetRenderer({
  widget,
  handlers,
}: {
  widget: Widget;
  handlers: WidgetHandlers;
}) {
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
    return <SelfieCamera onCapture={(blob) => handlers.onSelfie(blob)} />;
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
        }}
      />
    );
  }
  return null;
}
