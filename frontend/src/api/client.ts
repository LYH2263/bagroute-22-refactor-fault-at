export type FaultAt = "route" | "stop" | "pack";

export type FaultBody = { fault: string; detail: string; at: FaultAt };

export class FaultError extends Error {
  fault: string;
  detail: string;
  at: FaultAt;
  constructor(body: FaultBody) {
    super(body.detail);
    this.name = "FaultError";
    this.fault = body.fault;
    this.detail = body.detail;
    this.at = body.at;
  }
}

function asFaultBody(data: unknown): FaultBody | null {
  if (data && typeof data === "object") {
    const d = data as Record<string, unknown>;
    if (
      typeof d.fault === "string" &&
      typeof d.detail === "string" &&
      (d.at === "route" || d.at === "stop" || d.at === "pack")
    ) {
      return { fault: d.fault, detail: d.detail, at: d.at };
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
    const text = await res.text();
    let data: unknown = null;
    try {
      data = JSON.parse(text);
    } catch {
      // 非 JSON 错误体，按原样抛出
    }
    const fault = asFaultBody(data);
    if (fault) throw new FaultError(fault);
    throw new Error(text || res.statusText);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}
