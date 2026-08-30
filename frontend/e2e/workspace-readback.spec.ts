import { expect, test, type Page, type Route } from "@playwright/test";

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

const profileHistory = {
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

const jobOneSummary = {
  job_id: "job-1",
  active_version_id: "job-1-version-2",
  version_number: 2,
  title: "Senior AI Engineer",
  company: "Example AI",
  city: "Shenzhen",
  lifecycle_status: "screened",
  source,
  current_screen_recommendation: "screen_in",
  current_triage_decision: null,
};

const jobTwoSummary = {
  ...jobOneSummary,
  job_id: "job-2",
  active_version_id: "job-2-version-2",
  title: "AI Platform Engineer",
  company: "Second AI",
  lifecycle_status: "imported",
  current_screen_recommendation: null,
};

const jobOne = {
  job_id: "job-1",
  active_version_id: "job-1-version-2",
  lifecycle_status: "screened",
  versions: [
    {
      job_version_id: "job-1-version-1",
      job_id: "job-1",
      version_number: 1,
      title: "AI Engineer",
      company: "Example AI",
      city: "Shenzhen",
      description: "Python experience",
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
      job_version_id: "job-1-version-2",
      job_id: "job-1",
      version_number: 2,
      title: "Senior AI Engineer",
      company: "Example AI",
      city: "Shenzhen",
      description: "Python and FastAPI experience",
      source_snapshot_id: source.snapshot_id,
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
      job_version_id: "job-1-version-2",
      source_text: "Python and FastAPI experience",
      text: "Python and FastAPI experience",
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
      quick_screen_result_id: "screen-historical",
      job_id: "job-1",
      job_version_id: "job-1-version-1",
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
      quick_screen_result_id: "screen-current",
      job_id: "job-1",
      job_version_id: "job-1-version-2",
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
  triage_history: [],
};

const jobTwo = {
  job_id: "job-2",
  active_version_id: "job-2-version-2",
  lifecycle_status: "imported",
  versions: [
    {
      ...jobOne.versions[0],
      job_version_id: "job-2-version-1",
      job_id: "job-2",
      title: "Platform Engineer",
      company: "Second AI",
    },
    {
      ...jobOne.versions[1],
      job_version_id: "job-2-version-2",
      job_id: "job-2",
      title: "AI Platform Engineer",
      company: "Second AI",
    },
  ],
  requirements: [],
  screening_results: [
    {
      ...jobOne.screening_results[0],
      quick_screen_result_id: "job-2-screen-historical",
      job_id: "job-2",
      job_version_id: "job-2-version-1",
    },
  ],
  triage_history: [],
};

const evidenceHistory = {
  items: [
    {
      evidence_id: "evidence-1",
      active_version_id: "evidence-version-1",
      versions: [
        {
          evidence_version_id: "evidence-version-1",
          evidence_id: "evidence-1",
          version_number: 1,
          evidence_type: "project",
          canonical_content: "Built an evaluation pipeline.",
          occurred_on: "2026-06-01",
          source: "manual",
          provenance: "User-confirmed project",
          sensitivity: "private",
          validity: "valid",
          created_at: timestamp,
          correlation_id: "correlation-evidence",
          run_id: "run-evidence",
          is_active: true,
        },
      ],
    },
  ],
};

interface MockState {
  jobListReads: number;
  jobOneReads: number;
  triageBodies: string[];
}

async function fulfillJson(route: Route, body: unknown, status = 200) {
  await route.fulfill({
    status,
    contentType: "application/json",
    headers: { "Cache-Control": "no-store" },
    body: JSON.stringify(body),
  });
}

async function mockWorkspace(page: Page): Promise<MockState> {
  const state: MockState = {
    jobListReads: 0,
    jobOneReads: 0,
    triageBodies: [],
  };
  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (request.method() === "POST" && path === "/api/v1/jobs/job-1/triage") {
      state.triageBodies.push(request.postData() ?? "");
      await fulfillJson(
        route,
        {
          triage_decision_id: "triage-e2e",
          job_id: "job-1",
          quick_screen_result_id: "screen-current",
          recommendation: "screen_in",
          decision: "shortlisted",
          lifecycle_status: "shortlisted",
          decided_at: timestamp,
          correlation_id: "correlation-triage",
          run_id: "run-triage",
        },
        201,
      );
      return;
    }
    if (request.method() !== "GET") {
      await route.abort("failed");
      return;
    }
    if (path === "/api/v1/jobs") {
      state.jobListReads += 1;
      await fulfillJson(route, { items: [jobOneSummary, jobTwoSummary] });
      return;
    }
    if (path === "/api/v1/jobs/job-1") {
      state.jobOneReads += 1;
      await fulfillJson(route, jobOne);
      return;
    }
    if (path === "/api/v1/jobs/job-2") {
      await fulfillJson(route, jobTwo);
      return;
    }
    if (path === "/api/v1/knowledge/profiles") {
      await fulfillJson(route, profileHistory);
      return;
    }
    if (path === "/api/v1/knowledge/evidence") {
      await fulfillJson(route, evidenceHistory);
      return;
    }
    await route.abort("failed");
  });
  return state;
}

test("浏览器刷新会从 GET readback 重建完整工作区", async ({ page }) => {
  const state = await mockWorkspace(page);

  await page.goto("/");
  await expect(page.getByText("工作区已从后端恢复。")).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Senior AI Engineer，Example AI" }),
  ).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByText("版本 2 · Senior AI Engineer")).toBeVisible();
  await expect(
    page
      .getByRole("region", { name: "ParsedRequirement" })
      .getByText("requirement-1"),
  ).toBeVisible();
  await expect(page.getByText("Evidence 版本 1")).toBeVisible();

  await page.reload();

  await expect(page.getByText("工作区已从后端恢复。")).toBeVisible();
  await expect(page.getByText("Profile 已过期")).toBeVisible();
  await expect(page.getByText("screen-historical")).toBeVisible();
  await expect.poll(() => state.jobListReads).toBe(2);
  await expect.poll(() => state.jobOneReads).toBe(2);
});

test("Job 选择遵循后端投影控制 Triage 可操作性", async ({ page }) => {
  const state = await mockWorkspace(page);

  await page.goto("/");
  await expect(page.getByText("工作区已从后端恢复。")).toBeVisible();
  await expect(page.getByText("Profile 已过期")).toBeVisible();
  await expect(page.getByRole("button", { name: "加入候选" })).toBeEnabled();

  await page.getByRole("button", { name: "加入候选" }).click();
  await expect(page.getByText("人工决定已追加。")).toBeVisible();
  await expect.poll(() => state.triageBodies).toHaveLength(1);
  expect(state.triageBodies[0]).toContain(
    '"quick_screen_result_id":"screen-current"',
  );
  expect(state.triageBodies[0]).toContain('"decision":"shortlisted"');

  await page
    .getByRole("button", { name: "AI Platform Engineer，Second AI" })
    .click();
  await expect(page.getByText("职位详情已恢复。")).toBeVisible();
  await expect(
    page.getByRole("button", { name: "AI Platform Engineer，Second AI" }),
  ).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByText("job-2-version-2").first()).toBeVisible();
  await expect(page.getByRole("button", { name: "加入候选" })).toBeDisabled();
  await expect(page.getByRole("button", { name: "跳过" })).toBeDisabled();
  await expect(
    page
      .getByRole("region", { name: "QuickScreen 历史" })
      .getByText("历史 JobVersion"),
  ).toBeVisible();
});
