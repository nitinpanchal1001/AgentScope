import { useAuthStore, type User } from "./auth-store";

export const API_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type ApiErrorPayload = {
  error?: { message?: string; code?: string; request_id?: string };
};
export type AuthResponse = {
  access_token: string;
  expires_at: string;
  user: User;
};

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public code?: string,
  ) {
    super(message);
  }
}

export async function apiFetch<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const token = useAuthStore.getState().accessToken;
  const headers = new Headers(init.headers);
  if (init.body) headers.set("Content-Type", "application/json");
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    headers,
    credentials: "include",
  });
  if (!response.ok) {
    const payload = (await response
      .json()
      .catch(() => ({}))) as ApiErrorPayload;
    throw new ApiError(
      payload.error?.message ?? "Request failed",
      response.status,
      payload.error?.code,
    );
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export async function refreshSession(): Promise<AuthResponse> {
  const session = await apiFetch<AuthResponse>("/api/v1/auth/refresh", {
    method: "POST",
  });
  useAuthStore.getState().setSession(session.access_token, session.user);
  return session;
}
