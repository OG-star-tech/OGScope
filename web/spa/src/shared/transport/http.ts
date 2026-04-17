export async function requestJson<T>(
  url: string,
  options: RequestInit & { cache?: RequestCache } = {},
): Promise<T> {
  const { cache, ...rest } = options;
  const fetchOpts: RequestInit = {
    headers: { "Content-Type": "application/json" },
    ...rest,
  };
  if (cache !== undefined) Object.assign(fetchOpts, { cache });
  const response = await fetch(url, fetchOpts);
  let data: unknown = {};
  try {
    data = await response.json();
  } catch {
    // ignore parse failure
  }
  if (!response.ok) {
    const d = data as { detail?: string };
    throw new Error(d.detail || `HTTP ${response.status}`);
  }
  return data as T;
}


export async function requestDevDebugJson<T>(
  url: string,
  options: RequestInit & { cache?: RequestCache } = {},
): Promise<T> {
  const normalizedUrl = url.startsWith("/api/debug/")
    ? url.replace("/api/debug/", "/api/dev/debug/")
    : url;
  return requestJson<T>(normalizedUrl, options);
}

