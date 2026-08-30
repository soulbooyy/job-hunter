import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { App } from "../app/App";

type JsonRecord = Record<string, unknown>;

const jsonResponse = (body: JsonRecord, status = 201) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });

const profileResponse = (id = "profile-1") => ({
  profile_id: id,
  target_role_keywords: ["AI Engineer"],
  skill_keywords: ["Python"],
  preferred_cities: ["Shenzhen"],
  created_at: "2026-08-29T09:00:00Z",
  correlation_id: "correlation-profile",
  run_id: "run-profile",
});

const jobResponse = (overrides: JsonRecord = {}) => ({
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
  correlation_id: "correlation-job",
  run_id: "run-job",
  ...overrides,
});

const screenResponse = (
  recommendation = "screen_in",
  id = "screen-1",
  profileId = "profile-1",
) => ({
  quick_screen_result_id: id,
  job_id: "job-1",
  job_version_id: "job-version-1",
  candidate_profile_id: profileId,
  requirement_ids: ["requirement-1", "requirement-2"],
  recommendation,
  reason_codes:
    recommendation === "screen_out"
      ? ["city_outside_preference"]
      : recommendation === "uncertain"
        ? ["insufficient_signal"]
        : ["target_role_match", "skill_overlap"],
  policy_version: "quick-screen-v1",
  lifecycle_status: "screened",
  created_at: "2026-08-29T09:00:00Z",
  correlation_id: "correlation-job",
  run_id: `run-${id}`,
});

const triageResponse = (
  decision: "shortlisted" | "skipped",
  id = "triage-1",
) => ({
  triage_decision_id: id,
  job_id: "job-1",
  quick_screen_result_id: "screen-1",
  recommendation: "screen_in",
  decision,
  lifecycle_status: decision,
  decided_at: "2026-08-29T09:00:00Z",
  correlation_id: "correlation-job",
  run_id: `run-${id}`,
});

function createIdFactory() {
  let value = 0;
  return () => `test-id-${String((value += 1))}`;
}

async function saveProfile(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByLabelText("目标职位关键词"), "AI Engineer");
  await user.type(screen.getByLabelText("技能关键词"), "Python");
  await user.type(screen.getByLabelText("偏好城市"), "Shenzhen");
  await user.click(screen.getByRole("button", { name: "保存 Profile 快照" }));
}

async function importJob(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByLabelText("职位名称"), "Senior AI Engineer");
  await user.type(screen.getByLabelText("公司"), "Example AI");
  await user.type(screen.getByLabelText("城市"), "Shenzhen");
  await user.type(
    screen.getByLabelText("职位描述内容"),
    "Must have Python experience",
  );
  await user.click(screen.getByRole("button", { name: "导入职位" }));
}

function renderWorkspace(fetchMock: ReturnType<typeof vi.fn>) {
  vi.stubGlobal("fetch", fetchMock);
  render(<App idFactory={createIdFactory()} enableWorkspaceQueries={false} />);
}

function readJsonRequestBody(call: unknown): unknown {
  if (!Array.isArray(call)) throw new Error("Expected a fetch call");
  const options: unknown = call[1];
  if (
    typeof options !== "object" ||
    options === null ||
    !("body" in options) ||
    typeof options.body !== "string"
  ) {
    throw new Error("Expected a JSON request body");
  }
  const parsed: unknown = JSON.parse(options.body);
  return parsed;
}

describe("Job Hunter workspace", () => {
  it("uses Simplified Chinese user copy while preserving product terms", () => {
    renderWorkspace(vi.fn());

    expect(screen.getByRole("heading", { name: "Job Hunter" })).toBeVisible();
    expect(screen.getByText("本地优先求职工作区")).toBeVisible();
    expect(
      screen.getByRole("heading", { name: "Candidate Profile" }),
    ).toBeVisible();
    expect(
      screen.getByRole("heading", { name: "QuickScreen 与人工职位筛选" }),
    ).toBeVisible();
    expect(
      screen.getByRole("button", { name: "保存 Profile 快照" }),
    ).toBeVisible();
    expect(
      screen.queryByText("Local-first application workspace"),
    ).not.toBeInTheDocument();
  });

  it("shows Manual JD source, freshness, version, and the full Profile → Import → QuickScreen → Shortlisted path", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(profileResponse()))
      .mockResolvedValueOnce(jsonResponse(jobResponse()))
      .mockResolvedValueOnce(jsonResponse(screenResponse()))
      .mockResolvedValueOnce(jsonResponse(triageResponse("shortlisted")));
    renderWorkspace(fetchMock);
    const user = userEvent.setup();

    await saveProfile(user);
    expect(await screen.findAllByText("profile-1")).not.toHaveLength(0);
    await importJob(user);
    expect(await screen.findByText("manual_jd")).toBeVisible();
    expect(screen.getByText("fresh")).toBeVisible();
    expect(screen.getByText("版本 1")).toBeVisible();

    await user.click(screen.getByRole("button", { name: "运行 QuickScreen" }));
    const currentScreen = await screen.findByLabelText("当前 QuickScreen 结果");
    expect(within(currentScreen).getByText("screen_in")).toBeVisible();
    expect(within(currentScreen).getByText("quick-screen-v1")).toBeVisible();
    expect(
      within(currentScreen).getByText("requirement-1, requirement-2"),
    ).toBeVisible();
    expect(
      screen.getByText(/不是 DeepFit，也不使用 Evidence 或 RAG/i),
    ).toBeVisible();

    await user.click(screen.getByRole("button", { name: "加入候选" }));
    expect(await screen.findByText("人工决定：shortlisted")).toBeVisible();
    expect(
      screen.getByText(
        /不代表获得 MaterialApproval、Ready 状态或外部执行授权/i,
      ),
    ).toBeVisible();
  });

  it("sends user-provided content for Manual URL and displays the locator", async () => {
    const locator = "https://jobs.example/roles/1";
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse(
        jobResponse({
          source: {
            kind: "manual_url",
            locator,
            captured_at: "2026-08-29T09:00:00Z",
            last_verified_at: "2026-08-29T09:00:00Z",
            freshness: "fresh",
          },
        }),
      ),
    );
    renderWorkspace(fetchMock);
    const user = userEvent.setup();

    await user.click(screen.getByLabelText("Manual URL + 用户提供内容"));
    await user.type(screen.getByLabelText("职位 URL"), locator);
    await importJob(user);

    expect(await screen.findByText(locator)).toBeVisible();
    expect(screen.getByText(/不会自动抓取页面/i)).toBeVisible();
    const firstCall: unknown = fetchMock.mock.calls[0];
    expect(readJsonRequestBody(firstCall)).toMatchObject({
      source: {
        source_type: "manual_url",
        url: locator,
        content: "Must have Python experience",
      },
    });
  });

  it.each(["screen_out", "uncertain"])(
    "renders %s as a QuickScreen recommendation",
    async (recommendation) => {
      const fetchMock = vi
        .fn()
        .mockResolvedValueOnce(jsonResponse(profileResponse()))
        .mockResolvedValueOnce(jsonResponse(jobResponse()))
        .mockResolvedValueOnce(jsonResponse(screenResponse(recommendation)));
      renderWorkspace(fetchMock);
      const user = userEvent.setup();
      await saveProfile(user);
      await importJob(user);
      await user.click(
        screen.getByRole("button", { name: "运行 QuickScreen" }),
      );

      expect(await screen.findByText(recommendation)).toBeVisible();
      expect(
        screen.queryByText(/DeepFit recommendation/i),
      ).not.toBeInTheDocument();
    },
  );

  it("marks an old Profile result stale, recommends re-screening, and still allows Triage", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(profileResponse()))
      .mockResolvedValueOnce(jsonResponse(jobResponse()))
      .mockResolvedValueOnce(jsonResponse(screenResponse()))
      .mockResolvedValueOnce(jsonResponse(profileResponse("profile-2")))
      .mockResolvedValueOnce(jsonResponse(triageResponse("shortlisted")));
    renderWorkspace(fetchMock);
    const user = userEvent.setup();
    await saveProfile(user);
    await importJob(user);
    await user.click(screen.getByRole("button", { name: "运行 QuickScreen" }));
    await user.click(screen.getByRole("button", { name: "保存 Profile 快照" }));

    expect(await screen.findByText("Profile 已过期")).toBeVisible();
    expect(
      screen.getByText(/不是基于最新 Profile.*建议重新筛选/i),
    ).toBeVisible();
    expect(screen.getByRole("button", { name: "加入候选" })).toBeEnabled();
    await user.click(screen.getByRole("button", { name: "加入候选" }));
    expect(await screen.findByText("人工决定：shortlisted")).toBeVisible();
  });

  it("appends a re-screen result and retains historical results", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(profileResponse()))
      .mockResolvedValueOnce(jsonResponse(jobResponse()))
      .mockResolvedValueOnce(
        jsonResponse(screenResponse("uncertain", "screen-1")),
      )
      .mockResolvedValueOnce(
        jsonResponse(screenResponse("screen_in", "screen-2")),
      );
    renderWorkspace(fetchMock);
    const user = userEvent.setup();
    await saveProfile(user);
    await importJob(user);
    await user.click(screen.getByRole("button", { name: "运行 QuickScreen" }));
    await user.click(screen.getByRole("button", { name: "运行 QuickScreen" }));

    const history = await screen.findByRole("region", {
      name: "QuickScreen 历史",
    });
    expect(within(history).getByText("screen-1")).toBeVisible();
    expect(within(history).getByText("screen-2")).toBeVisible();
    expect(within(history).getByText("当前可操作")).toBeVisible();
  });

  it("keeps old screening history but disables it after a new JobVersion", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(profileResponse()))
      .mockResolvedValueOnce(jsonResponse(jobResponse()))
      .mockResolvedValueOnce(jsonResponse(screenResponse()))
      .mockResolvedValueOnce(
        jsonResponse(
          jobResponse({
            job_version_id: "job-version-2",
            active_version_id: "job-version-2",
            version_number: 2,
          }),
        ),
      );
    renderWorkspace(fetchMock);
    const user = userEvent.setup();
    await saveProfile(user);
    await importJob(user);
    await user.click(screen.getByRole("button", { name: "运行 QuickScreen" }));
    await user.click(screen.getByLabelText("为当前职位创建新版本"));
    await user.click(screen.getByRole("button", { name: "导入职位" }));

    expect(await screen.findByText("版本 2")).toBeVisible();
    expect(screen.getByText("历史 JobVersion")).toBeVisible();
    expect(screen.getByRole("button", { name: "加入候选" })).toBeDisabled();
  });

  it("appends human decisions and permits shortlisted/skipped overrides", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(profileResponse()))
      .mockResolvedValueOnce(jsonResponse(jobResponse()))
      .mockResolvedValueOnce(jsonResponse(screenResponse()))
      .mockResolvedValueOnce(
        jsonResponse(triageResponse("shortlisted", "triage-1")),
      )
      .mockResolvedValueOnce(
        jsonResponse(triageResponse("skipped", "triage-2")),
      );
    renderWorkspace(fetchMock);
    const user = userEvent.setup();
    await saveProfile(user);
    await importJob(user);
    await user.click(screen.getByRole("button", { name: "运行 QuickScreen" }));
    await user.click(screen.getByRole("button", { name: "加入候选" }));
    await user.click(screen.getByRole("button", { name: "跳过" }));

    expect(await screen.findByText("人工决定：skipped")).toBeVisible();
    const history = screen.getByRole("region", { name: "人工筛选历史" });
    expect(within(history).getByText("triage-1")).toBeVisible();
    expect(within(history).getByText("triage-2")).toBeVisible();
  });

  it("creates and versions Evidence while preserving provenance", async () => {
    const evidence = (version: number) => ({
      evidence_id: "evidence-1",
      evidence_version_id: `evidence-version-${String(version)}`,
      active_version_id: `evidence-version-${String(version)}`,
      version_number: version,
      evidence_type: "project",
      canonical_content: "Built an evaluation system.",
      occurred_on: "2026-06-01",
      source: "manual",
      provenance: "User-confirmed project record",
      sensitivity: "private",
      validity: "valid",
      created_at: "2026-08-29T09:00:00Z",
      correlation_id: "correlation-evidence",
      run_id: `run-evidence-${String(version)}`,
    });
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(evidence(1)))
      .mockResolvedValueOnce(jsonResponse(evidence(2)));
    renderWorkspace(fetchMock);
    const user = userEvent.setup();

    await user.type(
      screen.getByLabelText("Evidence 规范内容"),
      "Built an evaluation system.",
    );
    await user.type(screen.getByLabelText("发生日期"), "2026-06-01");
    await user.type(screen.getByLabelText("Evidence 来源"), "manual");
    await user.type(
      screen.getByLabelText("来源依据"),
      "User-confirmed project record",
    );
    await user.click(screen.getByRole("button", { name: "保存 Evidence" }));
    expect(await screen.findByText("Evidence 版本 1")).toBeVisible();
    await user.click(screen.getByLabelText("为当前 Evidence 创建新版本"));
    await user.click(screen.getByRole("button", { name: "保存 Evidence" }));

    expect(await screen.findByText("Evidence 版本 2")).toBeVisible();
    expect(screen.getAllByText("User-confirmed project record")).toHaveLength(
      2,
    );
    expect(screen.getByText(/QuickScreen 不使用 Evidence/i)).toBeVisible();
    const secondCall: unknown = fetchMock.mock.calls[1];
    expect(readJsonRequestBody(secondCall)).toMatchObject({
      existing_evidence_id: "evidence-1",
    });
  });

  it("shows safe malformed/network failures and keeps unvalidated data out of state", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        jsonResponse({
          profile_id: "raw-only",
          private_detail: "do-not-render",
        }),
      )
      .mockRejectedValueOnce(new Error("secret transport detail"));
    renderWorkspace(fetchMock);
    const user = userEvent.setup();
    await saveProfile(user);

    expect(await screen.findByText("后端返回了无效响应。")).toBeVisible();
    expect(screen.queryByText("raw-only")).not.toBeInTheDocument();
    expect(screen.queryByText("do-not-render")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "保存 Profile 快照" }));
    expect(
      await screen.findByText("后端不可用，请确认本地 API 已启动。"),
    ).toBeVisible();
    expect(
      screen.queryByText(/secret transport detail/i),
    ).not.toBeInTheDocument();
  });

  it("prevents duplicate submissions while loading and announces completion", async () => {
    let resolveRequest!: (response: Response) => void;
    const fetchMock = vi.fn().mockReturnValue(
      new Promise<Response>((resolve) => {
        resolveRequest = resolve;
      }),
    );
    renderWorkspace(fetchMock);
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("目标职位关键词"), "AI Engineer");
    await user.type(screen.getByLabelText("技能关键词"), "Python");
    const submit = screen.getByRole("button", {
      name: "保存 Profile 快照",
    });
    await user.click(submit);

    expect(submit).toBeDisabled();
    expect(screen.getByRole("status")).toHaveTextContent("正在保存 Profile");
    resolveRequest(jsonResponse(profileResponse()));
    expect(await screen.findByText("Profile 快照已保存。")).toBeVisible();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("turns a backend 409 during Triage into re-screen guidance", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(profileResponse()))
      .mockResolvedValueOnce(jsonResponse(jobResponse()))
      .mockResolvedValueOnce(jsonResponse(screenResponse()))
      .mockResolvedValueOnce(
        jsonResponse(
          {
            error: {
              code: "conflict",
              message: "quick screen result is stale",
            },
          },
          409,
        ),
      );
    renderWorkspace(fetchMock);
    const user = userEvent.setup();
    await saveProfile(user);
    await importJob(user);
    await user.click(screen.getByRole("button", { name: "运行 QuickScreen" }));
    await user.click(screen.getByRole("button", { name: "加入候选" }));

    expect(
      await screen.findByText(/QuickScreen 结果已过期.*重新运行 QuickScreen/i),
    ).toBeVisible();
  });
});
