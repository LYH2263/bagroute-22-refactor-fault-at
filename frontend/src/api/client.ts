export type FaultBody = { fault: string; detail: string; at: "route" | "stop" | "pack" };

export class ApiError extends Error {
  status: number;
  body: unknown;
  constructor(status: number, body: unknown) {
    super(`请求失败（HTTP ${status}）`);
    this.status = status;
    this.body = body;
  }
}

export function asFault(body: unknown): FaultBody | null {
  if (body && typeof body === "object") {
    const b = body as Record<string, unknown>;
    if (
      typeof b.fault === "string" &&
      typeof b.detail === "string" &&
      (b.at === "route" || b.at === "stop" || b.at === "pack")
    ) {
      return { fault: b.fault, detail: b.detail, at: b.at };
    }
  }
  return null;
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, {
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
    ...init,
  });
  if (!res.ok) {
    let body: unknown = null;
    try {
      body = await res.json();
    } catch {
      // 非 JSON 错误体，body 保持 null
    }
    throw new ApiError(res.status, body);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}
