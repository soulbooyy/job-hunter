import { requestJson } from "../../api/client";
import {
  quickScreenResponseSchema,
  triageResponseSchema,
  type QuickScreenResult,
  type TriageDecision,
  type TriageResult,
} from "./contracts";

interface MutationContext {
  jobId: string;
  correlationId: string;
  runId: string;
}

export function runQuickScreen(
  context: MutationContext,
): Promise<QuickScreenResult> {
  return requestJson(
    `/api/v1/jobs/${encodeURIComponent(context.jobId)}/screen`,
    {
      method: "POST",
      body: JSON.stringify({
        correlation_id: context.correlationId,
        run_id: context.runId,
      }),
    },
    quickScreenResponseSchema,
  );
}

interface TriageOptions extends MutationContext {
  quickScreenResultId: string;
  decision: TriageDecision;
}

export function recordTriage(options: TriageOptions): Promise<TriageResult> {
  return requestJson(
    `/api/v1/jobs/${encodeURIComponent(options.jobId)}/triage`,
    {
      method: "POST",
      body: JSON.stringify({
        quick_screen_result_id: options.quickScreenResultId,
        decision: options.decision,
        correlation_id: options.correlationId,
        run_id: options.runId,
      }),
    },
    triageResponseSchema,
  );
}
