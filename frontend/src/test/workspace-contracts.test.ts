import { describe, expect, it, vi } from "vitest";

import { ApiError } from "../api/errors";
import { getJob, listJobs } from "../features/workspace/api";
import {
  candidateProfileHistoryResponseSchema,
  evidenceHistoryResponseSchema,
  jobListResponseSchema,
  jobWorkspaceResponseSchema,
} from "../features/workspace/contracts";

const timestamp = "2026-08-30T09:00:00Z";
const source = {
  reference_id: "source-reference-1",
  snapshot_id: "source-snapshot-1",
  kind: "manual_jd",
  locator: null,
  captured_at: timestamp,
  last_verified_at: timestamp,
  freshness: "fresh",
};

const workspace = {
  job_id: "job-1",
  active_version_id: "job-version-1",
  lifecycle_status: "imported",
  versions: [
    {
      job_version_id: "job-version-1",
      job_id: "job-1",
      version_number: 1,
      title: "AI Engineer",
      company: "Example AI",
      city: "Shenzhen",
      description: "Must have Python experience",
      source_snapshot_id: "source-snapshot-1",
      source,
      created_at: timestamp,
      correlation_id: "correlation-job",
      run_id: "run-job",
      is_active: true,
    },
  ],
  requirements: [],
  screening_results: [],
  triage_history: [],
};

describe("Workspace GET runtime contracts", () => {
  it("accepts the typed empty collections and a complete Job workspace", () => {
    expect(jobListResponseSchema.parse({ items: [] })).toEqual({ items: [] });
    expect(
      candidateProfileHistoryResponseSchema.parse({
        active_profile_id: null,
        items: [],
      }),
    ).toEqual({ active_profile_id: null, items: [] });
    expect(evidenceHistoryResponseSchema.parse({ items: [] })).toEqual({
      items: [],
    });
    expect(jobWorkspaceResponseSchema.parse(workspace).job_id).toBe("job-1");
  });

  it("rejects extra fields and inconsistent active pointers", () => {
    expect(() =>
      jobListResponseSchema.parse({ items: [], unexpected: true }),
    ).toThrow();
    expect(() =>
      jobWorkspaceResponseSchema.parse({
        ...workspace,
        active_version_id: "missing-version",
      }),
    ).toThrow();
    expect(() =>
      candidateProfileHistoryResponseSchema.parse({
        active_profile_id: "missing-profile",
        items: [],
      }),
    ).toThrow();
    expect(() =>
      evidenceHistoryResponseSchema.parse({
        items: [
          {
            evidence_id: "evidence-1",
            active_version_id: "missing-version",
            versions: [
              {
                evidence_version_id: "evidence-version-1",
                evidence_id: "evidence-1",
                version_number: 1,
                evidence_type: "project",
                canonical_content: "Built an evaluation pipeline.",
                occurred_on: null,
                source: "manual",
                provenance: "User-confirmed",
                sensitivity: "private",
                validity: "valid",
                created_at: timestamp,
                correlation_id: "correlation-evidence",
                run_id: "run-evidence",
                is_active: false,
              },
            ],
          },
        ],
      }),
    ).toThrow();
  });

  it("uses no-store GET requests and encodes Job IDs", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ items: [] }), { status: 200 }),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify(workspace), { status: 200 }),
      );
    vi.stubGlobal("fetch", fetchMock);

    await listJobs();
    await getJob("job / one");

    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/v1/jobs");
    expect(fetchMock.mock.calls[0]?.[1]).toMatchObject({
      method: "GET",
      cache: "no-store",
    });
    expect(fetchMock.mock.calls[1]?.[0]).toBe("/api/v1/jobs/job%20%2F%20one");
  });

  it("maps an unknown Job read to the stable not-found error", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            error: { code: "not_found", message: "job not found: missing" },
          }),
          { status: 404 },
        ),
      ),
    );

    const error = await getJob("missing").catch((failure: unknown) => failure);

    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ code: "not_found", status: 404 });
  });
});
