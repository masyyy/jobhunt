const STORAGE_KEY = 'jobhunt-app-password'

export function getAppPassword(): string | null {
  try {
    return localStorage.getItem(STORAGE_KEY)
  } catch {
    return null
  }
}

export function setAppPassword(password: string): void {
  try {
    localStorage.setItem(STORAGE_KEY, password)
  } catch {
    // ignore: storage may be unavailable (private mode)
  }
}

export function clearAppPassword(): void {
  try {
    localStorage.removeItem(STORAGE_KEY)
  } catch {
    // ignore
  }
}

/** fetch wrapper that injects the app password header on every request. */
export async function apiFetch(input: RequestInfo | URL, init: RequestInit = {}): Promise<Response> {
  const password = getAppPassword()
  const headers = new Headers(init.headers)
  if (password) headers.set('X-App-Password', password)
  return fetch(input, { ...init, headers })
}

/** Validate a candidate password against the backend. */
export async function checkAppPassword(password: string): Promise<boolean> {
  const response = await fetch('/api/auth/check', {
    headers: { 'X-App-Password': password },
  })
  return response.ok
}
