import { requestJson } from "../../api/client";
import {
  importJobResponseSchema,
  type ImportedJob,
  type ManualJobInput,
} from "./contracts";

interface ImportJobOptions {
  input: ManualJobInput;
  existingJobId: string | null;
  correlationId: string;
  runId: string;
}

export function importJob(options: ImportJobOptions): Promise<ImportedJob> {
  const source =
    options.input.sourceType === "manual_url"
      ? {
          source_type: options.input.sourceType,
          url: options.input.url,
          title: options.input.title,
          company: options.input.company,
          city: options.input.city,
          content: options.input.content,
        }
      : {
          source_type: options.input.sourceType,
          title: options.input.title,
          company: options.input.company,
          city: options.input.city,
          content: options.input.content,
        };

  return requestJson(
    "/api/v1/jobs/import",
    {
      method: "POST",
      body: JSON.stringify({
        correlation_id: options.correlationId,
        run_id: options.runId,
        existing_job_id: options.existingJobId,
        source,
      }),
    },
    importJobResponseSchema,
  );
}
