import type { CandidateProfile } from "../candidate-profile/contracts";
import type { ActiveJob } from "../jobs/contracts";
import type { QuickScreenViewResult, TriageResult } from "./contracts";

interface ScreeningViewModel {
  currentResult: QuickScreenViewResult | null;
  currentDecision: TriageResult | null;
  isProfileStale: boolean;
}

export function deriveScreeningView(
  activeJob: ActiveJob | null,
  activeProfile: CandidateProfile | null,
  screeningHistory: readonly QuickScreenViewResult[],
  triageHistory: readonly TriageResult[],
): ScreeningViewModel {
  const currentResult =
    screeningHistory.findLast(
      (result) =>
        result.job_id === activeJob?.job_id &&
        (result.triage_eligible ??
          result.job_version_id === activeJob.job_version_id),
    ) ?? null;

  // The backend projection is authoritative after readback. Comparing immutable
  // IDs keeps a just-created local result accurate until the next synchronization.
  const isProfileStale =
    currentResult !== null &&
    activeProfile !== null &&
    (currentResult.profile_status === "stale" ||
      currentResult.candidate_profile_id !== activeProfile.profile_id);
  const currentDecision =
    triageHistory.findLast(
      (result) =>
        result.quick_screen_result_id === currentResult?.quick_screen_result_id,
    ) ?? null;

  return { currentResult, currentDecision, isProfileStale };
}
