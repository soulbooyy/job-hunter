import { z } from "zod";

export const timestampSchema = z.iso.datetime({ offset: true });

export const sourceKindSchema = z.enum(["manual_jd", "manual_url"]);
export const freshnessSchema = z.enum(["fresh", "stale"]);
export const jobLifecycleStatusSchema = z.enum([
  "imported",
  "screened",
  "shortlisted",
  "skipped",
]);

export const importedSourceSchema = z
  .object({
    kind: sourceKindSchema,
    locator: z.string().nullable(),
    captured_at: timestampSchema,
    last_verified_at: timestampSchema,
    freshness: freshnessSchema,
  })
  .strict();

export const importJobResponseSchema = z
  .object({
    job_id: z.string().min(1),
    job_version_id: z.string().min(1),
    active_version_id: z.string().min(1),
    source_snapshot_id: z.string().min(1),
    version_number: z.number().int().positive(),
    lifecycle_status: z.literal("imported"),
    source: importedSourceSchema,
    correlation_id: z.string().min(1),
    run_id: z.string().min(1),
  })
  .strict();

export type ImportedJob = z.infer<typeof importJobResponseSchema>;
export type ImportedSource = z.infer<typeof importedSourceSchema>;
export type JobLifecycleStatus = z.infer<typeof jobLifecycleStatusSchema>;

export interface ActiveJob {
  job_id: string;
  job_version_id: string;
  active_version_id: string;
  source_snapshot_id: string;
  version_number: number;
  lifecycle_status: JobLifecycleStatus;
  source: ImportedSource;
}

export type ManualJobInput =
  | {
      sourceType: "manual_jd";
      title: string;
      company: string;
      city: string;
      content: string;
    }
  | {
      sourceType: "manual_url";
      url: string;
      title: string;
      company: string;
      city: string;
      content: string;
    };
