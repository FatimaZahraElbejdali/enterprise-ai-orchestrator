export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export type AuthUser = {
  email: string;
  role: string;
  role_label: string;
  department?: string;
  department_label?: string;
  permissions: string[];
};

export const ACCESS_DENIED_MESSAGE =
  "Accès refusé : votre rôle ne permet pas d’effectuer cette action.";
export const TOKEN_EXPIRED_MESSAGE = "Votre session a expiré. Veuillez vous reconnecter.";
export const API_ERROR_MESSAGE =
  "Une erreur est survenue lors du traitement de la demande.";
export const BACKEND_UNREACHABLE_MESSAGE =
  "Impossible de joindre le serveur de l’orchestrateur.";

const AUTH_RETURN_TO_KEY = "auth_return_to";
const AUTH_ERROR_KEY = "auth_error";
const CHAT_DRAFT_KEY = "chat_unsent_draft";

const ROLE_LABELS: Record<string, string> = {
  admin: "Administrateur",
  odoo_manager: "Responsable Odoo",
  it_manager: "Responsable IT",
  support_agent: "Agent Support",
  employee: "Employé",
  readonly_viewer: "Lecture seule",
};

const DEPARTMENT_LABELS: Record<string, string> = {
  administration: "Administration",
  commerciale: "Commerciale",
  comptabilite_finance: "Comptabilité & Finance",
  informatique: "Informatique",
  nettoyage: "Nettoyage",
  rh: "Ressources humaines",
  securite: "Sécurité",
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

export function getDepartmentLabel(user: AuthUser | null) {
  if (!user) return "Administration";

  return (
    DEPARTMENT_LABELS[user.department || ""] ||
    user.department_label ||
    "Administration"
  );
}

export function authHeaders(): HeadersInit {
  const token = getStoredToken();

  return token
    ? {
        Authorization: `Bearer ${token}`,
      }
    : {};
}

type ApiFetchOptions = {
  draftToPreserve?: string;
  returnTo?: string;
};

function currentPath() {
  if (typeof window === "undefined") return "/";

  return `${window.location.pathname}${window.location.search || ""}`;
}

function loginUrl(returnTo: string) {
  return `/login?next=${encodeURIComponent(returnTo || "/chat")}`;
}

export function saveChatDraft(draft: string) {
  if (typeof window === "undefined") return;

  const trimmedDraft = draft.trim();

  if (trimmedDraft) {
    window.localStorage.setItem(CHAT_DRAFT_KEY, draft);
  }
}

export function consumeSavedChatDraft() {
  if (typeof window === "undefined") return "";

  const draft = window.localStorage.getItem(CHAT_DRAFT_KEY) || "";
  window.localStorage.removeItem(CHAT_DRAFT_KEY);
  return draft;
}

export function handleSessionExpired(options: ApiFetchOptions = {}) {
  if (typeof window === "undefined") return TOKEN_EXPIRED_MESSAGE;

  const returnTo = options.returnTo || currentPath();

  if (options.draftToPreserve) {
    saveChatDraft(options.draftToPreserve);
  }

  window.localStorage.setItem(AUTH_ERROR_KEY, TOKEN_EXPIRED_MESSAGE);
  window.localStorage.setItem(AUTH_RETURN_TO_KEY, returnTo);
  clearAuth();
  window.location.href = loginUrl(returnTo);
  return TOKEN_EXPIRED_MESSAGE;
}

export async function apiFetch(
  input: RequestInfo | URL,
  init: RequestInit = {},
  options: ApiFetchOptions = {}
) {
  const headers = new Headers(authHeaders());
  new Headers(init.headers || {}).forEach((value, key) => {
    headers.set(key, value);
  });

  const response = await fetch(input, {
    ...init,
    headers,
  });

  if (response.status === 401) {
    handleSessionExpired(options);
    throw new ApiRequestError(TOKEN_EXPIRED_MESSAGE, response.status);
  }

  return response;
}

export async function validateAuthSession(returnTo?: string) {
  if (!getStoredToken()) {
    handleSessionExpired({ returnTo });
    return false;
  }

  let response: Response;

  try {
    response = await apiFetch(
      `${API_BASE_URL}/auth/me`,
      { cache: "no-store" },
      { returnTo }
    );
  } catch {
    return false;
  }

  if (!response.ok) return false;

  const user = (await response.json()) as AuthUser;
  window.localStorage.setItem("auth_user", JSON.stringify(user));
  return true;
}

export async function postChatMessage<T = unknown>(
  message: string,
  sessionId = "demo-session"
): Promise<T> {
  const response = await apiFetch(
    `${API_BASE_URL}/chat`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        message,
        session_id: sessionId,
      }),
    },
    {
      draftToPreserve: message,
      returnTo: "/chat",
    }
  );

  if (!response.ok) {
    if (response.status === 403) {
      throw new ApiRequestError(ACCESS_DENIED_MESSAGE, response.status);
    }

    throw new ApiRequestError(API_ERROR_MESSAGE, response.status);
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
  const response = await apiFetch(`${API_BASE_URL}/approvals/${approvalId}/${decision}`, {
    method: "POST",
  });

  if (!response.ok) {
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
    const returnTo = currentPath();
    window.localStorage.setItem(AUTH_RETURN_TO_KEY, returnTo);
    window.location.href = loginUrl(returnTo);
    return false;
  }

  return true;
}

export function handleAuthFailure(status: number) {
  if (status === 401) {
    handleSessionExpired();
    return TOKEN_EXPIRED_MESSAGE;
  }

  if (status === 403) {
    return ACCESS_DENIED_MESSAGE;
  }

  return "";
}

export function getPostLoginRedirect() {
  if (typeof window === "undefined") return "/chat";

  const nextParam = new URLSearchParams(window.location.search).get("next");
  const storedReturnTo = window.localStorage.getItem(AUTH_RETURN_TO_KEY);
  const destination = nextParam || storedReturnTo || "/chat";
  window.localStorage.removeItem(AUTH_RETURN_TO_KEY);
  return destination.startsWith("/") && !destination.startsWith("//")
    ? destination
    : "/chat";
}

export function hasAnyPermission(user: AuthUser | null, permissions: string[]) {
  if (!user) return false;

  if (user.permissions.includes("all")) return true;

  return permissions.some((permission) => user.permissions.includes(permission));
}
