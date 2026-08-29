import { requestJson } from "../../api/client";
import {
  candidateProfileResponseSchema,
  type CandidateProfile,
  type CandidateProfileInput,
} from "./contracts";

interface SaveCandidateProfileOptions {
  input: CandidateProfileInput;
  correlationId: string;
  runId: string;
}

export function saveCandidateProfile(
  options: SaveCandidateProfileOptions,
): Promise<CandidateProfile> {
  return requestJson(
    "/api/v1/knowledge/profile",
    {
      method: "POST",
      body: JSON.stringify({
        target_role_keywords: options.input.targetRoleKeywords,
        skill_keywords: options.input.skillKeywords,
        preferred_cities: options.input.preferredCities,
        correlation_id: options.correlationId,
        run_id: options.runId,
      }),
    },
    candidateProfileResponseSchema,
  );
}
