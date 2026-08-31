import { render, screen, within } from "@testing-library/react";
import { userEvent } from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { App } from "../app/App";

const timestamp = "2026-08-30T09:00:00Z";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      "Cache-Control": "no-store",
      "Content-Type": "application/json",
    },
  });
}

function requestPath(input: RequestInfo | URL): string {
  if (typeof input === "string") return input;
  if (input instanceof URL) return input.toString();
  return input.url;
}

const source = {
  reference_id: "source-reference-1",
  snapshot_id: "source-snapshot-1",
  kind: "manual_jd",
  locator: null,
  captured_at: timestamp,
  last_verified_at: timestamp,
  freshness: "fresh",
};

const profiles = {
  active_profile_id: "profile-2",
  items: [
    {
      profile_id: "profile-1",
      target_role_keywords: ["AI Engineer"],
      skill_keywords: ["Python"],
      preferred_cities: ["Shenzhen"],
      created_at: "2026-08-30T08:00:00Z",
      correlation_id: "correlation-profile-1",
      run_id: "run-profile-1",
    },
    {
      profile_id: "profile-2",
      target_role_keywords: ["Platform Engineer"],
      skill_keywords: ["Python", "FastAPI"],
      preferred_cities: ["Shenzhen"],
      created_at: timestamp,
      correlation_id: "correlation-profile-2",
      run_id: "run-profile-2",
    },
  ],
};

const jobSummary = {
  job_id: "job-1",
  active_version_id: "job-version-2",
  version_number: 2,
  title: "Senior AI Engineer",
  company: "Example AI",
  city: "Shenzhen",
  lifecycle_status: "shortlisted",
  source,
  current_screen_recommendation: "screen_in",
  current_triage_decision: "shortlisted",
};

const jobDetail = {
  job_id: "job-1",
  active_version_id: "job-version-2",
  lifecycle_status: "shortlisted",
  versions: [
    {
      job_version_id: "job-version-1",
      job_id: "job-1",
      version_number: 1,
      title: "AI Engineer",
      company: "Example AI",
      city: "Shenzhen",
      description: "Must have Python experience",
      source_snapshot_id: "source-snapshot-old",
      source: {
        ...source,
        reference_id: "source-reference-old",
        snapshot_id: "source-snapshot-old",
      },
      created_at: "2026-08-30T07:00:00Z",
      correlation_id: "correlation-job",
      run_id: "run-job-1",
      is_active: false,
    },
    {
      job_version_id: "job-version-2",
      job_id: "job-1",
      version_number: 2,
      title: "Senior AI Engineer",
      company: "Example AI",
      city: "Shenzhen",
      description: "Must have Python and FastAPI experience",
      source_snapshot_id: "source-snapshot-1",
      source,
      created_at: timestamp,
      correlation_id: "correlation-job",
      run_id: "run-job-2",
      is_active: true,
    },
  ],
  requirements: [
    {
      requirement_id: "requirement-1",
      job_version_id: "job-version-2",
      source_text: "Must have Python and FastAPI experience",
      text: "Must have Python and FastAPI experience",
      requirement_type: "skill",
      priority: "required",
      parser_name: "deterministic-line-parser",
      parser_version: "v1",
      created_at: timestamp,
      correlation_id: "correlation-screen",
      run_id: "run-screen",
    },
  ],
  screening_results: [
    {
      quick_screen_result_id: "screen-old",
      job_id: "job-1",
      job_version_id: "job-version-1",
      candidate_profile_id: "profile-1",
      requirement_ids: [],
      recommendation: "uncertain",
      reason_codes: ["insufficient_signal"],
      policy_version: "quick-screen-v1",
      lifecycle_status: "screened",
      created_at: "2026-08-30T08:00:00Z",
      correlation_id: "correlation-screen-old",
      run_id: "run-screen-old",
      profile_status: "stale",
      job_version_status: "historical",
      is_latest_result: false,
      triage_eligible: false,
    },
    {
      quick_screen_result_id: "screen-1",
      job_id: "job-1",
      job_version_id: "job-version-2",
      candidate_profile_id: "profile-1",
      requirement_ids: ["requirement-1"],
      recommendation: "screen_in",
      reason_codes: ["target_role_match", "skill_overlap"],
      policy_version: "quick-screen-v1",
      lifecycle_status: "screened",
      created_at: timestamp,
      correlation_id: "correlation-screen",
      run_id: "run-screen",
      profile_status: "stale",
      job_version_status: "current",
      is_latest_result: true,
      triage_eligible: true,
    },
  ],
  triage_history: [
    {
      triage_decision_id: "triage-1",
      job_id: "job-1",
      quick_screen_result_id: "screen-1",
      recommendation: "screen_in",
      decision: "shortlisted",
      lifecycle_status: "shortlisted",
      decided_at: timestamp,
      correlation_id: "correlation-triage",
      run_id: "run-triage",
    },
  ],
};

const evidence = {
  items: [
    {
      evidence_id: "evidence-1",
      active_version_id: "evidence-version-2",
      versions: [1, 2].map((version) => ({
        evidence_version_id: `evidence-version-${String(version)}`,
        evidence_id: "evidence-1",
        version_number: version,
        evidence_type: "project",
        canonical_content:
          version === 1
            ? "Built an evaluation pipeline."
            : "Built and benchmarked an evaluation pipeline.",
        occurred_on: "2026-06-01",
        source: "manual",
        provenance: `User-confirmed project v${String(version)}`,
        sensitivity: "private",
        validity: "valid",
        created_at: timestamp,
        correlation_id: "correlation-evidence",
        run_id: `run-evidence-${String(version)}`,
        is_active: version === 2,
      })),
    },
  ],
};

function createWorkspaceFetch() {
  return vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const path = requestPath(input);
    if (path.endsWith("/api/v1/jobs/job-1")) {
      return Promise.resolve(jsonResponse(jobDetail));
    }
    if (path.endsWith("/api/v1/jobs")) {
      return Promise.resolve(jsonResponse({ items: [jobSummary] }));
    }
    if (path.endsWith("/api/v1/knowledge/profiles")) {
      return Promise.resolve(jsonResponse(profiles));
    }
    if (path.endsWith("/api/v1/knowledge/evidence")) {
      return Promise.resolve(jsonResponse(evidence));
    }
    return Promise.reject(
      new Error(`unexpected request: ${path} ${init?.method ?? "unknown"}`),
    );
  });
}

describe("Workspace GET readback", () => {
  it("restores complete backend state and backend-derived actionability after mount", async () => {
    const fetchMock = createWorkspaceFetch();
    vi.stubGlobal("fetch", fetchMock);

    render(<App idFactory={() => "test-id"} />);

    expect(await screen.findByText("工作区已从后端恢复。")).toBeVisible();
    expect(screen.getByLabelText("本地数据边界")).toHaveTextContent(
      /后端进程重启后.*本地 SQLite 数据库重新读取/u,
    );
    expect(screen.getByLabelText("本地数据边界")).not.toHaveTextContent(
      "后端进程重启后无法恢复",
    );
    const workspace = screen.getByRole("region", { name: "后端工作区" });
    expect(within(workspace).getByText(/本地 SQLite 持久化/u)).toBeVisible();
    expect(
      within(workspace).getByRole("button", {
        name: "Senior AI Engineer，Example AI",
      }),
    ).toBeVisible();
    expect(within(workspace).getByText("JobVersion 历史")).toBeVisible();
    expect(within(workspace).getByText("ParsedRequirement")).toBeVisible();
    expect(within(workspace).getByText("requirement-1")).toBeVisible();
    expect(screen.getAllByText("profile-2")).not.toHaveLength(0);
    expect(screen.getByText("Profile 已过期")).toBeVisible();
    expect(screen.getByRole("button", { name: "加入候选" })).toBeEnabled();
    const screeningHistory = screen.getByRole("region", {
      name: "QuickScreen 历史",
    });
    expect(within(screeningHistory).getByText("历史 JobVersion")).toBeVisible();
    expect(
      within(screeningHistory).getByText(/Profile：stale.*false/u),
    ).toBeVisible();
    expect(screen.getByText("Evidence 版本 2")).toBeVisible();

    const requestedPaths = fetchMock.mock.calls.map(([input]) =>
      requestPath(input),
    );
    expect(requestedPaths).toEqual(
      expect.arrayContaining([
        "/api/v1/jobs",
        "/api/v1/jobs/job-1",
        "/api/v1/knowledge/profiles",
        "/api/v1/knowledge/evidence",
      ]),
    );
    for (const [, init] of fetchMock.mock.calls) {
      expect(init).toMatchObject({ method: "GET", cache: "no-store" });
    }
  });

  it("announces a safe readback failure and permits retry", async () => {
    let unavailable = true;
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      if (unavailable)
        return Promise.reject(new Error("secret network detail"));
      const path = requestPath(input);
      if (path.endsWith("/api/v1/jobs")) {
        return Promise.resolve(jsonResponse({ items: [] }));
      }
      if (path.endsWith("/api/v1/knowledge/profiles")) {
        return Promise.resolve(
          jsonResponse({ active_profile_id: null, items: [] }),
        );
      }
      return Promise.resolve(jsonResponse({ items: [] }));
    });
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();

    render(<App idFactory={() => "test-id"} />);

    expect(
      await screen.findByText("后端不可用，请确认本地 API 已启动。"),
    ).toBeVisible();
    expect(
      screen.queryByText(/secret network detail/i),
    ).not.toBeInTheDocument();
    unavailable = false;
    await user.click(screen.getByRole("button", { name: "重新同步" }));

    expect(await screen.findByText("工作区为空，可以开始录入。")).toBeVisible();
  });

  it("switches the selected Job by reading its complete detail", async () => {
    const secondSummary = {
      ...jobSummary,
      job_id: "job-2",
      active_version_id: "job-2-version-1",
      version_number: 1,
      title: "AI Platform Engineer",
      company: "Second AI",
      lifecycle_status: "imported",
      current_screen_recommendation: null,
      current_triage_decision: null,
    };
    const secondDetail = {
      ...jobDetail,
      job_id: "job-2",
      active_version_id: "job-2-version-1",
      lifecycle_status: "imported",
      versions: [
        {
          ...jobDetail.versions[1],
          job_version_id: "job-2-version-1",
          job_id: "job-2",
          version_number: 1,
          title: "AI Platform Engineer",
          company: "Second AI",
          is_active: true,
        },
      ],
      requirements: [],
      screening_results: [],
      triage_history: [],
    };
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const path = requestPath(input);
      if (path.endsWith("/api/v1/jobs/job-1")) {
        return Promise.resolve(jsonResponse(jobDetail));
      }
      if (path.endsWith("/api/v1/jobs/job-2")) {
        return Promise.resolve(jsonResponse(secondDetail));
      }
      if (path.endsWith("/api/v1/jobs")) {
        return Promise.resolve(
          jsonResponse({ items: [jobSummary, secondSummary] }),
        );
      }
      if (path.endsWith("/api/v1/knowledge/profiles")) {
        return Promise.resolve(jsonResponse(profiles));
      }
      return Promise.resolve(jsonResponse(evidence));
    });
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();

    render(<App idFactory={() => "test-id"} />);
    await screen.findByText("工作区已从后端恢复。");
    await user.click(
      screen.getByRole("button", {
        name: "AI Platform Engineer，Second AI",
      }),
    );

    expect(await screen.findByText("职位详情已恢复。")).toBeVisible();
    expect(
      screen.getByRole("button", {
        name: "AI Platform Engineer，Second AI",
      }),
    ).toHaveAttribute("aria-pressed", "true");
    expect(screen.getAllByText("job-2-version-1")).not.toHaveLength(0);
    expect(screen.getByRole("button", { name: "加入候选" })).toBeDisabled();
  });

  it("keeps the current view when selected Job detail returns 404", async () => {
    const missingSummary = {
      ...jobSummary,
      job_id: "missing-job",
      active_version_id: "missing-version",
      title: "Missing Job",
    };
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const path = requestPath(input);
      if (path.endsWith("/api/v1/jobs/job-1")) {
        return Promise.resolve(jsonResponse(jobDetail));
      }
      if (path.endsWith("/api/v1/jobs/missing-job")) {
        return Promise.resolve(
          jsonResponse(
            {
              error: {
                code: "not_found",
                message: "job not found: missing-job",
              },
            },
            404,
          ),
        );
      }
      if (path.endsWith("/api/v1/jobs")) {
        return Promise.resolve(
          jsonResponse({ items: [jobSummary, missingSummary] }),
        );
      }
      if (path.endsWith("/api/v1/knowledge/profiles")) {
        return Promise.resolve(jsonResponse(profiles));
      }
      return Promise.resolve(jsonResponse(evidence));
    });
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();

    render(<App idFactory={() => "test-id"} />);
    await screen.findByText("工作区已从后端恢复。");
    await user.click(
      screen.getByRole("button", { name: "Missing Job，Example AI" }),
    );

    expect(await screen.findByText("未找到所需数据。")).toBeVisible();
    expect(screen.queryByText(/job not found/i)).not.toBeInTheDocument();
    expect(screen.getByText("Profile 已过期")).toBeVisible();
  });

  it("rejects malformed readback without committing unvalidated state", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const path = requestPath(input);
      if (path.endsWith("/api/v1/jobs/job-1")) {
        return Promise.resolve(
          jsonResponse({ job_id: "raw-only", secret: "do-not-render" }),
        );
      }
      if (path.endsWith("/api/v1/jobs")) {
        return Promise.resolve(jsonResponse({ items: [jobSummary] }));
      }
      if (path.endsWith("/api/v1/knowledge/profiles")) {
        return Promise.resolve(jsonResponse(profiles));
      }
      return Promise.resolve(jsonResponse(evidence));
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App idFactory={() => "test-id"} />);

    expect(await screen.findByText("后端返回了无效响应。")).toBeVisible();
    expect(screen.queryByText("raw-only")).not.toBeInTheDocument();
    expect(screen.queryByText("do-not-render")).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", {
        name: "Senior AI Engineer，Example AI",
      }),
    ).not.toBeInTheDocument();
  });

  it("resynchronizes read models after a successful mutation", async () => {
    let hasSavedProfile = false;
    let profileReads = 0;
    const savedProfile = profiles.items[1];
    if (savedProfile === undefined) throw new Error("missing profile fixture");
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const path = requestPath(input);
      if (
        path.endsWith("/api/v1/knowledge/profile") &&
        init?.method === "POST"
      ) {
        hasSavedProfile = true;
        return Promise.resolve(jsonResponse(savedProfile, 201));
      }
      if (path.endsWith("/api/v1/knowledge/profiles")) {
        profileReads += 1;
        return Promise.resolve(
          jsonResponse(
            hasSavedProfile
              ? {
                  active_profile_id: savedProfile.profile_id,
                  items: [savedProfile],
                }
              : { active_profile_id: null, items: [] },
          ),
        );
      }
      return Promise.resolve(jsonResponse({ items: [] }));
    });
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();

    render(<App idFactory={() => "test-id"} />);
    await screen.findByText("工作区为空，可以开始录入。");
    await user.type(
      screen.getByLabelText("目标职位关键词"),
      "Platform Engineer",
    );
    await user.type(screen.getByLabelText("技能关键词"), "Python, FastAPI");
    await user.type(screen.getByLabelText("偏好城市"), "Shenzhen");
    await user.click(screen.getByRole("button", { name: "保存 Profile 快照" }));

    expect(await screen.findByText("工作区已从后端恢复。")).toBeVisible();
    expect(profileReads).toBeGreaterThanOrEqual(2);
    const history = screen.getByRole("region", { name: "Profile 快照历史" });
    expect(within(history).getByText("profile-2")).toBeVisible();
  });
});
