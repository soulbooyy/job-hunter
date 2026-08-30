import { useState, type SyntheticEvent } from "react";

import { getErrorMessage } from "../../../api/errors";
import type { IdFactory } from "../../../shared/id";
import {
  RequestStatus,
  type RequestStatusValue,
} from "../../../shared/components/RequestStatus";
import { saveCandidateProfile } from "../api";
import type { CandidateProfile } from "../contracts";

interface CandidateProfilePanelProps {
  activeProfile: CandidateProfile | null;
  history: readonly CandidateProfile[];
  correlationId: string;
  idFactory: IdFactory;
  onSaved: (profile: CandidateProfile) => void;
}

function parseKeywords(value: string): string[] {
  return value
    .split(/[,\n]/u)
    .map((item) => item.trim())
    .filter((item) => item.length > 0);
}

export function CandidateProfilePanel({
  activeProfile,
  history,
  correlationId,
  idFactory,
  onSaved,
}: CandidateProfilePanelProps) {
  const [targetRoles, setTargetRoles] = useState("");
  const [skills, setSkills] = useState("");
  const [cities, setCities] = useState("");
  const [isSaving, setIsSaving] = useState(false);
  const [status, setStatus] = useState<RequestStatusValue | null>(null);

  async function handleSubmit(
    event: SyntheticEvent<HTMLFormElement, SubmitEvent>,
  ) {
    event.preventDefault();
    if (isSaving) return;
    setIsSaving(true);
    setStatus({ tone: "progress", message: "正在保存 Profile…" });
    try {
      const profile = await saveCandidateProfile({
        input: {
          targetRoleKeywords: parseKeywords(targetRoles),
          skillKeywords: parseKeywords(skills),
          preferredCities: parseKeywords(cities),
        },
        correlationId,
        runId: idFactory(),
      });
      onSaved(profile);
      setStatus({ tone: "success", message: "Profile 快照已保存。" });
    } catch (error: unknown) {
      setStatus({ tone: "error", message: getErrorMessage(error) });
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <section className="panel" aria-labelledby="profile-heading">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">01 · 候选人信息</p>
          <h2 id="profile-heading">Candidate Profile</h2>
        </div>
        <span className="state-chip">不可变快照</span>
      </div>
      <p className="panel-intro">
        仅保存经人工确认的筛选事实。再次保存会创建新的活跃快照，不会修改历史
        QuickScreen 结果。
      </p>

      <form onSubmit={(event) => void handleSubmit(event)}>
        <label>
          目标职位关键词
          <textarea
            aria-label="目标职位关键词"
            value={targetRoles}
            onChange={(event) => {
              setTargetRoles(event.target.value);
            }}
            placeholder="AI Engineer, LLM Application Engineer"
            required
          />
          <span className="field-hint">使用逗号或换行分隔</span>
        </label>
        <label>
          技能关键词
          <textarea
            aria-label="技能关键词"
            value={skills}
            onChange={(event) => {
              setSkills(event.target.value);
            }}
            placeholder="Python, LangGraph"
            required
          />
          <span className="field-hint">仅填写已确认的技能</span>
        </label>
        <label>
          偏好城市
          <input
            aria-label="偏好城市"
            value={cities}
            onChange={(event) => {
              setCities(event.target.value);
            }}
            placeholder="Shenzhen"
          />
        </label>
        <button className="primary-button" type="submit" disabled={isSaving}>
          {isSaving ? "正在保存…" : "保存 Profile 快照"}
        </button>
      </form>
      <RequestStatus value={status} />

      {activeProfile !== null && (
        <article
          className="result-card result-card--accent"
          aria-label="当前 Profile 快照"
        >
          <div className="result-card-heading">
            <h3>当前规范化 Profile</h3>
            <span className="mono-value">{activeProfile.profile_id}</span>
          </div>
          <dl className="detail-grid">
            <div>
              <dt>目标职位</dt>
              <dd>{activeProfile.target_role_keywords.join(", ")}</dd>
            </div>
            <div>
              <dt>技能</dt>
              <dd>{activeProfile.skill_keywords.join(", ")}</dd>
            </div>
            <div>
              <dt>偏好城市</dt>
              <dd>{activeProfile.preferred_cities.join(", ") || "无偏好"}</dd>
            </div>
            <div>
              <dt>创建时间</dt>
              <dd>{activeProfile.created_at}</dd>
            </div>
          </dl>
        </article>
      )}

      {history.length > 0 && (
        <section className="history-block" aria-label="Profile 快照历史">
          <h3>Profile 快照历史</h3>
          <ol className="history-list">
            {history.map((profile) => (
              <li key={profile.profile_id}>
                <article className="history-card history-card--stacked">
                  <div className="result-card-heading">
                    <span className="mono-value">{profile.profile_id}</span>
                    <span
                      className={`state-chip ${
                        profile.profile_id === activeProfile?.profile_id
                          ? "state-chip--success"
                          : "state-chip--muted"
                      }`}
                    >
                      {profile.profile_id === activeProfile?.profile_id
                        ? "current"
                        : "historical"}
                    </span>
                  </div>
                  <dl className="detail-grid detail-grid--compact">
                    <div>
                      <dt>目标职位</dt>
                      <dd>{profile.target_role_keywords.join(", ")}</dd>
                    </div>
                    <div>
                      <dt>技能</dt>
                      <dd>{profile.skill_keywords.join(", ")}</dd>
                    </div>
                    <div>
                      <dt>偏好城市</dt>
                      <dd>{profile.preferred_cities.join(", ") || "无偏好"}</dd>
                    </div>
                    <div>
                      <dt>创建时间</dt>
                      <dd>{profile.created_at}</dd>
                    </div>
                    <div>
                      <dt>Correlation ID</dt>
                      <dd className="mono-value">{profile.correlation_id}</dd>
                    </div>
                    <div>
                      <dt>Run ID</dt>
                      <dd className="mono-value">{profile.run_id}</dd>
                    </div>
                  </dl>
                </article>
              </li>
            ))}
          </ol>
        </section>
      )}
    </section>
  );
}
