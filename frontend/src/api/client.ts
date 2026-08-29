import type { z } from "zod";

import { ApiError, errorResponseSchema } from "./errors";

export { ApiError } from "./errors";

const rawBaseUrl: unknown = import.meta.env.VITE_API_BASE_URL;
const configuredBaseUrl =
  typeof rawBaseUrl === "string" ? rawBaseUrl.replace(/\/$/u, "") : "";

function apiUrl(path: string): string {
  return `${configuredBaseUrl}${path}`;
}

export async function requestJson<T>(
  path: string,
  init: RequestInit,
  responseSchema: z.ZodType<T>,
  expectedStatus = 201,
): Promise<T> {
  let response: Response;
  try {
    const headers = new Headers(init.headers);
    if (!headers.has("Content-Type")) {
      headers.set("Content-Type", "application/json");
    }
    response = await fetch(apiUrl(path), {
      ...init,
      headers,
    });
  } catch {
    // Transport exceptions can contain machine or payload details, so they end here.
    throw new ApiError(
      "backend_unavailable",
      "后端不可用，请确认本地 API 已启动。",
      null,
    );
  }

  let payload: unknown;
  try {
    payload = await response.json();
  } catch {
    throw new ApiError(
      "invalid_response",
      "后端返回了无效响应。",
      response.status,
    );
  }

  if (!response.ok) {
    const parsedError = errorResponseSchema.safeParse(payload);
    if (!parsedError.success) {
      throw new ApiError(
        "invalid_response",
        "后端返回了无效错误响应。",
        response.status,
      );
    }
    throw new ApiError(
      parsedError.data.error.code,
      parsedError.data.error.message,
      response.status,
    );
  }

  if (response.status !== expectedStatus) {
    throw new ApiError(
      "invalid_response",
      "后端返回了非预期的成功状态码。",
      response.status,
    );
  }

  // JSON remains unknown until the endpoint-specific runtime contract accepts it.
  const parsedResponse = responseSchema.safeParse(payload);
  if (!parsedResponse.success) {
    throw new ApiError(
      "invalid_response",
      "后端返回了无效响应。",
      response.status,
    );
  }
  return parsedResponse.data;
}
