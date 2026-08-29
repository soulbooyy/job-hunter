import { useState } from "react";

import { ApiError, getErrorMessage } from "../../../api/errors";
import type { CandidateProfile } from "../../candidate-profile/contracts";
import type { ImportedJob } from "../../jobs/contracts";
import {
  RequestStatus,
  type RequestStatusValue,
} from "../../../shared/components/RequestStatus";
import type { IdFactory } from "../../../shared/id";
import { recordTriage, runQuickScreen } from "../api";
import type {
  QuickScreenResult,
  TriageDecision,
  TriageResult,
} from "../contracts";
import { deriveScreeningView } from "../view-model";

interface ScreeningPanelProps {
  activeJob: ImportedJob | null;
  activeProfile: CandidateProfile | null;
  screeningHistory: readonly QuickScreenResult[];
  triageHistory: readonly TriageResult[];
  correlationId: string;
  idFactory: IdFactory;
  onScreened: (result: QuickScreenResult) => void;
  onTriaged: (result: TriageResult) => void;
}

export function ScreeningPanel({
  activeJob,
  activeProfile,
  screeningHistory,
  triageHistory,
  correlationId,
  idFactory,
  onScreened,
  onTriaged,
}: ScreeningPanelProps) {
  const [isScreening, setIsScreening] = useState(false);
  const [isTriaging, setIsTriaging] = useState(false);
  const [screenStatus, setScreenStatus] = useState<RequestStatusValue | null>(
    null,
  );
  const [triageStatus, setTriageStatus] = useState<RequestStatusValue | null>(
    null,
  );

  const { currentResult, currentDecision, isProfileStale } =
    deriveScreeningView(
      activeJob,
      activeProfile,
      screeningHistory,
      triageHistory,
    );
  const canScreen = activeJob !== null && activeProfile !== null;
  const canTriage = currentResult !== null;

  async function handleScreen() {
    if (!canScreen || isScreening) return;
    setIsScreening(true);
    setScreenStatus({ tone: "progress", message: "正在运行 QuickScreen…" });
    try {
      const result = await runQuickScreen({
        jobId: activeJob.job_id,
        correlationId,
        runId: idFactory(),
      });
      onScreened(result);
      setScreenStatus({
        tone: "success",
        message: "QuickScreen 结果已追加。",
      });
      setTriageStatus(null);
    } catch (error: unknown) {
      setScreenStatus({ tone: "error", message: getErrorMessage(error) });
    } finally {
      setIsScreening(false);
    }
  }

  async function handleTriage(decision: TriageDecision) {
    if (activeJob === null || currentResult === null || isTriaging) return;
    setIsTriaging(true);
    setTriageStatus({ tone: "progress", message: "正在记录人工决定…" });
    try {
      const result = await recordTriage({
        jobId: activeJob.job_id,
        quickScreenResultId: currentResult.quick_screen_result_id,
        decision,
        correlationId,
        runId: idFactory(),
      });
      onTriaged(result);
      setTriageStatus({ tone: "success", message: "人工决定已追加。" });
    } catch (error: unknown) {
      const message =
        error instanceof ApiError && error.code === "conflict"
          ? "当前 QuickScreen 结果已过期。请重新运行 QuickScreen 后再进行人工筛选。"
          : getErrorMessage(error);
      setTriageStatus({ tone: "error", message });
    } finally {
      setIsTriaging(false);
    }
  }

  return (
    <section className="panel panel--wide" aria-labelledby="screening-heading">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">03 · 低成本决策支持</p>
          <h2 id="screening-heading">QuickScreen 与人工职位筛选</h2>
        </div>
        <span className="state-chip">当前会话追加历史</span>
      </div>
      <p className="panel-intro">
        QuickScreen 不是 DeepFit，也不使用 Evidence 或
        RAG。它只提供轻量推荐，人工决定始终独立保留。
      </p>

      <div className="workflow-controls">
        <button
          className="primary-button"
          type="button"
          disabled={!canScreen || isScreening}
          onClick={() => void handleScreen()}
        >
          {isScreening ? "正在筛选…" : "运行 QuickScreen"}
        </button>
        {!canScreen && (
          <p className="field-hint">
            请先在当前会话中保存 Profile 并导入职位。
          </p>
        )}
      </div>
      <RequestStatus value={screenStatus} />

      {currentResult !== null && (
        <article
          className="result-card result-card--accent"
          aria-label="当前 QuickScreen 结果"
        >
          <div className="result-card-heading">
            <div>
              <p className="eyebrow">系统推荐</p>
              <strong
                className={`recommendation recommendation--${currentResult.recommendation}`}
              >
                {currentResult.recommendation}
              </strong>
            </div>
            <span className="mono-value">
              {currentResult.quick_screen_result_id}
            </span>
          </div>
          {isProfileStale && (
            <div className="warning-callout">
              <strong>Profile 已过期</strong>
              <p>
                该结果不是基于最新 Profile。建议重新筛选，但当前 JobVersion
                仍允许人工筛选。
              </p>
            </div>
          )}
          <dl className="detail-grid">
            <div>
              <dt>策略版本</dt>
              <dd>{currentResult.policy_version}</dd>
            </div>
            <div>
              <dt>JobVersion ID</dt>
              <dd className="mono-value">{currentResult.job_version_id}</dd>
            </div>
            <div>
              <dt>CandidateProfile ID</dt>
              <dd className="mono-value">
                {currentResult.candidate_profile_id}
              </dd>
            </div>
            <div>
              <dt>Requirement IDs</dt>
              <dd>{currentResult.requirement_ids.join(", ") || "无"}</dd>
            </div>
            <div>
              <dt>原因代码</dt>
              <dd>{currentResult.reason_codes.join(", ")}</dd>
            </div>
            <div>
              <dt>创建时间</dt>
              <dd>{currentResult.created_at}</dd>
            </div>
          </dl>
        </article>
      )}

      <div className="triage-block">
        <div className="triage-copy">
          <h3>人工职位筛选</h3>
          <p>加入候选不代表获得 MaterialApproval、Ready 状态或外部执行授权。</p>
          {currentResult !== null && (
            <p>系统推荐：{currentResult.recommendation}</p>
          )}
          {currentDecision !== null && (
            <p className="decision-line">
              人工决定：{currentDecision.decision}
            </p>
          )}
        </div>
        <div className="button-row">
          <button
            className="primary-button"
            type="button"
            disabled={!canTriage || isTriaging}
            onClick={() => void handleTriage("shortlisted")}
          >
            加入候选
          </button>
          <button
            className="secondary-button"
            type="button"
            disabled={!canTriage || isTriaging}
            onClick={() => void handleTriage("skipped")}
          >
            跳过
          </button>
        </div>
      </div>
      <RequestStatus value={triageStatus} />

      {screeningHistory.length > 0 && (
        <section className="history-block" aria-label="QuickScreen 历史">
          <h3>QuickScreen 历史</h3>
          <ol className="history-list">
            {screeningHistory.map((result) => {
              const latest =
                result.quick_screen_result_id ===
                currentResult?.quick_screen_result_id;
              const historicalVersion =
                result.job_version_id !== activeJob?.job_version_id;
              return (
                <li key={result.quick_screen_result_id}>
                  <article className="history-card">
                    <div>
                      <span className="mono-value">
                        {result.quick_screen_result_id}
                      </span>
                      <p>推荐：{result.recommendation}</p>
                    </div>
                    <div className="history-tags">
                      {latest && (
                        <span className="state-chip state-chip--success">
                          当前可操作
                        </span>
                      )}
                      {historicalVersion && (
                        <span className="state-chip state-chip--muted">
                          历史 JobVersion
                        </span>
                      )}
                    </div>
                  </article>
                </li>
              );
            })}
          </ol>
        </section>
      )}

      {triageHistory.length > 0 && (
        <section className="history-block" aria-label="人工筛选历史">
          <h3>人工筛选历史</h3>
          <ol className="history-list">
            {triageHistory.map((result) => (
              <li key={result.triage_decision_id}>
                <article className="history-card">
                  <span className="mono-value">
                    {result.triage_decision_id}
                  </span>
                  <p>
                    {result.recommendation} → {result.decision}
                  </p>
                </article>
              </li>
            ))}
          </ol>
        </section>
      )}
    </section>
  );
}
