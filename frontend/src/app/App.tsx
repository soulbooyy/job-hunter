import { useEffect, useRef, useState } from "react";

import { getErrorMessage } from "../api/errors";
import { CandidateProfilePanel } from "../features/candidate-profile/components/CandidateProfilePanel";
import type { CandidateProfile } from "../features/candidate-profile/contracts";
import { EvidencePanel } from "../features/evidence/components/EvidencePanel";
import type { Evidence } from "../features/evidence/contracts";
import { JobImportPanel } from "../features/jobs/components/JobImportPanel";
import type { ActiveJob, ImportedJob } from "../features/jobs/contracts";
import { ScreeningPanel } from "../features/screening/components/ScreeningPanel";
import type {
  QuickScreenResult,
  QuickScreenViewResult,
  TriageResult,
} from "../features/screening/contracts";
import {
  getJob,
  listCandidateProfiles,
  listEvidence,
  listJobs,
} from "../features/workspace/api";
import { WorkspaceReadbackPanel } from "../features/workspace/components/WorkspaceReadbackPanel";
import type {
  EvidenceItemRead,
  JobSummary,
  JobWorkspace,
} from "../features/workspace/contracts";
import type { RequestStatusValue } from "../shared/components/RequestStatus";
import { randomId, type IdFactory } from "../shared/id";

interface AppProps {
  idFactory?: IdFactory;
  enableWorkspaceQueries?: boolean;
}

function activeJobFromWorkspace(workspace: JobWorkspace): ActiveJob | null {
  const version = workspace.versions.find(
    (item) =>
      item.job_version_id === workspace.active_version_id && item.is_active,
  );
  if (version === undefined) return null;
  return {
    job_id: workspace.job_id,
    job_version_id: version.job_version_id,
    active_version_id: workspace.active_version_id,
    source_snapshot_id: version.source_snapshot_id,
    version_number: version.version_number,
    lifecycle_status: workspace.lifecycle_status,
    source: {
      kind: version.source.kind,
      locator: version.source.locator,
      captured_at: version.source.captured_at,
      last_verified_at: version.source.last_verified_at,
      freshness: version.source.freshness,
    },
  };
}

function flattenEvidence(items: readonly EvidenceItemRead[]): Evidence[] {
  return items.flatMap((item) =>
    item.versions.map((version) => ({
      evidence_id: version.evidence_id,
      evidence_version_id: version.evidence_version_id,
      active_version_id: item.active_version_id,
      version_number: version.version_number,
      evidence_type: version.evidence_type,
      canonical_content: version.canonical_content,
      occurred_on: version.occurred_on,
      source: version.source,
      provenance: version.provenance,
      sensitivity: version.sensitivity,
      validity: version.validity,
      created_at: version.created_at,
      correlation_id: version.correlation_id,
      run_id: version.run_id,
    })),
  );
}

function mergeEvidenceMutation(
  history: readonly Evidence[],
  saved: Evidence,
): Evidence[] {
  const prior = history
    .filter((item) => item.evidence_version_id !== saved.evidence_version_id)
    .map((item) =>
      item.evidence_id === saved.evidence_id
        ? { ...item, active_version_id: saved.active_version_id }
        : item,
    );
  return [...prior, saved];
}

export function App({
  idFactory = randomId,
  enableWorkspaceQueries = true,
}: AppProps) {
  const [profileCorrelationId] = useState(() => idFactory());
  const [jobCorrelationId] = useState(() => idFactory());
  const [evidenceCorrelationId] = useState(() => idFactory());
  const [profiles, setProfiles] = useState<CandidateProfile[]>([]);
  const [activeProfile, setActiveProfile] = useState<CandidateProfile | null>(
    null,
  );
  const [jobs, setJobs] = useState<readonly JobSummary[]>([]);
  const [selectedJob, setSelectedJob] = useState<JobWorkspace | null>(null);
  const [activeJob, setActiveJob] = useState<ActiveJob | null>(null);
  const [screeningHistory, setScreeningHistory] = useState<
    QuickScreenViewResult[]
  >([]);
  const [triageHistory, setTriageHistory] = useState<TriageResult[]>([]);
  const [evidenceHistory, setEvidenceHistory] = useState<Evidence[]>([]);
  const [workspaceStatus, setWorkspaceStatus] =
    useState<RequestStatusValue | null>(null);
  const [isWorkspaceLoading, setIsWorkspaceLoading] = useState(false);
  const hydrationStarted = useRef(false);
  const requestSequence = useRef(0);

  function applyJobWorkspace(workspace: JobWorkspace | null) {
    setSelectedJob(workspace);
    setActiveJob(workspace === null ? null : activeJobFromWorkspace(workspace));
    setScreeningHistory(workspace?.screening_results ?? []);
    setTriageHistory(workspace?.triage_history ?? []);
  }

  async function synchronizeWorkspace(preferredJobId: string | null) {
    const sequence = requestSequence.current + 1;
    requestSequence.current = sequence;
    setIsWorkspaceLoading(true);
    setWorkspaceStatus({ tone: "progress", message: "正在读取后端工作区…" });
    try {
      const [jobItems, profileHistory, evidenceItems] = await Promise.all([
        listJobs(),
        listCandidateProfiles(),
        listEvidence(),
      ]);
      const selectedId =
        jobItems.find((item) => item.job_id === preferredJobId)?.job_id ??
        jobItems[0]?.job_id ??
        null;
      const workspace = selectedId === null ? null : await getJob(selectedId);
      if (requestSequence.current !== sequence) return;

      // Commit only after every unknown JSON boundary has validated, so partial or
      // malformed readback cannot leak into the currently usable workspace state.
      setJobs(jobItems);
      setProfiles(profileHistory.items);
      setActiveProfile(
        profileHistory.items.find(
          (item) => item.profile_id === profileHistory.active_profile_id,
        ) ?? null,
      );
      setEvidenceHistory(flattenEvidence(evidenceItems.items));
      applyJobWorkspace(workspace);
      const isEmpty =
        jobItems.length === 0 &&
        profileHistory.items.length === 0 &&
        evidenceItems.items.length === 0;
      setWorkspaceStatus({
        tone: "success",
        message: isEmpty
          ? "工作区为空，可以开始录入。"
          : "工作区已从后端恢复。",
      });
    } catch (error: unknown) {
      if (requestSequence.current === sequence) {
        setWorkspaceStatus({ tone: "error", message: getErrorMessage(error) });
      }
    } finally {
      if (requestSequence.current === sequence) setIsWorkspaceLoading(false);
    }
  }

  async function selectJob(jobId: string) {
    const sequence = requestSequence.current + 1;
    requestSequence.current = sequence;
    setIsWorkspaceLoading(true);
    setWorkspaceStatus({ tone: "progress", message: "正在读取职位详情…" });
    try {
      const workspace = await getJob(jobId);
      if (requestSequence.current !== sequence) return;
      applyJobWorkspace(workspace);
      setWorkspaceStatus({ tone: "success", message: "职位详情已恢复。" });
    } catch (error: unknown) {
      if (requestSequence.current === sequence) {
        setWorkspaceStatus({ tone: "error", message: getErrorMessage(error) });
      }
    } finally {
      if (requestSequence.current === sequence) setIsWorkspaceLoading(false);
    }
  }

  function resynchronizeAfterMutation(jobId: string | null) {
    if (enableWorkspaceQueries) void synchronizeWorkspace(jobId);
  }

  useEffect(() => {
    if (!enableWorkspaceQueries || hydrationStarted.current) return;
    hydrationStarted.current = true;
    void synchronizeWorkspace(null);
  }, [enableWorkspaceQueries]);

  return (
    <div className="app-shell">
      <header className="app-header">
        <div className="brand-mark" aria-hidden="true">
          JH
        </div>
        <div>
          <p className="eyebrow">本地优先求职工作区</p>
          <h1>Job Hunter</h1>
          <p className="header-copy">
            从原始职位内容出发，形成由你掌控的人工筛选决定。
          </p>
        </div>
        <div className="session-badge">
          <span className="session-dot" aria-hidden="true" />
          后端状态可读回
        </div>
      </header>

      <aside className="session-notice" aria-label="本地数据边界">
        <strong>私密的本地工作区。</strong>
        <span>
          页面刷新或后端进程重启后，会从本地 SQLite 数据库重新读取 Profile、Job
          和 Evidence；内容不会写入浏览器存储、日志或
          URL。数据仅保存在当前设备，不提供跨设备同步或自动备份。
        </span>
      </aside>

      <main className="workspace-grid">
        <WorkspaceReadbackPanel
          jobs={jobs}
          selectedJob={selectedJob}
          status={workspaceStatus}
          isLoading={isWorkspaceLoading}
          onRefresh={() => {
            void synchronizeWorkspace(
              selectedJob?.job_id ?? activeJob?.job_id ?? null,
            );
          }}
          onSelectJob={(jobId) => {
            void selectJob(jobId);
          }}
        />
        <CandidateProfilePanel
          activeProfile={activeProfile}
          history={profiles}
          correlationId={profileCorrelationId}
          idFactory={idFactory}
          onSaved={(profile) => {
            setProfiles((history) => [...history, profile]);
            setActiveProfile(profile);
            resynchronizeAfterMutation(activeJob?.job_id ?? null);
          }}
        />
        <JobImportPanel
          activeJob={activeJob}
          correlationId={jobCorrelationId}
          idFactory={idFactory}
          onImported={(job: ImportedJob) => {
            const changedJob = activeJob?.job_id !== job.job_id;
            setActiveJob(job);
            if (changedJob) {
              setSelectedJob(null);
              setScreeningHistory([]);
              setTriageHistory([]);
            }
            resynchronizeAfterMutation(job.job_id);
          }}
        />
        <ScreeningPanel
          activeJob={activeJob}
          activeProfile={activeProfile}
          screeningHistory={screeningHistory}
          triageHistory={triageHistory}
          correlationId={jobCorrelationId}
          idFactory={idFactory}
          onScreened={(result: QuickScreenResult) => {
            setScreeningHistory((history) => [...history, result]);
            resynchronizeAfterMutation(result.job_id);
          }}
          onTriaged={(result) => {
            setTriageHistory((history) => [...history, result]);
            resynchronizeAfterMutation(result.job_id);
          }}
        />
        <EvidencePanel
          history={evidenceHistory}
          correlationId={evidenceCorrelationId}
          idFactory={idFactory}
          onSaved={(result) => {
            setEvidenceHistory((history) =>
              mergeEvidenceMutation(history, result),
            );
            resynchronizeAfterMutation(activeJob?.job_id ?? null);
          }}
        />
      </main>

      <footer className="app-footer">
        <span>Job Hunter · localhost 工作区</span>
        <span>当前切片不提供任何外部操作。</span>
      </footer>
    </div>
  );
}
