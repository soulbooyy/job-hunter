import type { CandidateProfile } from "../candidate-profile/contracts";
import type { ImportedJob } from "../jobs/contracts";
import type { QuickScreenResult, TriageResult } from "./contracts";

interface ScreeningViewModel {
  currentResult: QuickScreenResult | null;
  currentDecision: TriageResult | null;
  isProfileStale: boolean;
}

export function deriveScreeningView(
  activeJob: ImportedJob | null,
  activeProfile: CandidateProfile | null,
  screeningHistory: readonly QuickScreenResult[],
  triageHistory: readonly TriageResult[],
): ScreeningViewModel {
  const currentResult =
    screeningHistory.findLast(
      (result) =>
        result.job_id === activeJob?.job_id &&
        result.job_version_id === activeJob.job_version_id,
    ) ?? null;

  // Staleness is a session read projection over immutable response lineage. It is
  // never sent to the API or promoted into a second source of business truth.
  const isProfileStale =
    currentResult !== null &&
    activeProfile !== null &&
    currentResult.candidate_profile_id !== activeProfile.profile_id;
  const currentDecision =
    triageHistory.findLast(
      (result) =>
        result.quick_screen_result_id === currentResult?.quick_screen_result_id,
    ) ?? null;

  return { currentResult, currentDecision, isProfileStale };
}
