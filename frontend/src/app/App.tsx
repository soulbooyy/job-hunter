import { useState } from "react";

import { CandidateProfilePanel } from "../features/candidate-profile/components/CandidateProfilePanel";
import type { CandidateProfile } from "../features/candidate-profile/contracts";
import { EvidencePanel } from "../features/evidence/components/EvidencePanel";
import type { Evidence } from "../features/evidence/contracts";
import { JobImportPanel } from "../features/jobs/components/JobImportPanel";
import type { ImportedJob } from "../features/jobs/contracts";
import { ScreeningPanel } from "../features/screening/components/ScreeningPanel";
import type {
  QuickScreenResult,
  TriageResult,
} from "../features/screening/contracts";
import { randomId, type IdFactory } from "../shared/id";

interface AppProps {
  idFactory?: IdFactory;
}

export function App({ idFactory = randomId }: AppProps) {
  const [profileCorrelationId] = useState(() => idFactory());
  const [jobCorrelationId] = useState(() => idFactory());
  const [evidenceCorrelationId] = useState(() => idFactory());
  const [activeProfile, setActiveProfile] = useState<CandidateProfile | null>(
    null,
  );
  const [activeJob, setActiveJob] = useState<ImportedJob | null>(null);
  const [screeningHistory, setScreeningHistory] = useState<QuickScreenResult[]>(
    [],
  );
  const [triageHistory, setTriageHistory] = useState<TriageResult[]>([]);
  const [evidenceHistory, setEvidenceHistory] = useState<Evidence[]>([]);

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
          仅当前会话
        </div>
      </header>

      <aside className="session-notice" aria-label="会话存储限制">
        <strong>私密的临时工作区。</strong>
        <span>
          Profile、职位内容和 Evidence 仅保存在 React
          内存中，不会写入浏览器存储或 URL。由于 GET/read
          接口尚未实现，刷新后无法恢复当前状态。
        </span>
      </aside>

      <main className="workspace-grid">
        <CandidateProfilePanel
          activeProfile={activeProfile}
          correlationId={profileCorrelationId}
          idFactory={idFactory}
          onSaved={setActiveProfile}
        />
        <JobImportPanel
          activeJob={activeJob}
          correlationId={jobCorrelationId}
          idFactory={idFactory}
          onImported={setActiveJob}
        />
        <ScreeningPanel
          activeJob={activeJob}
          activeProfile={activeProfile}
          screeningHistory={screeningHistory}
          triageHistory={triageHistory}
          correlationId={jobCorrelationId}
          idFactory={idFactory}
          onScreened={(result) => {
            setScreeningHistory((history) => [...history, result]);
          }}
          onTriaged={(result) => {
            setTriageHistory((history) => [...history, result]);
          }}
        />
        <EvidencePanel
          history={evidenceHistory}
          correlationId={evidenceCorrelationId}
          idFactory={idFactory}
          onSaved={(result) => {
            setEvidenceHistory((history) => [...history, result]);
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
