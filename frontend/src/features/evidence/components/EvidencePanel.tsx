import { useEffect, useState, type SyntheticEvent } from "react";

import { getErrorMessage } from "../../../api/errors";
import {
  RequestStatus,
  type RequestStatusValue,
} from "../../../shared/components/RequestStatus";
import type { IdFactory } from "../../../shared/id";
import { saveEvidence } from "../api";
import type {
  Evidence,
  EvidenceSensitivity,
  EvidenceType,
  EvidenceValidity,
} from "../contracts";
import {
  evidenceSensitivitySchema,
  evidenceTypeSchema,
  evidenceValiditySchema,
} from "../contracts";

interface EvidencePanelProps {
  history: readonly Evidence[];
  correlationId: string;
  idFactory: IdFactory;
  onSaved: (evidence: Evidence) => void;
}

const evidenceTypes: readonly EvidenceType[] = [
  "project",
  "experience",
  "education",
  "certification",
  "skill",
  "other",
];
const sensitivities: readonly EvidenceSensitivity[] = [
  "public",
  "private",
  "sensitive",
];
const validities: readonly EvidenceValidity[] = ["valid", "expired", "revoked"];

export function EvidencePanel({
  history,
  correlationId,
  idFactory,
  onSaved,
}: EvidencePanelProps) {
  const [selectedEvidenceId, setSelectedEvidenceId] = useState("");
  const evidenceIds = Array.from(
    new Set(history.map((item) => item.evidence_id)),
  );
  const selectedHistory = history.filter(
    (item) => item.evidence_id === selectedEvidenceId,
  );
  const activeEvidence =
    selectedHistory.find(
      (item) => item.evidence_version_id === item.active_version_id,
    ) ?? null;
  const [evidenceType, setEvidenceType] = useState<EvidenceType>("project");
  const [canonicalContent, setCanonicalContent] = useState("");
  const [occurredOn, setOccurredOn] = useState("");
  const [source, setSource] = useState("");
  const [provenance, setProvenance] = useState("");
  const [sensitivity, setSensitivity] =
    useState<EvidenceSensitivity>("private");
  const [validity, setValidity] = useState<EvidenceValidity>("valid");
  const [createVersion, setCreateVersion] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [status, setStatus] = useState<RequestStatusValue | null>(null);

  useEffect(() => {
    if (evidenceIds.length > 0 && !evidenceIds.includes(selectedEvidenceId)) {
      setSelectedEvidenceId(evidenceIds[0] ?? "");
    }
  }, [evidenceIds, selectedEvidenceId]);

  async function handleSubmit(
    event: SyntheticEvent<HTMLFormElement, SubmitEvent>,
  ) {
    event.preventDefault();
    if (isSaving) return;
    setIsSaving(true);
    setStatus({ tone: "progress", message: "正在保存 Evidence…" });
    try {
      const result = await saveEvidence({
        input: {
          evidenceType,
          canonicalContent,
          occurredOn: occurredOn.length > 0 ? occurredOn : null,
          source,
          provenance,
          sensitivity,
          validity,
        },
        existingEvidenceId: createVersion
          ? (activeEvidence?.evidence_id ?? null)
          : null,
        correlationId,
        runId: idFactory(),
      });
      onSaved(result);
      setSelectedEvidenceId(result.evidence_id);
      setStatus({ tone: "success", message: "Evidence 版本已保存。" });
    } catch (error: unknown) {
      setStatus({ tone: "error", message: getErrorMessage(error) });
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <section className="panel" aria-labelledby="evidence-heading">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">独立知识录入</p>
          <h2 id="evidence-heading">手动 Evidence</h2>
        </div>
        <span className="state-chip">不可变版本</span>
      </div>
      <p className="panel-intro">
        QuickScreen 不使用
        Evidence。本面板只创建权威的手动版本，不执行自动合并、事实推断、批量导入或
        RAG。
      </p>

      <form onSubmit={(event) => void handleSubmit(event)}>
        {evidenceIds.length > 0 && (
          <label>
            当前 Evidence
            <select
              aria-label="当前 Evidence"
              value={selectedEvidenceId}
              onChange={(event) => {
                setSelectedEvidenceId(event.target.value);
                setCreateVersion(false);
              }}
            >
              {evidenceIds.map((evidenceId) => (
                <option key={evidenceId} value={evidenceId}>
                  {evidenceId}
                </option>
              ))}
            </select>
          </label>
        )}
        <div className="form-grid">
          <label>
            Evidence 类型
            <select
              aria-label="Evidence 类型"
              value={evidenceType}
              onChange={(event) => {
                const parsed = evidenceTypeSchema.safeParse(event.target.value);
                if (parsed.success) setEvidenceType(parsed.data);
              }}
            >
              {evidenceTypes.map((value) => (
                <option key={value} value={value}>
                  {value}
                </option>
              ))}
            </select>
          </label>
          <label>
            发生日期
            <input
              aria-label="发生日期"
              type="date"
              value={occurredOn}
              onChange={(event) => {
                setOccurredOn(event.target.value);
              }}
            />
          </label>
        </div>
        <label>
          Evidence 规范内容
          <textarea
            aria-label="Evidence 规范内容"
            className="content-area"
            value={canonicalContent}
            onChange={(event) => {
              setCanonicalContent(event.target.value);
            }}
            required
          />
        </label>
        <div className="form-grid">
          <label>
            Evidence 来源
            <input
              aria-label="Evidence 来源"
              value={source}
              onChange={(event) => {
                setSource(event.target.value);
              }}
              required
            />
          </label>
          <label>
            来源依据
            <input
              aria-label="来源依据"
              value={provenance}
              onChange={(event) => {
                setProvenance(event.target.value);
              }}
              required
            />
          </label>
          <label>
            敏感级别
            <select
              aria-label="敏感级别"
              value={sensitivity}
              onChange={(event) => {
                const parsed = evidenceSensitivitySchema.safeParse(
                  event.target.value,
                );
                if (parsed.success) setSensitivity(parsed.data);
              }}
            >
              {sensitivities.map((value) => (
                <option key={value} value={value}>
                  {value}
                </option>
              ))}
            </select>
          </label>
          <label>
            有效状态
            <select
              aria-label="有效状态"
              value={validity}
              onChange={(event) => {
                const parsed = evidenceValiditySchema.safeParse(
                  event.target.value,
                );
                if (parsed.success) setValidity(parsed.data);
              }}
            >
              {validities.map((value) => (
                <option key={value} value={value}>
                  {value}
                </option>
              ))}
            </select>
          </label>
        </div>
        <label className="checkbox-row">
          <input
            aria-label="为当前 Evidence 创建新版本"
            type="checkbox"
            checked={createVersion}
            disabled={activeEvidence === null}
            onChange={(event) => {
              setCreateVersion(event.target.checked);
            }}
          />
          为当前 Evidence 创建新版本
        </label>
        <button className="primary-button" type="submit" disabled={isSaving}>
          {isSaving ? "正在保存…" : "保存 Evidence"}
        </button>
      </form>
      <RequestStatus value={status} />

      {history.length > 0 && (
        <section className="history-block" aria-label="Evidence 版本历史">
          <h3>Evidence 版本历史</h3>
          <ol className="history-list">
            {history.map((item) => (
              <li key={item.evidence_version_id}>
                <article className="history-card history-card--stacked">
                  <div className="result-card-heading">
                    <div>
                      <strong>Evidence 版本 {item.version_number}</strong>
                      <p className="mono-value">{item.evidence_version_id}</p>
                    </div>
                    {item.active_version_id === item.evidence_version_id && (
                      <span className="state-chip state-chip--success">
                        当前活跃版本
                      </span>
                    )}
                  </div>
                  <dl className="detail-grid">
                    <div>
                      <dt>Evidence ID</dt>
                      <dd className="mono-value">{item.evidence_id}</dd>
                    </div>
                    <div>
                      <dt>活跃版本 ID</dt>
                      <dd className="mono-value">{item.active_version_id}</dd>
                    </div>
                    <div>
                      <dt>来源依据</dt>
                      <dd>{item.provenance}</dd>
                    </div>
                    <div>
                      <dt>规范内容</dt>
                      <dd>{item.canonical_content}</dd>
                    </div>
                    <div>
                      <dt>类型 / 发生日期</dt>
                      <dd>
                        {item.evidence_type} · {item.occurred_on ?? "未填写"}
                      </dd>
                    </div>
                    <div>
                      <dt>来源</dt>
                      <dd>{item.source}</dd>
                    </div>
                    <div>
                      <dt>状态</dt>
                      <dd>
                        {item.sensitivity} · {item.validity}
                      </dd>
                    </div>
                    <div>
                      <dt>Correlation ID</dt>
                      <dd className="mono-value">{item.correlation_id}</dd>
                    </div>
                    <div>
                      <dt>Run ID / 创建时间</dt>
                      <dd className="mono-value">
                        {item.run_id} / {item.created_at}
                      </dd>
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
