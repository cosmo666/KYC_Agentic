import { z } from "zod";

export const IpCheckSchema = z.object({
  ip: z.string().optional().nullable(),
  country_code: z.string().optional().nullable(),
  country_ok: z.boolean().optional().nullable(),
  city: z.string().optional().nullable(),
  region: z.string().optional().nullable(),
  city_match: z.boolean().optional().nullable(),
  state_match: z.boolean().optional().nullable(),
  latitude: z.number().optional().nullable(),
  longitude: z.number().optional().nullable(),
});
export type IpCheck = z.infer<typeof IpCheckSchema>;

export const FaceCheckSchema = z.object({
  verified: z.boolean().optional().nullable(),
  confidence: z.number().optional().nullable(),
  faces_detected: z.boolean().optional().nullable(),
  predicted_gender: z.string().optional().nullable(),
  aadhaar_gender: z.string().optional().nullable(),
  gender_match: z.boolean().optional().nullable(),
});
export type FaceCheck = z.infer<typeof FaceCheckSchema>;

export const WidgetSchema = z.object({
  type: z.enum([
    "contact_form",
    "upload",
    "editable_card",
    "selfie_camera",
    "verdict",
  ]),
  doc_type: z.string().optional().nullable(),
  accept: z.array(z.string()).optional().nullable(),
  // `editable_card` and `contact_form` both ship a `fields` array.
  // contact_form fields carry optional `placeholder` and `input_type`.
  fields: z
    .array(
      z.object({
        name: z.string(),
        label: z.string(),
        value: z.string(),
        placeholder: z.string().optional().nullable(),
        input_type: z.string().optional().nullable(),
      }),
    )
    .optional()
    .nullable(),
  decision: z.string().optional().nullable(),
  decision_reason: z.string().optional().nullable(),
  checks: z.array(z.any()).optional().nullable(),
  flags: z.array(z.string()).optional().nullable(),
  recommendations: z.array(z.string()).optional().nullable(),
  ip_check: IpCheckSchema.optional().nullable(),
  face_check: FaceCheckSchema.optional().nullable(),
  selfie_url: z.string().optional().nullable(),
  aadhaar_face_url: z.string().optional().nullable(),
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
