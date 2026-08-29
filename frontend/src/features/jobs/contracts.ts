import { z } from "zod";

const timestampSchema = z.iso.datetime({ offset: true });

export const importJobResponseSchema = z
  .object({
    job_id: z.string().min(1),
    job_version_id: z.string().min(1),
    active_version_id: z.string().min(1),
    source_snapshot_id: z.string().min(1),
    version_number: z.number().int().positive(),
    lifecycle_status: z.literal("imported"),
    source: z
      .object({
        kind: z.enum(["manual_jd", "manual_url"]),
        locator: z.string().nullable(),
        captured_at: timestampSchema,
        last_verified_at: timestampSchema,
        freshness: z.enum(["fresh", "stale"]),
      })
      .strict(),
    correlation_id: z.string().min(1),
    run_id: z.string().min(1),
  })
  .strict();

export type ImportedJob = z.infer<typeof importJobResponseSchema>;

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
