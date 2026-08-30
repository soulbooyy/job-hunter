import { requestJson } from "../../api/client";
import {
  candidateProfileHistoryResponseSchema,
  evidenceHistoryResponseSchema,
  jobListResponseSchema,
  jobWorkspaceResponseSchema,
  type CandidateProfileHistory,
  type EvidenceHistory,
  type JobSummary,
  type JobWorkspace,
} from "./contracts";

const readRequest: RequestInit = {
  method: "GET",
  cache: "no-store",
};

export async function listJobs(): Promise<readonly JobSummary[]> {
  const response = await requestJson(
    "/api/v1/jobs",
    readRequest,
    jobListResponseSchema,
    200,
  );
  return response.items;
}

export function getJob(jobId: string): Promise<JobWorkspace> {
  return requestJson(
    `/api/v1/jobs/${encodeURIComponent(jobId)}`,
    readRequest,
    jobWorkspaceResponseSchema,
    200,
  );
}

export function listCandidateProfiles(): Promise<CandidateProfileHistory> {
  return requestJson(
    "/api/v1/knowledge/profiles",
    readRequest,
    candidateProfileHistoryResponseSchema,
    200,
  );
}

export function listEvidence(): Promise<EvidenceHistory> {
  return requestJson(
    "/api/v1/knowledge/evidence",
    readRequest,
    evidenceHistoryResponseSchema,
    200,
  );
}
