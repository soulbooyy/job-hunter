import { z } from "zod";

export const backendErrorCodeSchema = z.enum([
  "input_validation",
  "not_found",
  "conflict",
  "dependency_unavailable",
]);

export const errorResponseSchema = z
  .object({
    error: z
      .object({
        code: backendErrorCodeSchema,
        message: z.string().min(1),
      })
      .strict(),
  })
  .strict();

export type ApiErrorCode =
  | z.infer<typeof backendErrorCodeSchema>
  | "backend_unavailable"
  | "invalid_response";

export class ApiError extends Error {
  readonly code: ApiErrorCode;
  readonly status: number | null;

  constructor(code: ApiErrorCode, message: string, status: number | null) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
  }
}

export function getErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    switch (error.code) {
      case "input_validation":
        return "输入内容未通过校验。";
      case "not_found":
        return "未找到所需数据。";
      case "conflict":
        return "当前状态已发生变化，请刷新相关结果后重试。";
      case "dependency_unavailable":
        return "后端依赖暂不可用。";
      case "backend_unavailable":
      case "invalid_response":
        return error.message;
    }
  }
  return "请求未能完成。";
}
