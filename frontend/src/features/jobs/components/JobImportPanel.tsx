import { useState, type SyntheticEvent } from "react";

import { getErrorMessage } from "../../../api/errors";
import {
  RequestStatus,
  type RequestStatusValue,
} from "../../../shared/components/RequestStatus";
import type { IdFactory } from "../../../shared/id";
import { importJob } from "../api";
import type { ActiveJob, ImportedJob, ManualJobInput } from "../contracts";

interface JobImportPanelProps {
  activeJob: ActiveJob | null;
  correlationId: string;
  idFactory: IdFactory;
  onImported: (job: ImportedJob) => void;
}

export function JobImportPanel({
  activeJob,
  correlationId,
  idFactory,
  onImported,
}: JobImportPanelProps) {
  const [sourceType, setSourceType] = useState<"manual_jd" | "manual_url">(
    "manual_jd",
  );
  const [url, setUrl] = useState("");
  const [title, setTitle] = useState("");
  const [company, setCompany] = useState("");
  const [city, setCity] = useState("");
  const [content, setContent] = useState("");
  const [createVersion, setCreateVersion] = useState(false);
  const [isImporting, setIsImporting] = useState(false);
  const [status, setStatus] = useState<RequestStatusValue | null>(null);

  async function handleSubmit(
    event: SyntheticEvent<HTMLFormElement, SubmitEvent>,
  ) {
    event.preventDefault();
    if (isImporting) return;
    setIsImporting(true);
    setStatus({ tone: "progress", message: "正在导入职位…" });
    const sharedInput = { title, company, city, content };
    const input: ManualJobInput =
      sourceType === "manual_url"
        ? { sourceType, url, ...sharedInput }
        : { sourceType, ...sharedInput };
    try {
      const imported = await importJob({
        input,
        existingJobId: createVersion ? (activeJob?.job_id ?? null) : null,
        correlationId,
        runId: idFactory(),
      });
      onImported(imported);
      setStatus({ tone: "success", message: "职位版本已导入。" });
    } catch (error: unknown) {
      setStatus({ tone: "error", message: getErrorMessage(error) });
    } finally {
      setIsImporting(false);
    }
  }

  return (
    <section className="panel panel--wide" aria-labelledby="job-heading">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">02 · 职位录入</p>
          <h2 id="job-heading">手动职位导入</h2>
        </div>
        <span className="state-chip">版本化来源</span>
      </div>
      <p className="panel-intro">
        导入粘贴的 JD，或导入 URL 与你提供的职位内容。URL
        模式不会自动抓取页面，本次采集以 content 字段为准。
      </p>

      <form onSubmit={(event) => void handleSubmit(event)}>
        <fieldset className="choice-row">
          <legend>来源模式</legend>
          <label className="choice-card">
            <input
              aria-label="Manual JD"
              type="radio"
              name="source-type"
              checked={sourceType === "manual_jd"}
              onChange={() => {
                setSourceType("manual_jd");
              }}
            />
            Manual JD
          </label>
          <label className="choice-card">
            <input
              aria-label="Manual URL + 用户提供内容"
              type="radio"
              name="source-type"
              checked={sourceType === "manual_url"}
              onChange={() => {
                setSourceType("manual_url");
              }}
            />
            Manual URL + 用户提供内容
          </label>
        </fieldset>
        {sourceType === "manual_url" && (
          <label>
            职位 URL
            <input
              aria-label="职位 URL"
              type="url"
              value={url}
              onChange={(event) => {
                setUrl(event.target.value);
              }}
              placeholder="https://jobs.example/roles/1"
              required
            />
          </label>
        )}
        <div className="form-grid">
          <label>
            职位名称
            <input
              aria-label="职位名称"
              value={title}
              onChange={(event) => {
                setTitle(event.target.value);
              }}
              required
            />
          </label>
          <label>
            公司
            <input
              aria-label="公司"
              value={company}
              onChange={(event) => {
                setCompany(event.target.value);
              }}
              required
            />
          </label>
          <label>
            城市
            <input
              aria-label="城市"
              value={city}
              onChange={(event) => {
                setCity(event.target.value);
              }}
              required
            />
          </label>
        </div>
        <label>
          职位描述内容
          <textarea
            aria-label="职位描述内容"
            className="content-area"
            value={content}
            onChange={(event) => {
              setContent(event.target.value);
            }}
            required
          />
        </label>
        <label className="checkbox-row">
          <input
            aria-label="为当前职位创建新版本"
            type="checkbox"
            checked={createVersion}
            disabled={activeJob === null}
            onChange={(event) => {
              setCreateVersion(event.target.checked);
            }}
          />
          为当前职位创建新版本
        </label>
        <button className="primary-button" type="submit" disabled={isImporting}>
          {isImporting ? "正在导入…" : "导入职位"}
        </button>
      </form>
      <RequestStatus value={status} />

      {activeJob !== null && (
        <article
          className="result-card result-card--accent"
          aria-label="当前职位版本"
        >
          <div className="result-card-heading">
            <div>
              <p className="eyebrow">当前会话职位</p>
              <h3>版本 {activeJob.version_number}</h3>
            </div>
            <span className="mono-value">{activeJob.job_id}</span>
          </div>
          <dl className="detail-grid">
            <div>
              <dt>JobVersion ID</dt>
              <dd className="mono-value">{activeJob.job_version_id}</dd>
            </div>
            <div>
              <dt>来源类型</dt>
              <dd>{activeJob.source.kind}</dd>
            </div>
            <div>
              <dt>来源定位</dt>
              <dd className="break-value">
                {activeJob.source.locator ?? "手动录入"}
              </dd>
            </div>
            <div>
              <dt>新鲜度</dt>
              <dd>{activeJob.source.freshness}</dd>
            </div>
            <div>
              <dt>采集时间</dt>
              <dd>{activeJob.source.captured_at}</dd>
            </div>
            <div>
              <dt>最近验证时间</dt>
              <dd>{activeJob.source.last_verified_at}</dd>
            </div>
          </dl>
        </article>
      )}
    </section>
  );
}
