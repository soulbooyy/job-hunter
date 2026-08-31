import type { RequestStatusValue } from "../../../shared/components/RequestStatus";
import { RequestStatus } from "../../../shared/components/RequestStatus";
import type { JobSummary, JobWorkspace } from "../contracts";

interface WorkspaceReadbackPanelProps {
  jobs: readonly JobSummary[];
  selectedJob: JobWorkspace | null;
  status: RequestStatusValue | null;
  isLoading: boolean;
  onRefresh: () => void;
  onSelectJob: (jobId: string) => void;
}

export function WorkspaceReadbackPanel({
  jobs,
  selectedJob,
  status,
  isLoading,
  onRefresh,
  onSelectJob,
}: WorkspaceReadbackPanelProps) {
  return (
    <section
      className="panel panel--workspace"
      aria-label="后端工作区"
      aria-busy={isLoading}
    >
      <div className="panel-heading">
        <div>
          <p className="eyebrow">后端状态读回</p>
          <h2>后端工作区</h2>
        </div>
        <button
          className="secondary-button"
          type="button"
          disabled={isLoading}
          onClick={onRefresh}
        >
          {isLoading ? "正在同步…" : "重新同步"}
        </button>
      </div>
      <p className="panel-intro">
        页面加载时从本地 API 重建 Job、Profile 和 Evidence
        视图。浏览器不保存这些内容；本地 SQLite
        持久化支持后端进程重启后的工作区恢复。
      </p>
      <RequestStatus value={status} />

      {jobs.length === 0 && !isLoading && status?.tone !== "error" && (
        <p className="empty-state">尚无已保存职位。</p>
      )}

      {jobs.length > 0 && (
        <div className="workspace-readback-layout">
          <nav className="job-navigator" aria-label="已保存职位">
            <h3>已保存职位</h3>
            <ul className="job-list">
              {jobs.map((job) => (
                <li key={job.job_id}>
                  <button
                    className={`job-list-button${
                      selectedJob?.job_id === job.job_id
                        ? " job-list-button--active"
                        : ""
                    }`}
                    type="button"
                    aria-label={`${job.title}，${job.company}`}
                    aria-pressed={selectedJob?.job_id === job.job_id}
                    onClick={() => {
                      onSelectJob(job.job_id);
                    }}
                  >
                    <strong>{job.title}</strong>
                    <span>
                      {job.company} · {job.city}
                    </span>
                    <span className="mono-value">{job.job_id}</span>
                    <span>
                      版本 {job.version_number} · {job.lifecycle_status}
                    </span>
                    <span>
                      QuickScreen：{job.current_screen_recommendation ?? "无"}
                    </span>
                    <span>人工决定：{job.current_triage_decision ?? "无"}</span>
                  </button>
                </li>
              ))}
            </ul>
          </nav>

          {selectedJob !== null && (
            <div className="lineage-view">
              <div className="result-card-heading">
                <div>
                  <p className="eyebrow">当前选择</p>
                  <h3>{selectedJob.lifecycle_status}</h3>
                </div>
                <span className="mono-value">{selectedJob.job_id}</span>
              </div>

              <section className="history-block" aria-label="JobVersion 历史">
                <h3>JobVersion 历史</h3>
                <ol className="history-list">
                  {selectedJob.versions.map((version) => (
                    <li key={version.job_version_id}>
                      <article className="history-card history-card--stacked">
                        <div className="result-card-heading">
                          <div>
                            <strong>
                              版本 {version.version_number} · {version.title}
                            </strong>
                            <p>
                              {version.company} · {version.city}
                            </p>
                          </div>
                          <span
                            className={`state-chip ${
                              version.is_active
                                ? "state-chip--success"
                                : "state-chip--muted"
                            }`}
                          >
                            {version.is_active ? "current" : "historical"}
                          </span>
                        </div>
                        <p className="lineage-content">{version.description}</p>
                        <dl className="detail-grid detail-grid--compact">
                          <div>
                            <dt>JobVersion ID</dt>
                            <dd className="mono-value">
                              {version.job_version_id}
                            </dd>
                          </div>
                          <div>
                            <dt>SourceSnapshot ID</dt>
                            <dd className="mono-value">
                              {version.source_snapshot_id}
                            </dd>
                          </div>
                          <div>
                            <dt>SourceReference ID</dt>
                            <dd className="mono-value">
                              {version.source.reference_id}
                            </dd>
                          </div>
                          <div>
                            <dt>来源</dt>
                            <dd>
                              {version.source.kind} · {version.source.freshness}
                            </dd>
                          </div>
                          <div>
                            <dt>来源定位</dt>
                            <dd className="break-value">
                              {version.source.locator ?? "手动录入"}
                            </dd>
                          </div>
                          <div>
                            <dt>采集 / 验证时间</dt>
                            <dd>
                              {version.source.captured_at} /{" "}
                              {version.source.last_verified_at}
                            </dd>
                          </div>
                          <div>
                            <dt>Correlation ID</dt>
                            <dd className="mono-value">
                              {version.correlation_id}
                            </dd>
                          </div>
                          <div>
                            <dt>Run ID / 创建时间</dt>
                            <dd className="mono-value">
                              {version.run_id} / {version.created_at}
                            </dd>
                          </div>
                        </dl>
                      </article>
                    </li>
                  ))}
                </ol>
              </section>

              <section className="history-block" aria-label="ParsedRequirement">
                <h3>ParsedRequirement</h3>
                {selectedJob.requirements.length === 0 ? (
                  <p className="empty-state">当前没有解析出的 Requirement。</p>
                ) : (
                  <ol className="history-list">
                    {selectedJob.requirements.map((requirement) => (
                      <li key={requirement.requirement_id}>
                        <article className="history-card history-card--stacked">
                          <div className="result-card-heading">
                            <strong>{requirement.text}</strong>
                            <span className="mono-value">
                              {requirement.requirement_id}
                            </span>
                          </div>
                          <dl className="detail-grid detail-grid--compact">
                            <div>
                              <dt>JobVersion ID</dt>
                              <dd className="mono-value">
                                {requirement.job_version_id}
                              </dd>
                            </div>
                            <div>
                              <dt>类型 / 优先级</dt>
                              <dd>
                                {requirement.requirement_type} ·{" "}
                                {requirement.priority}
                              </dd>
                            </div>
                            <div>
                              <dt>原始文本</dt>
                              <dd>{requirement.source_text}</dd>
                            </div>
                            <div>
                              <dt>Parser</dt>
                              <dd>
                                {requirement.parser_name} ·{" "}
                                {requirement.parser_version}
                              </dd>
                            </div>
                            <div>
                              <dt>Correlation ID</dt>
                              <dd className="mono-value">
                                {requirement.correlation_id}
                              </dd>
                            </div>
                            <div>
                              <dt>Run ID / 创建时间</dt>
                              <dd className="mono-value">
                                {requirement.run_id} / {requirement.created_at}
                              </dd>
                            </div>
                          </dl>
                        </article>
                      </li>
                    ))}
                  </ol>
                )}
              </section>
            </div>
          )}
        </div>
      )}
    </section>
  );
}
