import { z } from "zod";

export const WidgetSchema = z.object({
  type: z.enum(["upload", "editable_card", "selfie_camera", "verdict"]),
  doc_type: z.string().optional().nullable(),
  accept: z.array(z.string()).optional().nullable(),
  fields: z
    .array(
      z.object({
        name: z.string(),
        label: z.string(),
        value: z.string(),
      }),
    )
    .optional()
    .nullable(),
  decision: z.string().optional().nullable(),
  decision_reason: z.string().optional().nullable(),
  checks: z.array(z.any()).optional().nullable(),
  flags: z.array(z.string()).optional().nullable(),
  recommendations: z.array(z.string()).optional().nullable(),
});
export type Widget = z.infer<typeof WidgetSchema>;

export const ChatMessageSchema = z.object({
  role: z.enum(["user", "assistant", "system"]),
  content: z.string(),
  widget: WidgetSchema.nullable().optional(),
});
export type ChatMessage = z.infer<typeof ChatMessageSchema>;

export const ChatResponseSchema = z.object({
  session_id: z.string(),
  messages: z.array(ChatMessageSchema),
  next_required: z.string(),
  language: z.string(),
});
export type ChatResponse = z.infer<typeof ChatResponseSchema>;
