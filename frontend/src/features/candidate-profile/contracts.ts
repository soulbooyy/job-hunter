import { z } from "zod";

export const candidateProfileResponseSchema = z
  .object({
    profile_id: z.string().min(1),
    target_role_keywords: z.array(z.string().min(1)).min(1),
    skill_keywords: z.array(z.string().min(1)).min(1),
    preferred_cities: z.array(z.string().min(1)),
    created_at: z.iso.datetime({ offset: true }),
    correlation_id: z.string().min(1),
    run_id: z.string().min(1),
  })
  .strict();

export type CandidateProfile = z.infer<typeof candidateProfileResponseSchema>;

export interface CandidateProfileInput {
  targetRoleKeywords: readonly string[];
  skillKeywords: readonly string[];
  preferredCities: readonly string[];
}
