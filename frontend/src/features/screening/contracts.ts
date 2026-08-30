import { z } from "zod";

export const recommendationSchema = z.enum([
  "screen_in",
  "screen_out",
  "uncertain",
]);
export const reasonCodeSchema = z.enum([
  "city_outside_preference",
  "target_role_match",
  "skill_overlap",
  "insufficient_signal",
]);
export const triageDecisionSchema = z.enum(["shortlisted", "skipped"]);

export const quickScreenResponseSchema = z
  .object({
    quick_screen_result_id: z.string().min(1),
    job_id: z.string().min(1),
    job_version_id: z.string().min(1),
    candidate_profile_id: z.string().min(1),
    requirement_ids: z.array(z.string().min(1)),
    recommendation: recommendationSchema,
    reason_codes: z.array(reasonCodeSchema),
    policy_version: z.string().min(1),
    lifecycle_status: z.literal("screened"),
    created_at: z.iso.datetime({ offset: true }),
    correlation_id: z.string().min(1),
    run_id: z.string().min(1),
  })
  .strict();

export const triageResponseSchema = z
  .object({
    triage_decision_id: z.string().min(1),
    job_id: z.string().min(1),
    quick_screen_result_id: z.string().min(1),
    recommendation: recommendationSchema,
    decision: triageDecisionSchema,
    lifecycle_status: z.enum(["shortlisted", "skipped"]),
    decided_at: z.iso.datetime({ offset: true }),
    correlation_id: z.string().min(1),
    run_id: z.string().min(1),
  })
  .strict();

export type QuickScreenResult = z.infer<typeof quickScreenResponseSchema>;
export type QuickScreenViewResult = QuickScreenResult & {
  profile_status?: "current" | "stale";
  job_version_status?: "current" | "historical";
  is_latest_result?: boolean;
  triage_eligible?: boolean;
};
export type TriageDecision = z.infer<typeof triageDecisionSchema>;
export type TriageResult = z.infer<typeof triageResponseSchema>;
