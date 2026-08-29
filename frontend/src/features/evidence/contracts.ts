import { z } from "zod";

export const evidenceTypeSchema = z.enum([
  "project",
  "experience",
  "education",
  "certification",
  "skill",
  "other",
]);
export const evidenceSensitivitySchema = z.enum([
  "public",
  "private",
  "sensitive",
]);
export const evidenceValiditySchema = z.enum(["valid", "expired", "revoked"]);

export const evidenceResponseSchema = z
  .object({
    evidence_id: z.string().min(1),
    evidence_version_id: z.string().min(1),
    active_version_id: z.string().min(1),
    version_number: z.number().int().positive(),
    evidence_type: evidenceTypeSchema,
    canonical_content: z.string().min(1),
    occurred_on: z.iso.date().nullable(),
    source: z.string().min(1),
    provenance: z.string().min(1),
    sensitivity: evidenceSensitivitySchema,
    validity: evidenceValiditySchema,
    created_at: z.iso.datetime({ offset: true }),
    correlation_id: z.string().min(1),
    run_id: z.string().min(1),
  })
  .strict();

export type Evidence = z.infer<typeof evidenceResponseSchema>;
export type EvidenceType = z.infer<typeof evidenceTypeSchema>;
export type EvidenceSensitivity = z.infer<typeof evidenceSensitivitySchema>;
export type EvidenceValidity = z.infer<typeof evidenceValiditySchema>;

export interface EvidenceInput {
  evidenceType: EvidenceType;
  canonicalContent: string;
  occurredOn: string | null;
  source: string;
  provenance: string;
  sensitivity: EvidenceSensitivity;
  validity: EvidenceValidity;
}
