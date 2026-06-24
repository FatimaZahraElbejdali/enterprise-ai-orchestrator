export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export type AuthUser = {
  email: string;
  role: string;
  role_label: string;
  permissions: string[];
};

export const ACCESS_DENIED_MESSAGE =
  "Accès refusé : votre rôle ne permet pas d’effectuer cette action.";

export function getStoredToken() {
  if (typeof window === "undefined") return "";

  return window.localStorage.getItem("auth_token") || "";
}

export function getStoredUser(): AuthUser | null {
  if (typeof window === "undefined") return null;

  const rawUser = window.localStorage.getItem("auth_user");

  if (!rawUser) return null;

  try {
    return JSON.parse(rawUser) as AuthUser;
  } catch {
    return null;
  }
}

export function storeAuth(accessToken: string, user: AuthUser) {
  window.localStorage.setItem("auth_token", accessToken);
  window.localStorage.setItem("auth_user", JSON.stringify(user));
}

export function clearAuth() {
  window.localStorage.removeItem("auth_token");
  window.localStorage.removeItem("auth_user");
}

export function authHeaders(): HeadersInit {
  const token = getStoredToken();

  return token
    ? {
        Authorization: `Bearer ${token}`,
      }
    : {};
}

export function requireAuth() {
  const token = getStoredToken();

  if (!token) {
    window.location.href = "/login";
    return false;
  }

  return true;
}

export function handleAuthFailure(status: number) {
  if (status === 401) {
    clearAuth();
    window.location.href = "/login";
    return "Session expirée";
  }

  if (status === 403) {
    return ACCESS_DENIED_MESSAGE;
  }

  return "";
}

export function hasAnyPermission(user: AuthUser | null, permissions: string[]) {
  if (!user) return false;

  if (user.permissions.includes("all")) return true;

  return permissions.some((permission) => user.permissions.includes(permission));
}
