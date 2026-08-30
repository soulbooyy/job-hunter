import { expect, test, type Page, type Route } from "@playwright/test";

const timestamp = "2026-08-30T10:00:00Z";

const source = {
  reference_id: "source-reference-e2e",
  snapshot_id: "source-snapshot-e2e",
  kind: "manual_jd",
  locator: null,
  captured_at: timestamp,
  last_verified_at: timestamp,
  freshness: "fresh",
};

const profile = {
  profile_id: "profile-e2e",
  target_role_keywords: ["AI Engineer"],
  skill_keywords: ["Python", "FastAPI"],
  preferred_cities: ["Shenzhen"],
  created_at: timestamp,
  correlation_id: "correlation-profile-e2e",
  run_id: "run-profile-e2e",
};

const importedJob = {
  job_id: "job-e2e",
  job_version_id: "job-version-e2e",
  active_version_id: "job-version-e2e",
  source_snapshot_id: source.snapshot_id,
  version_number: 1,
  lifecycle_status: "imported",
  source: {
    kind: source.kind,
    locator: source.locator,
    captured_at: source.captured_at,
    last_verified_at: source.last_verified_at,
    freshness: source.freshness,
  },
  correlation_id: "correlation-job-e2e",
  run_id: "run-job-e2e",
};

const screening = {
  quick_screen_result_id: "screen-e2e",
  job_id: importedJob.job_id,
  job_version_id: importedJob.job_version_id,
  candidate_profile_id: profile.profile_id,
  requirement_ids: ["requirement-e2e"],
  recommendation: "screen_in",
  reason_codes: ["target_role_match", "skill_overlap"],
  policy_version: "quick-screen-v1",
  lifecycle_status: "screened",
  created_at: timestamp,
  correlation_id: "correlation-screen-e2e",
  run_id: "run-screen-e2e",
};

const triage = {
  triage_decision_id: "triage-e2e",
  job_id: importedJob.job_id,
  quick_screen_result_id: screening.quick_screen_result_id,
  recommendation: screening.recommendation,
  decision: "shortlisted",
  lifecycle_status: "shortlisted",
  decided_at: timestamp,
  correlation_id: "correlation-triage-e2e",
  run_id: "run-triage-e2e",
};

interface ManualWorkflowState {
  profileSaved: boolean;
  jobImported: boolean;
  screened: boolean;
  triaged: boolean;
  mutationBodies: string[];
}

async function fulfillJson(route: Route, body: unknown, status = 200) {
  await route.fulfill({
    status,
    contentType: "application/json",
    headers: { "Cache-Control": "no-store" },
    body: JSON.stringify(body),
  });
}

function jobSummary(state: ManualWorkflowState) {
  return {
    job_id: importedJob.job_id,
    active_version_id: importedJob.active_version_id,
    version_number: 1,
    title: "Senior AI Engineer",
    company: "Example AI",
    city: "Shenzhen",
    lifecycle_status: state.triaged
      ? "shortlisted"
      : state.screened
        ? "screened"
        : "imported",
    source,
    current_screen_recommendation: state.screened ? "screen_in" : null,
    current_triage_decision: state.triaged ? "shortlisted" : null,
  };
}

function jobDetail(state: ManualWorkflowState) {
  return {
    job_id: importedJob.job_id,
    active_version_id: importedJob.active_version_id,
    lifecycle_status: state.triaged
      ? "shortlisted"
      : state.screened
        ? "screened"
        : "imported",
    versions: [
      {
        job_version_id: importedJob.job_version_id,
        job_id: importedJob.job_id,
        version_number: 1,
        title: "Senior AI Engineer",
        company: "Example AI",
        city: "Shenzhen",
        description: "Python and FastAPI experience",
        source_snapshot_id: source.snapshot_id,
        source,
        created_at: timestamp,
        correlation_id: "correlation-job-e2e",
        run_id: "run-job-e2e",
        is_active: true,
      },
    ],
    requirements: [
      {
        requirement_id: "requirement-e2e",
        job_version_id: importedJob.job_version_id,
        source_text: "Python and FastAPI experience",
        text: "Python and FastAPI experience",
        requirement_type: "skill",
        priority: "required",
        parser_name: "deterministic-line-parser",
        parser_version: "v1",
        created_at: timestamp,
        correlation_id: "correlation-job-e2e",
        run_id: "run-job-e2e",
      },
    ],
    screening_results: state.screened
      ? [
          {
            ...screening,
            profile_status: "current",
            job_version_status: "current",
            is_latest_result: true,
            triage_eligible: true,
          },
        ]
      : [],
    triage_history: state.triaged ? [triage] : [],
  };
}

async function mockManualWorkflow(page: Page): Promise<ManualWorkflowState> {
  const state: ManualWorkflowState = {
    profileSaved: false,
    jobImported: false,
    screened: false,
    triaged: false,
    mutationBodies: [],
  };
  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (request.method() === "POST") {
      state.mutationBodies.push(request.postData() ?? "");
      if (path === "/api/v1/knowledge/profile") {
        state.profileSaved = true;
        await fulfillJson(route, profile, 201);
        return;
      }
      if (path === "/api/v1/jobs/import") {
        state.jobImported = true;
        await fulfillJson(route, importedJob, 201);
        return;
      }
      if (path === "/api/v1/jobs/job-e2e/screen") {
        state.screened = true;
        await fulfillJson(route, screening, 201);
        return;
      }
      if (path === "/api/v1/jobs/job-e2e/triage") {
        state.triaged = true;
        await fulfillJson(route, triage, 201);
        return;
      }
    }
    if (request.method() === "GET") {
      if (path === "/api/v1/jobs") {
        await fulfillJson(route, {
          items: state.jobImported ? [jobSummary(state)] : [],
        });
        return;
      }
      if (path === "/api/v1/jobs/job-e2e" && state.jobImported) {
        await fulfillJson(route, jobDetail(state));
        return;
      }
      if (path === "/api/v1/knowledge/profiles") {
        await fulfillJson(route, {
          active_profile_id: state.profileSaved ? profile.profile_id : null,
          items: state.profileSaved ? [profile] : [],
        });
        return;
      }
      if (path === "/api/v1/knowledge/evidence") {
        await fulfillJson(route, { items: [] });
        return;
      }
    }
    await route.abort("failed");
  });
  return state;
}

test("Manual JD path 完成 Profile、QuickScreen 与 Human Triage", async ({
  page,
}) => {
  const state = await mockManualWorkflow(page);
  await page.goto("/");

  await page.getByLabel("目标职位关键词").fill("AI Engineer");
  await page.getByLabel("技能关键词").fill("Python, FastAPI");
  await page.getByLabel("偏好城市").fill("Shenzhen");
  await page.getByRole("button", { name: "保存 Profile 快照" }).click();
  await expect(page.getByText("Profile 快照已保存。")).toBeVisible();

  await page.getByLabel("职位名称").fill("Senior AI Engineer");
  await page.getByLabel("公司").fill("Example AI");
  await page.getByLabel("城市", { exact: true }).fill("Shenzhen");
  await page.getByLabel("职位描述内容").fill("Python and FastAPI experience");
  await page.getByRole("button", { name: "导入职位" }).click();
  await expect(page.getByText("职位版本已导入。")).toBeVisible();

  await page.getByRole("button", { name: "运行 QuickScreen" }).click();
  await expect(page.getByText("QuickScreen 结果已追加。")).toBeVisible();
  await expect(
    page.getByRole("article", { name: "当前 QuickScreen 结果" }),
  ).toContainText("screen_in");

  await page.getByRole("button", { name: "加入候选" }).click();
  await expect(page.getByText("人工决定已追加。")).toBeVisible();
  await expect(
    page
      .getByRole("region", { name: "QuickScreen 与人工职位筛选" })
      .getByText("人工决定：shortlisted"),
  ).toBeVisible();

  await page.reload();
  await expect(page.getByText("工作区已从后端恢复。")).toBeVisible();
  await expect(
    page
      .getByRole("region", { name: "QuickScreen 与人工职位筛选" })
      .getByText("人工决定：shortlisted"),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Senior AI Engineer，Example AI" }),
  ).toHaveAttribute("aria-pressed", "true");

  expect(state.mutationBodies).toHaveLength(4);
  expect(state.mutationBodies[0]).toContain(
    '"skill_keywords":["Python","FastAPI"]',
  );
  expect(state.mutationBodies[1]).toContain('"source_type":"manual_jd"');
  expect(state.mutationBodies[1]).toContain(
    '"content":"Python and FastAPI experience"',
  );
  expect(state.mutationBodies[3]).toContain(
    '"quick_screen_result_id":"screen-e2e"',
  );
  expect(state.mutationBodies[3]).toContain('"decision":"shortlisted"');
});

test("后端网络不可用时安全提示并允许恢复", async ({ page }) => {
  let unavailable = true;
  await page.route("**/api/v1/**", async (route) => {
    if (unavailable) {
      await route.abort("connectionrefused");
      return;
    }
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/v1/knowledge/profiles") {
      await fulfillJson(route, { active_profile_id: null, items: [] });
      return;
    }
    await fulfillJson(route, { items: [] });
  });

  await page.goto("/");
  await expect(
    page.getByText("后端不可用，请确认本地 API 已启动。"),
  ).toBeVisible();
  await expect(page.getByText(/ERR_CONNECTION_REFUSED/u)).toHaveCount(0);

  unavailable = false;
  await page.getByRole("button", { name: "重新同步" }).click();
  await expect(page.getByText("工作区为空，可以开始录入。")).toBeVisible();
  await expect(page.getByText("尚无已保存职位。")).toBeVisible();
});
