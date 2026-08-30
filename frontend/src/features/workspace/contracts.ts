import { z } from "zod";

import { candidateProfileResponseSchema } from "../candidate-profile/contracts";
import {
  evidenceResponseSchema,
  evidenceSensitivitySchema,
  evidenceTypeSchema,
  evidenceValiditySchema,
} from "../evidence/contracts";
import {
  freshnessSchema,
  jobLifecycleStatusSchema,
  sourceKindSchema,
  timestampSchema,
} from "../jobs/contracts";
import {
  quickScreenResponseSchema,
  recommendationSchema,
  triageDecisionSchema,
  triageResponseSchema,
} from "../screening/contracts";

export const sourceReadSchema = z
  .object({
    reference_id: z.string().min(1),
    snapshot_id: z.string().min(1),
    kind: sourceKindSchema,
    locator: z.string().nullable(),
    captured_at: timestampSchema,
    last_verified_at: timestampSchema,
    freshness: freshnessSchema,
  })
  .strict();

export const jobSummarySchema = z
  .object({
    job_id: z.string().min(1),
    active_version_id: z.string().min(1),
    version_number: z.number().int().positive(),
    title: z.string().min(1),
    company: z.string().min(1),
    city: z.string().min(1),
    lifecycle_status: jobLifecycleStatusSchema,
    source: sourceReadSchema,
    current_screen_recommendation: recommendationSchema.nullable(),
    current_triage_decision: triageDecisionSchema.nullable(),
  })
  .strict();

export const jobListResponseSchema = z
  .object({ items: z.array(jobSummarySchema) })
  .strict();

export const jobVersionReadSchema = z
  .object({
    job_version_id: z.string().min(1),
    job_id: z.string().min(1),
    version_number: z.number().int().positive(),
    title: z.string().min(1),
    company: z.string().min(1),
    city: z.string().min(1),
    description: z.string().min(1),
    source_snapshot_id: z.string().min(1),
    source: sourceReadSchema,
    created_at: timestampSchema,
    correlation_id: z.string().min(1),
    run_id: z.string().min(1),
    is_active: z.boolean(),
  })
  .strict();

export const requirementReadSchema = z
  .object({
    requirement_id: z.string().min(1),
    job_version_id: z.string().min(1),
    source_text: z.string().min(1),
    text: z.string().min(1),
    requirement_type: z.enum([
      "skill",
      "experience",
      "education",
      "location",
      "responsibility",
      "other",
    ]),
    priority: z.enum(["required", "preferred", "unspecified"]),
    parser_name: z.string().min(1),
    parser_version: z.string().min(1),
    created_at: timestampSchema,
    correlation_id: z.string().min(1),
    run_id: z.string().min(1),
  })
  .strict();

export const quickScreenReadSchema = quickScreenResponseSchema
  .extend({
    profile_status: z.enum(["current", "stale"]),
    job_version_status: z.enum(["current", "historical"]),
    is_latest_result: z.boolean(),
    triage_eligible: z.boolean(),
  })
  .strict();

export const jobWorkspaceResponseSchema = z
  .object({
    job_id: z.string().min(1),
    active_version_id: z.string().min(1),
    lifecycle_status: jobLifecycleStatusSchema,
    versions: z.array(jobVersionReadSchema).min(1),
    requirements: z.array(requirementReadSchema),
    screening_results: z.array(quickScreenReadSchema),
    triage_history: z.array(triageResponseSchema),
  })
  .strict()
  .superRefine((value, context) => {
    const activeVersions = value.versions.filter(
      (version) =>
        version.job_version_id === value.active_version_id && version.is_active,
    );
    if (activeVersions.length !== 1) {
      context.addIssue({
        code: "custom",
        message: "active JobVersion pointer is inconsistent",
        path: ["active_version_id"],
      });
    }
    if (value.versions.some((version) => version.job_id !== value.job_id)) {
      context.addIssue({
        code: "custom",
        message: "JobVersion belongs to another Job",
        path: ["versions"],
      });
    }
  });

export const candidateProfileHistoryResponseSchema = z
  .object({
    active_profile_id: z.string().min(1).nullable(),
    items: z.array(candidateProfileResponseSchema),
  })
  .strict()
  .superRefine((value, context) => {
    if (
      value.active_profile_id !== null &&
      !value.items.some((item) => item.profile_id === value.active_profile_id)
    ) {
      context.addIssue({
        code: "custom",
        message: "active CandidateProfile pointer is inconsistent",
        path: ["active_profile_id"],
      });
    }
  });

export const evidenceVersionReadSchema = evidenceResponseSchema
  .omit({ active_version_id: true })
  .extend({
    evidence_type: evidenceTypeSchema,
    sensitivity: evidenceSensitivitySchema,
    validity: evidenceValiditySchema,
    is_active: z.boolean(),
  })
  .strict();

export const evidenceItemReadSchema = z
  .object({
    evidence_id: z.string().min(1),
    active_version_id: z.string().min(1),
    versions: z.array(evidenceVersionReadSchema).min(1),
  })
  .strict()
  .superRefine((value, context) => {
    const activeVersions = value.versions.filter(
      (version) =>
        version.evidence_version_id === value.active_version_id &&
        version.is_active,
    );
    if (activeVersions.length !== 1) {
      context.addIssue({
        code: "custom",
        message: "active Evidence version pointer is inconsistent",
        path: ["active_version_id"],
      });
    }
    if (
      value.versions.some(
        (version) => version.evidence_id !== value.evidence_id,
      )
    ) {
      context.addIssue({
        code: "custom",
        message: "Evidence version belongs to another Evidence item",
        path: ["versions"],
      });
    }
  });

export const evidenceHistoryResponseSchema = z
  .object({ items: z.array(evidenceItemReadSchema) })
  .strict();

export type JobSummary = z.infer<typeof jobSummarySchema>;
export type JobWorkspace = z.infer<typeof jobWorkspaceResponseSchema>;
export type CandidateProfileHistory = z.infer<
  typeof candidateProfileHistoryResponseSchema
>;
export type EvidenceItemRead = z.infer<typeof evidenceItemReadSchema>;
export type EvidenceHistory = z.infer<typeof evidenceHistoryResponseSchema>;
