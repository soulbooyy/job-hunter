import { describe, expect, it, vi } from "vitest";

import { ApiError, requestJson } from "../api/client";
import { getErrorMessage } from "../api/errors";
import { candidateProfileResponseSchema } from "../features/candidate-profile/contracts";
import { evidenceResponseSchema } from "../features/evidence/contracts";
import { importJobResponseSchema } from "../features/jobs/contracts";
import {
  quickScreenResponseSchema,
  triageResponseSchema,
} from "../features/screening/contracts";

const importedJob = {
  job_id: "job-1",
  job_version_id: "job-version-1",
  active_version_id: "job-version-1",
  source_snapshot_id: "source-1",
  version_number: 1,
  lifecycle_status: "imported",
  source: {
    kind: "manual_jd",
    locator: null,
    captured_at: "2026-08-29T09:00:00Z",
    last_verified_at: "2026-08-29T09:00:00Z",
    freshness: "fresh",
  },
  correlation_id: "correlation-1",
  run_id: "run-1",
};

describe("HTTP response runtime contracts", () => {
  it("accepts every valid mutation response", () => {
    expect(importJobResponseSchema.parse(importedJob).job_id).toBe("job-1");
    expect(
      candidateProfileResponseSchema.parse({
        profile_id: "profile-1",
        target_role_keywords: ["AI Engineer"],
        skill_keywords: ["Python"],
        preferred_cities: ["Shenzhen"],
        created_at: "2026-08-29T09:00:00Z",
        correlation_id: "correlation-2",
        run_id: "run-2",
      }).profile_id,
    ).toBe("profile-1");
    expect(
      evidenceResponseSchema.parse({
        evidence_id: "evidence-1",
        evidence_version_id: "evidence-version-1",
        active_version_id: "evidence-version-1",
        version_number: 1,
        evidence_type: "project",
        canonical_content: "Built an evaluation system.",
        occurred_on: null,
        source: "manual",
        provenance: "User confirmed",
        sensitivity: "private",
        validity: "valid",
        created_at: "2026-08-29T09:00:00Z",
        correlation_id: "correlation-3",
        run_id: "run-3",
      }).version_number,
    ).toBe(1);
    expect(
      quickScreenResponseSchema.parse({
        quick_screen_result_id: "screen-1",
        job_id: "job-1",
        job_version_id: "job-version-1",
        candidate_profile_id: "profile-1",
        requirement_ids: ["requirement-1"],
        recommendation: "screen_in",
        reason_codes: ["target_role_match", "skill_overlap"],
        policy_version: "quick-screen-v1",
        lifecycle_status: "screened",
        created_at: "2026-08-29T09:00:00Z",
        correlation_id: "correlation-4",
        run_id: "run-4",
      }).recommendation,
    ).toBe("screen_in");
    expect(
      triageResponseSchema.parse({
        triage_decision_id: "triage-1",
        job_id: "job-1",
        quick_screen_result_id: "screen-1",
        recommendation: "screen_in",
        decision: "shortlisted",
        lifecycle_status: "shortlisted",
        decided_at: "2026-08-29T09:00:00Z",
        correlation_id: "correlation-5",
        run_id: "run-5",
      }).decision,
    ).toBe("shortlisted");
  });

  it("rejects malformed, extra, and invalid-enum response data", () => {
    expect(() =>
      importJobResponseSchema.parse({ ...importedJob, unexpected: true }),
    ).toThrow();
    expect(() =>
      importJobResponseSchema.parse({ ...importedJob, version_number: "1" }),
    ).toThrow();
    expect(() =>
      quickScreenResponseSchema.parse({ recommendation: "deep_fit" }),
    ).toThrow();
  });
});

describe("stable API failures", () => {
  it.each([
    ["input_validation", "输入内容未通过校验。"],
    ["not_found", "未找到所需数据。"],
    ["conflict", "当前状态已发生变化，请刷新相关结果后重试。"],
    ["dependency_unavailable", "后端依赖暂不可用。"],
  ] as const)("maps %s to stable Chinese UI copy", (code, expected) => {
    expect(
      getErrorMessage(new ApiError(code, "Safe backend message", 400)),
    ).toBe(expected);
  });

  it.each([
    [404, "not_found"],
    [409, "conflict"],
    [422, "input_validation"],
    [503, "dependency_unavailable"],
  ] as const)("maps backend status %s", async (status, code) => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({ error: { code, message: "Safe backend message" } }),
          {
            status,
            headers: { "Content-Type": "application/json" },
          },
        ),
      ),
    );

    await expect(
      requestJson("/api/example", {}, importJobResponseSchema),
    ).rejects.toMatchObject({
      name: "ApiError",
      code,
      status,
      message: "Safe backend message",
    });
  });

  it("maps unavailable networks without exposing the original exception", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockRejectedValue(new Error("secret network detail")),
    );

    const failure = await requestJson(
      "/api/example",
      {},
      importJobResponseSchema,
    ).catch((error: unknown) => error);

    expect(failure).toBeInstanceOf(ApiError);
    expect(failure).toMatchObject({
      code: "backend_unavailable",
      status: null,
    });
    expect(String(failure)).not.toContain("secret network detail");
  });

  it("maps a stale optimistic write without treating it as malformed JSON", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            error: {
              code: "stale_write",
              message: "Authoritative state changed",
            },
          }),
          {
            status: 409,
            headers: { "Content-Type": "application/json" },
          },
        ),
      ),
    );

    const failure = await requestJson(
      "/api/example",
      {},
      importJobResponseSchema,
    ).catch((error: unknown) => error);

    expect(failure).toMatchObject({
      name: "ApiError",
      code: "stale_write",
      status: 409,
    });
    expect(getErrorMessage(failure)).toBe(
      "数据已被其他操作更新，请重新同步后重试。",
    );
  });

  it("rejects malformed successful JSON at the runtime boundary", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ job_id: "unvalidated" }), {
          status: 201,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );

    await expect(
      requestJson("/api/example", {}, importJobResponseSchema),
    ).rejects.toMatchObject({
      code: "invalid_response",
      message: "后端返回了无效响应。",
    });
  });

  it("rejects a mutation response that drifts from the frozen 201 status", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify(importedJob), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );

    await expect(
      requestJson("/api/example", {}, importJobResponseSchema),
    ).rejects.toMatchObject({ code: "invalid_response" });
  });
});
