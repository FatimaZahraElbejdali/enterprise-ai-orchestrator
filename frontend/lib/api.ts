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
export const TOKEN_EXPIRED_MESSAGE = "Session expirée. Veuillez vous reconnecter.";
export const API_ERROR_MESSAGE =
  "Une erreur est survenue lors du traitement de la demande.";
export const BACKEND_UNREACHABLE_MESSAGE =
  "Impossible de joindre le serveur de l’orchestrateur.";

const ROLE_LABELS: Record<string, string> = {
  admin: "Administrateur",
  odoo_manager: "Responsable Odoo",
  it_manager: "Responsable IT",
  support_agent: "Agent Support",
  employee: "Employé",
  readonly_viewer: "Lecture seule",
};

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

export function getRoleLabel(user: AuthUser | null) {
  if (!user) return "Lecture seule";

  return ROLE_LABELS[user.role] || user.role_label || "Lecture seule";
}

export function authHeaders(): HeadersInit {
  const token = getStoredToken();

  return token
    ? {
        Authorization: `Bearer ${token}`,
      }
    : {};
}

export async function postChatMessage<T = unknown>(
  message: string,
  sessionId = "demo-session"
): Promise<T> {
  const response = await fetch(`${API_BASE_URL}/chat`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(),
    },
    body: JSON.stringify({
      message,
      session_id: sessionId,
    }),
  });

  if (!response.ok) {
    const authMessage = handleAuthFailure(response.status);
    throw new Error(authMessage || API_ERROR_MESSAGE);
  }

  return response.json() as Promise<T>;
}

export class ApiRequestError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiRequestError";
    this.status = status;
  }
}

async function submitApprovalDecision<T = unknown>(
  approvalId: string,
  decision: "approve" | "reject"
): Promise<T> {
  const response = await fetch(`${API_BASE_URL}/approvals/${approvalId}/${decision}`, {
    method: "POST",
    headers: authHeaders(),
  });

  if (!response.ok) {
    if (response.status === 401) {
      clearAuth();
      throw new ApiRequestError(TOKEN_EXPIRED_MESSAGE, response.status);
    }

    if (response.status === 403) {
      throw new ApiRequestError(ACCESS_DENIED_MESSAGE, response.status);
    }

    throw new ApiRequestError(API_ERROR_MESSAGE, response.status);
  }

  return response.json() as Promise<T>;
}

export function approveApproval<T = unknown>(approvalId: string) {
  return submitApprovalDecision<T>(approvalId, "approve");
}

export function rejectApproval<T = unknown>(approvalId: string) {
  return submitApprovalDecision<T>(approvalId, "reject");
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
    window.localStorage.setItem("auth_error", TOKEN_EXPIRED_MESSAGE);
    window.location.href = "/login";
    return TOKEN_EXPIRED_MESSAGE;
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
