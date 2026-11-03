export class ApiError extends Error {
  status: number;
  data: any;

  constructor(status: number, message: string, data?: any) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.data = data;
  }
}

export class ConflictError extends ApiError {
  constructor(message: string, data?: any) {
    super(409, message, data);
    this.name = "ConflictError";
  }
}

export async function apiRequest<T = any>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const headers = new Headers(options.headers || {});

  // Ensure JSON content-type if not multipart
  if (
    options.body &&
    !(options.body instanceof FormData) &&
    !headers.has("Content-Type")
  ) {
    headers.set("Content-Type", "application/json");
  }

  // CSRF Guard: Require X-Requested-With header on state-changing requests
  const method = (options.method || "GET").toUpperCase();
  if (["POST", "PUT", "PATCH", "DELETE"].includes(method)) {
    headers.set("X-Requested-With", "XMLHttpRequest");
  }

  const res = await fetch(endpoint, {
    ...options,
    headers,
    credentials: "include", // Sends HttpOnly JWT cookies
  });

  if (res.status === 401) {
    const errorJson = await res.json().catch(() => ({}));
    const message = errorJson.detail || (endpoint.includes("/login") ? "Invalid email or password" : "Session expired or unauthenticated");
    // Avoid infinite redirect loops on login endpoint
    if (!window.location.pathname.startsWith("/login")) {
      window.location.href = "/login";
    }
    throw new ApiError(401, message);
  }

  if (res.status === 409) {
    const errorJson = await res.json().catch(() => ({}));
    throw new ConflictError(
      errorJson.detail || "This record was modified by another process. Please reload.",
      errorJson
    );
  }

  if (!res.ok) {
    const errorJson = await res.json().catch(() => ({}));
    const message = errorJson.detail || errorJson.title || res.statusText || "Request failed";
    throw new ApiError(res.status, message, errorJson);
  }

  // Handle 204 No Content
  if (res.status === 204) {
    return {} as T;
  }

  return res.json() as Promise<T>;
}
