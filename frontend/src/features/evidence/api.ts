import { requestJson } from "../../api/client";
import {
  evidenceResponseSchema,
  type Evidence,
  type EvidenceInput,
} from "./contracts";

interface SaveEvidenceOptions {
  input: EvidenceInput;
  existingEvidenceId: string | null;
  correlationId: string;
  runId: string;
}

export function saveEvidence(options: SaveEvidenceOptions): Promise<Evidence> {
  return requestJson(
    "/api/v1/knowledge/evidence",
    {
      method: "POST",
      body: JSON.stringify({
        existing_evidence_id: options.existingEvidenceId,
        evidence_type: options.input.evidenceType,
        canonical_content: options.input.canonicalContent,
        occurred_on: options.input.occurredOn,
        source: options.input.source,
        provenance: options.input.provenance,
        sensitivity: options.input.sensitivity,
        validity: options.input.validity,
        correlation_id: options.correlationId,
        run_id: options.runId,
      }),
    },
    evidenceResponseSchema,
  );
}
