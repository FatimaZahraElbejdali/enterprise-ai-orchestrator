"use client";

import { useEffect, useMemo, useState } from "react";
import AppShell from "@/components/AppShell";
import {
  ACCESS_DENIED_MESSAGE,
  API_ERROR_MESSAGE,
  API_BASE_URL,
  AuthUser,
  apiFetch,
  clearAuth,
  getDepartmentLabel,
  getRoleLabel,
  getStoredUser,
  hasAnyPermission,
  requireAuth,
  validateAuthSession,
} from "@/lib/api";

type ExecutionResult = {
  success?: boolean;
  old_price?: string | number | null;
  new_price?: string | number | null;
  executed?: boolean;
  message?: string;
};

type LogEntry = {
  id?: string;
  timestamp?: string;
  event_type?: string;
  title?: string;
  system?: string;
  agent?: string;
  selected_agent?: string;
  status?: string;
  risk?: string;
  approval_status?: string;
  permission_decision?: string;
  user_email?: string;
  user_role?: string;
  approval_id?: string;
  user_message?: string;
  action?: string;
  product?: string;
  requested_value?: string | number;
  executed?: boolean;
  message?: string;
  data?: unknown;
  execution_result?: ExecutionResult;
};

type LogView = "important" | "all";

export default function LogsPage() {
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [logView, setLogView] = useState<LogView>("important");
  const [loading, setLoading] = useState(true);
  const [currentUser] = useState<AuthUser | null>(() => getStoredUser());
  const [error, setError] = useState("");
  const accessDenied = !hasAnyPermission(currentUser, ["all", "view_audit_logs"]);

  function handleLogout() {
    clearAuth();
    window.location.href = "/login";
  }

  async function loadLogs(view: LogView = logView) {
    setLoading(true);
    setError("");

    try {
      const res = await apiFetch(`${API_BASE_URL}/logs?view=${view}`, {
        cache: "no-store",
      });

      if (res.ok) {
        const data = await res.json();

        const cleanLogs = Array.isArray(data)
          ? data.filter((log) => {
              if (!log || typeof log !== "object") return false;
              if (log.title === "string") return false;
              if (log.message === "string") return false;
              if (log.user_message === "string") return false;
              return true;
            })
          : [];

        setLogs(cleanLogs);
      } else {
        setError(API_ERROR_MESSAGE);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : API_ERROR_MESSAGE);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (!requireAuth()) return;
    void validateAuthSession("/logs");

    const user = getStoredUser();

    if (!hasAnyPermission(user, ["all", "view_audit_logs"])) {
      return;
    }

    const timer = window.setTimeout(() => {
      void loadLogs("important");
    }, 0);

    return () => window.clearTimeout(timer);
  }, []);

  const odooReads = useMemo(
    () => logs.filter((log) => log.event_type === "odoo_read").length,
    [logs]
  );

  const approvalEvents = useMemo(
    () =>
      logs.filter(
        (log) =>
          log.event_type === "approval_required" ||
          log.event_type === "approval_decision"
      ).length,
    [logs]
  );

  const blockedActions = useMemo(
    () =>
      logs.filter(
        (log) =>
          log.status === "pending_approval" ||
          log.status === "access_denied" ||
          log.status === "blocked" ||
          log.approval_status === "pending" ||
          log.permission_decision === "denied"
      ).length,
    [logs]
  );

  return (
    <AppShell
      active="logs"
      eyebrow="Audit"
      title="Traçabilité des actions"
      subtitle="Suivi des consultations Odoo, demandes sensibles, décisions d’approbation et actions bloquées par la politique de sécurité."
      actions={<button onClick={() => void loadLogs(logView)}>Actualiser</button>}
    >
        <section className="metrics">
          <Metric label="Événements" value={logs.length} />
          <Metric label="Lectures Odoo" value={odooReads} />
          <Metric label="Validations" value={approvalEvents} />
          <Metric label="Actions bloquées" value={blockedActions} />
        </section>

        {(error || accessDenied) && (
          <div className="errorBox">
            {accessDenied ? ACCESS_DENIED_MESSAGE : error}
          </div>
        )}

        <section className="panel">
          <div className="panelHeader">
            <div>
              <p className="eyebrow">Historique</p>
              <h3>Événements récents</h3>
            </div>
            <div className="auditToggle" aria-label="Filtre du journal d’audit">
              <button
                className={logView === "important" ? "active" : ""}
                onClick={() => {
                  setLogView("important");
                  void loadLogs("important");
                }}
                type="button"
              >
                Événements importants
              </button>
              <button
                className={logView === "all" ? "active" : ""}
                onClick={() => {
                  setLogView("all");
                  void loadLogs("all");
                }}
                type="button"
              >
                Afficher tout
              </button>
            </div>
          </div>

          {loading && !accessDenied && <p className="empty">Chargement des logs...</p>}

          {!loading && !accessDenied && logs.length === 0 && (
            <p className="empty">
              {logView === "important"
                ? "Aucun événement important à afficher."
                : "Aucun événement d’audit propre à afficher."}
            </p>
          )}

          {!loading &&
            !accessDenied &&
            logs.map((log, index) => (
              <details className="auditRow" key={log.id || index}>
                <summary className="auditSummary">
                  <span className="auditDate">{formatDate(log.timestamp)}</span>
                  <span className="auditTitle">
                    <strong>{compactLogTitle(log)}</strong>
                    <small>{summarizeLogMessage(log)}</small>
                  </span>
                  <span>{formatAgentName(log.selected_agent || log.agent)}</span>
                  <span>{translateAction(log.action || log.event_type)}</span>
                  <span className={`status ${normalizeStatus(log.status)}`}>
                    {translateStatus(log.status)}
                  </span>
                  <span className={`risk ${log.risk || "low"}`}>
                    {translateRisk(log.risk)}
                  </span>
                  <span>{formatValue(log.user_email)}</span>
                  <span className="detailsButton">Détails</span>
                </summary>

                <div className="auditDetails">
                  <div className="detailsGrid">
                    <Detail label="Date" value={formatDate(log.timestamp)} />
                    <Detail label="Utilisateur" value={formatValue(log.user_email)} />
                    <Detail label="Rôle" value={translateRole(log.user_role)} />
                    <Detail label="Agent" value={formatAgentName(log.selected_agent || log.agent)} />
                    <Detail label="Action" value={translateAction(log.action || log.event_type)} />
                    <Detail
                      label="Décision d’accès"
                      value={translatePermissionDecision(log.permission_decision)}
                    />
                    <Detail
                      label="Validation"
                      value={translateApproval(log.approval_status)}
                    />
                    <Detail
                      label="Statut"
                      value={translateStatus(log.status)}
                    />
                    <Detail
                      label="Produit/document"
                      value={formatValue(log.product)}
                    />
                    <Detail
                      label="Valeur demandée"
                      value={formatValue(log.requested_value)}
                    />
                  </div>

                  {log.user_message && (
                    <div className="requestBox">
                      <span>Demande utilisateur</span>
                      <p>{cleanDisplayText(log.user_message)}</p>
                    </div>
                  )}

                  {log.execution_result && (
                    <div className="requestBox">
                      <span>Résultat Odoo</span>
                      <p>{formatExecutionResult(log.execution_result)}</p>
                    </div>
                  )}
                </div>
              </details>
            ))}
        </section>
      <style jsx global>{`
        * {
          box-sizing: border-box;
        }

        body {
          margin: 0;
          background: #f4f6f8;
          color: #172033;
          font-family: Inter, ui-sans-serif, system-ui, -apple-system,
            BlinkMacSystemFont, "Segoe UI", sans-serif;
        }

        .pageShell {
          min-height: 100vh;
          display: grid;
          grid-template-columns: 280px 1fr;
        }

        .sidebar {
          min-height: 100vh;
          background: #101827;
          color: #ffffff;
          padding: 28px 22px;
          display: flex;
          flex-direction: column;
          justify-content: space-between;
          position: sticky;
          top: 0;
        }

        .brand {
          display: flex;
          align-items: center;
          gap: 14px;
          margin-bottom: 34px;
        }

        .brandMark {
          width: 56px;
          height: 56px;
          background: #ffffff;
          display: grid;
          place-items: center;
          flex: 0 0 56px;
        }

        .brandLogo {
          width: 48px;
          height: 48px;
          object-fit: contain;
          display: block;
        }

        .brand p {
          margin: 0 0 4px;
          color: #94a3b8;
          font-size: 12px;
          text-transform: uppercase;
          letter-spacing: 0.09em;
          font-weight: 800;
        }

        .brand h1 {
          margin: 0;
          font-size: 18px;
        }

        .nav {
          display: grid;
          gap: 6px;
        }

        .nav a {
          text-decoration: none;
          color: #cbd5e1;
          padding: 12px 13px;
          border-radius: 8px;
          font-size: 14px;
          font-weight: 700;
        }

        .nav a:hover,
        .nav a.active {
          background: #1e293b;
          color: #ffffff;
        }

        .sidebarFooter {
          border-top: 1px solid rgba(255, 255, 255, 0.12);
          padding-top: 18px;
        }

        .sidebarFooter p {
          margin: 0 0 6px;
          font-size: 13px;
          font-weight: 800;
        }

        .sidebarFooter span {
          color: #94a3b8;
          font-size: 12px;
          line-height: 1.5;
        }

        .logoutButton {
          margin-top: 14px;
          width: 100%;
          min-height: 40px;
          border: 1px solid rgba(255, 255, 255, 0.18);
          border-radius: 8px;
          background: #ffffff;
          color: #123f8c;
          font-weight: 900;
          cursor: pointer;
        }

        .logoutButton:hover {
          background: #eef4ff;
        }

        .content {
          padding: 32px;
        }

        .header {
          background: #ffffff;
          border: 1px solid #d9dee7;
          padding: 28px;
          display: flex;
          justify-content: space-between;
          gap: 24px;
          margin-bottom: 18px;
        }

        .eyebrow {
          margin: 0;
          color: #647084;
          text-transform: uppercase;
          letter-spacing: 0.09em;
          font-size: 11px;
          font-weight: 900;
        }

        .header h2 {
          margin: 8px 0;
          font-size: 30px;
          color: #101827;
          letter-spacing: -0.04em;
        }

        .subtitle {
          margin: 0;
          max-width: 820px;
          color: #5b6472;
          font-size: 15px;
          line-height: 1.6;
        }

        button {
          height: 40px;
          border: 1px solid #172033;
          background: #172033;
          color: #ffffff;
          border-radius: 8px;
          padding: 0 16px;
          font-size: 14px;
          font-weight: 800;
          cursor: pointer;
        }

        .metrics {
          display: grid;
          grid-template-columns: repeat(4, minmax(0, 1fr));
          gap: 14px;
          margin-bottom: 18px;
        }

        .metric {
          background: #ffffff;
          border: 1px solid #d9dee7;
          padding: 20px;
        }

        .metric p {
          margin: 0 0 10px;
          color: #647084;
          font-size: 12px;
          font-weight: 900;
          text-transform: uppercase;
          letter-spacing: 0.08em;
        }

        .metric h3 {
          margin: 0;
          font-size: 28px;
          color: #101827;
        }

        .panel {
          background: #ffffff;
          border: 1px solid #d9dee7;
          padding: 24px;
        }

        .panelHeader {
          margin-bottom: 18px;
          display: flex;
          align-items: flex-start;
          justify-content: space-between;
          gap: 16px;
        }

        .panelHeader h3 {
          margin: 6px 0 0;
          font-size: 22px;
          color: #101827;
        }

        .auditToggle {
          display: inline-flex;
          gap: 4px;
          border: 1px solid #d9dee7;
          border-radius: 10px;
          background: #f8fafc;
          padding: 4px;
        }

        .auditToggle button {
          height: 32px;
          border: 0;
          border-radius: 7px;
          background: transparent;
          color: #647084;
          padding: 0 11px;
          font-size: 12px;
          font-weight: 850;
        }

        .auditToggle button.active {
          background: #ffffff;
          color: #123f8c;
          box-shadow: 0 1px 2px rgba(15, 27, 45, 0.08);
        }

        .empty {
          color: #647084;
          font-weight: 700;
        }

        .auditRow {
          border: 1px solid #d9dee7;
          background: #ffffff;
          margin-bottom: 8px;
        }

        .auditRow[open] {
          background: #fbfcfe;
        }

        .auditSummary {
          min-height: 58px;
          display: grid;
          grid-template-columns:
            150px minmax(260px, 1.5fr) minmax(120px, 0.75fr)
            minmax(130px, 0.85fr) 104px 84px minmax(160px, 1fr) 82px;
          gap: 12px;
          align-items: center;
          padding: 10px 14px;
          cursor: pointer;
          list-style: none;
        }

        .auditSummary::-webkit-details-marker {
          display: none;
        }

        .auditSummary > span {
          min-width: 0;
          color: #475467;
          font-size: 12px;
          font-weight: 750;
        }

        .auditDate {
          color: #667085;
          font-variant-numeric: tabular-nums;
        }

        .auditTitle {
          display: grid;
          gap: 2px;
        }

        .auditTitle strong {
          overflow: hidden;
          color: #172033;
          font-size: 13px;
          font-weight: 900;
          text-overflow: ellipsis;
          white-space: nowrap;
        }

        .auditTitle small {
          overflow: hidden;
          color: #667085;
          font-size: 11px;
          font-weight: 700;
          text-overflow: ellipsis;
          white-space: nowrap;
        }

        .detailsButton {
          justify-self: end;
          display: inline-flex;
          align-items: center;
          justify-content: center;
          min-height: 30px;
          border: 1px solid #d9dee7;
          border-radius: 7px;
          background: #f8fafc;
          color: #123f8c !important;
          padding: 0 10px;
          font-size: 12px;
          font-weight: 850;
        }

        .auditRow[open] .detailsButton {
          background: #123f8c;
          border-color: #123f8c;
          color: #ffffff !important;
        }

        .auditDetails {
          border-top: 1px solid #e5e7eb;
          padding: 14px;
        }

        .status,
        .risk {
          border-radius: 999px;
          padding: 5px 8px;
          font-size: 11px;
          font-weight: 900;
          white-space: nowrap;
          border: 1px solid #d9dee7;
          background: #f8fafc;
          color: #475569;
        }

        .status.completed,
        .risk.low {
          background: #eef8f3;
          color: #13754a;
          border-color: #b8e0cb;
        }

        .status.pending_approval,
        .status.pending,
        .risk.medium {
          background: #fff7df;
          color: #8a5a00;
          border-color: #f2d38b;
        }

        .status.rejected,
        .status.failed,
        .risk.high {
          background: #fff1f1;
          color: #9f1d1d;
          border-color: #f2c0c0;
        }

        .detailsGrid {
          display: grid;
          grid-template-columns: repeat(2, minmax(0, 1fr));
          gap: 0 24px;
          border-bottom: 1px solid #e5e7eb;
          margin-bottom: 16px;
        }

        .detail {
          display: grid;
          grid-template-columns: 150px 1fr;
          gap: 14px;
          padding: 12px 0;
          border-bottom: 1px solid #eef2f7;
        }

        .detail span:first-child {
          color: #647084;
          font-size: 13px;
          font-weight: 800;
        }

        .detail span:last-child {
          color: #172033;
          font-size: 13px;
          font-weight: 800;
          word-break: break-word;
        }

        .requestBox {
          background: #ffffff;
          border: 1px solid #e5e7eb;
          padding: 14px;
        }

        .requestBox span {
          display: block;
          color: #647084;
          font-size: 12px;
          font-weight: 900;
          text-transform: uppercase;
          letter-spacing: 0.08em;
          margin-bottom: 6px;
        }

        .requestBox p {
          margin: 0;
          color: #172033;
          font-weight: 700;
        }

        @media (max-width: 1100px) {
          .pageShell {
            grid-template-columns: 1fr;
          }

          .sidebar {
            min-height: auto;
            position: relative;
          }

          .metrics,
          .detailsGrid,
          .auditSummary {
            grid-template-columns: 1fr;
          }

          .detailsButton {
            justify-self: start;
          }
        }
      `}</style>
    </AppShell>
  );
}

function Metric({ label, value }: { label: string; value: number }) {
  return (
    <div className="metric">
      <p>{label}</p>
      <h3>{value}</h3>
    </div>
  );
}

function Detail({ label, value }: { label: string; value: string }) {
  return (
    <div className="detail">
      <span>{label}</span>
      <span>{value}</span>
    </div>
  );
}

function translateEvent(event?: string) {
  const labels: Record<string, string> = {
    answer_question: "Question répondue",
    odoo_read: "Consultation Odoo",
    approval_required: "Validation requise",
    approval_decision: "Décision de validation",
    permission_denied: "Accès refusé",
    unsupported_action: "Action non prise en charge",
    official_web_ingestion: "Ingestion site officiel",
    ai_model_call: "Appel modèle IA",
    odoo_write_executed: "Écriture Odoo exécutée",
    odoo_status: "Vérification Odoo",
  };

  if (!event) return "Événement système";
  return labels[event] || event;
}

function displayLogTitle(title?: string, eventType?: string) {
  const mappedTitle = translateEvent(title);
  if (title && mappedTitle !== title) return mappedTitle;
  if (title && !/^[a-z_]+$/i.test(title)) return cleanDisplayText(title);
  return translateEvent(eventType || title);
}

function normalizeStatus(status?: string) {
  if (!status) return "logged";
  return status;
}

function translateStatus(status?: string) {
  if (status === "completed") return "Terminé";
  if (status === "pending_approval") return "Validation requise";
  if (status === "approved") return "Approuvé";
  if (status === "rejected") return "Rejeté";
  if (status === "access_denied") return "Accès refusé";
  if (status === "blocked") return "Bloqué";
  if (status === "not_found") return "Introuvable";
  if (status === "failed") return "Échec";
  return status || "Journalisé";
}

function translateRisk(risk?: string) {
  if (risk === "low") return "Faible";
  if (risk === "medium") return "Moyen";
  if (risk === "high") return "Élevé";
  if (risk === "blocked") return "Bloqué";
  return "Faible";
}

function translateApproval(value?: string) {
  if (value === "not_required") return "Non requise";
  if (value === "pending") return "En attente";
  if (value === "approved") return "Approuvée";
  if (value === "rejected") return "Rejetée";
  if (value === "requires_approval") return "Validation requise";
  return "-";
}

function translatePermissionDecision(value?: string) {
  if (value === "allowed") return "Autorisé";
  if (value === "denied") return "Refusé";
  if (value === "requires_approval") return "Validation requise";
  return "Autorisé";
}

function translateRole(value?: string) {
  const labels: Record<string, string> = {
    admin: "Administrateur",
    odoo_manager: "Responsable Odoo",
    it_manager: "Responsable IT",
    support_agent: "Agent Support",
    employee: "Employé",
    readonly_viewer: "Lecture seule",
  };

  if (!value) return "-";
  return labels[value] || value;
}

function formatAgentName(value?: string) {
  const labels: Record<string, string> = {
    odoo_agent: "Agent Odoo",
    support_agent: "Agent Support",
    server_agent: "Agent Serveur",
    security_agent: "Agent Sécurité",
    knowledge_agent: "Agent Connaissance",
    development_agent: "Agent Développement",
    general_agent: "Agent Général",
  };

  if (!value) return "-";
  return labels[value] || value;
}

function compactLogTitle(log: LogEntry) {
  const prompt = cleanDisplayText(log.user_message);

  if (prompt) return prompt;

  return displayLogTitle(log.title, log.event_type);
}

function summarizeLogMessage(log: LogEntry) {
  if (log.permission_decision === "denied" || log.status === "access_denied") {
    return "Accès refusé par la politique de rôle.";
  }

  if (log.risk === "blocked" || log.status === "blocked") {
    return "Requête bloquée pour protéger les secrets, les accès et les systèmes.";
  }

  if (log.approval_status === "pending" || log.status === "pending_approval") {
    return "Action sensible enregistrée en attente de validation humaine.";
  }

  if (log.event_type === "odoo_read") {
    return "Consultation Odoo réalisée en lecture seule.";
  }

  if (log.event_type === "approval_decision") {
    return "Décision de validation enregistrée.";
  }

  if (log.agent === "server_agent" || log.selected_agent === "server_agent") {
    return "Diagnostic serveur enregistré.";
  }

  if (log.agent === "support_agent" || log.selected_agent === "support_agent") {
    return "Réponse support enregistrée.";
  }

  return cleanDisplayText(log.message || log.title || "Événement enregistré par l’orchestrateur.");
}

function translateAction(action?: string) {
  const labels: Record<string, string> = {
    check_stock: "Consultation stock",
    check_price: "Consultation prix",
    check_unit: "Consultation unité",
    check_product_details: "Consultation produit",
    answer_question: "Question répondue",
    odoo_read: "Lecture Odoo",
    approval_required: "Validation requise",
    permission_denied: "Accès refusé",
    unsupported_action: "Action non prise en charge",
    official_web_ingestion: "Ingestion site officiel",
    ai_model_call: "Appel modèle IA",
    change_price: "Modification du prix",
    change_stock: "Modification du stock",
    change_unit: "Modification de l’unité",
    modify_invoice: "Action facture",
  };

  if (!action) return "-";
  return labels[action] || action;
}

function formatValue(value?: string | number | null) {
  if (value === undefined || value === null || value === "") return "-";
  return String(value);
}

function formatMoney(value?: string | number | null) {
  const formatted = formatValue(value);

  if (formatted === "-") return formatted;
  if (/\b(dh|mad|eur|usd)\b/i.test(formatted)) return formatted;

  return `${formatted} DH`;
}

function formatExecutionResult(result: ExecutionResult) {
  const status = result.success ? "succès" : "échec";
  const oldPrice = formatMoney(result.old_price);
  const newPrice = formatMoney(result.new_price);
  const message = result.message || "Aucun message retourné.";

  return `Statut : ${status}. Ancien prix : ${oldPrice}. Nouveau prix : ${newPrice}. ${cleanDisplayText(message)}`;
}

function cleanDisplayText(value?: string) {
  if (!value) return "";

  if (/api key|password|secret|token|\.env|xml-rpc|traceback/i.test(value)) {
    return "Information technique masquée pour protéger les accès.";
  }

  return value;
}

function formatDate(value?: string) {
  if (!value) return "-";

  try {
    return new Date(value).toLocaleString("fr-FR", {
      dateStyle: "medium",
      timeStyle: "short",
    });
  } catch {
    return value;
  }
}
