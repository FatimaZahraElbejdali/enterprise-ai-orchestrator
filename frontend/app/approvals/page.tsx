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
  source?: string;
  action?: string;
  model?: string;
  document?: string;
  record_id?: string | number | null;
  line_id?: string | number | null;
  field?: string;
  product?: string;
  product_id?: string | number | null;
  old_price?: string | number | null;
  new_price?: string | number | null;
  old_value?: string | number | boolean | null;
  requested_value?: string | number | boolean | null;
  new_value?: string | number | boolean | null;
  executed?: boolean;
  found?: boolean;
  message?: string;
  candidates?: Candidate[];
  [key: string]: unknown;
};

type Candidate = {
  id?: string | number | null;
  line_id?: string | number | null;
  record_id?: string | number | null;
  name?: string;
  product?: string;
  product_name?: string;
  default_code?: string;
  list_price?: string | number | null;
  price_unit?: string | number | null;
  quantity?: string | number | null;
  qty_available?: string | number | null;
  virtual_available?: string | number | null;
  partner?: string;
  state?: string;
  date?: string;
  ref?: string;
  email?: string;
  phone?: string;
  sale_ok?: boolean;
  active?: boolean;
  uom_id?: string;
};

type Approval = {
  id: string;
  timestamp?: string;
  updated_at?: string | null;
  status: "pending" | "approved" | "rejected";
  user_message?: string;
  intent?: string;
  selected_agent?: string;
  selected_model?: string;
  action?: string;
  risk?: string;
  title?: string;
  description?: string;
  source_system?: string;
  entity_name?: string;
  requested_change?: string | number;
  executed?: boolean;
  execution_result?: ExecutionResult;
  metadata?: Record<string, unknown>;
};

export default function ApprovalsPage() {
  const [approvals, setApprovals] = useState<Approval[]>([]);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [currentUser] = useState<AuthUser | null>(() => getStoredUser());
  const [error, setError] = useState("");
  const accessDenied = !hasAnyPermission(currentUser, [
    "all",
    "view_approvals",
    "approve_odoo_actions",
  ]);

  function handleLogout() {
    clearAuth();
    window.location.href = "/login";
  }

  async function loadApprovals() {
    setLoading(true);
    setError("");

    try {
      const res = await apiFetch(`${API_BASE_URL}/approvals`, {
        cache: "no-store",
      });

      if (res.ok) {
        const data = await res.json();
        setApprovals(Array.isArray(data) ? data : []);
      } else {
        setError(API_ERROR_MESSAGE);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : API_ERROR_MESSAGE);
    } finally {
      setLoading(false);
    }
  }

  async function updateApproval(id: string, decision: "approve" | "reject") {
    setActionLoading(id);

    try {
      const res = await apiFetch(`${API_BASE_URL}/approvals/${id}/${decision}`, {
        method: "POST",
      });

      if (res.ok) {
        await loadApprovals();
      } else {
        setError(API_ERROR_MESSAGE);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : API_ERROR_MESSAGE);
    } finally {
      setActionLoading(null);
    }
  }

  useEffect(() => {
    if (!requireAuth()) return;
    void validateAuthSession("/approvals");

    const user = getStoredUser();

    if (!hasAnyPermission(user, ["all", "view_approvals", "approve_odoo_actions"])) {
      return;
    }

    const timer = window.setTimeout(() => {
      void loadApprovals();
    }, 0);

    return () => window.clearTimeout(timer);
  }, []);

  const pendingCount = useMemo(
    () => approvals.filter((item) => item.status === "pending").length,
    [approvals]
  );

  const approvedCount = useMemo(
    () => approvals.filter((item) => item.status === "approved").length,
    [approvals]
  );

  const rejectedCount = useMemo(
    () => approvals.filter((item) => item.status === "rejected").length,
    [approvals]
  );

  return (
    <AppShell
      active="approvals"
      eyebrow="Workflow"
      title="Demandes d’approbation"
      subtitle="Les demandes sensibles détectées par l’orchestrateur sont enregistrées ici avant toute exécution dans Odoo."
      actions={
        <button className="refreshButton" onClick={loadApprovals}>
          Actualiser
        </button>
      }
    >
        <section className="metrics">
          <Metric label="En attente" value={pendingCount} tone="warning" />
          <Metric label="Approuvées" value={approvedCount} tone="success" />
          <Metric label="Rejetées" value={rejectedCount} tone="danger" />
        </section>

        {(error || accessDenied) && (
          <div className="errorBox">
            {accessDenied ? ACCESS_DENIED_MESSAGE : error}
          </div>
        )}

        <section className="listPanel">
          <div className="panelHeader">
            <div>
              <p className="eyebrow">Actions sensibles</p>
              <h3>File de validation</h3>
            </div>
          </div>

          {loading && !accessDenied && <p className="emptyText">Chargement...</p>}

          {!loading && !accessDenied && approvals.length === 0 && (
            <p className="emptyText">
              Aucune demande de validation pour le moment.
            </p>
          )}

          {!loading &&
            !accessDenied &&
            approvals.map((approval) => {
              const isPending = approval.status === "pending";

              return (
                <article className="approvalCard" key={approval.id}>
                  <div className="approvalTop">
                    <div>
                      <div className="titleRow">
                        <h4>{approvalSummary(approval)}</h4>
                        <span className={`status ${approval.status}`}>
                          {translateStatus(approval.status)}
                        </span>
                      </div>

                      <div className="businessInfo">
                        <span>Demande originale :</span>
                        <p>{displayApprovalText(approval.user_message) || "Demande enregistrée par l’orchestrateur."}</p>
                      </div>
                    </div>

                    <div className="cardBadges">
                      <span className={`risk ${approval.risk || "medium"}`}>
                        Risque {translateRisk(approval.risk)}
                      </span>
                    </div>
                  </div>

                  <div className="cardMeta">
                    <span>Date : {formatDate(approval.timestamp)}</span>
                    <span>Statut : {translateStatus(approval.status)}</span>
                  </div>

                  <details className="technicalDetails">
                    <summary>Détails techniques</summary>
                    <div className="technicalGrid">
                      {technicalDetails(approval).map((item) => (
                        <Detail
                          key={item.label}
                          label={item.label}
                          value={item.value}
                        />
                      ))}
                    </div>
                  </details>

                  <div className="actions">
                    <button
                      disabled={!isPending || actionLoading === approval.id}
                      onClick={() => updateApproval(approval.id, "approve")}
                    >
                      Approuver
                    </button>

                    <button
                      className="reject"
                      disabled={!isPending || actionLoading === approval.id}
                      onClick={() => updateApproval(approval.id, "reject")}
                    >
                      Refuser
                    </button>
                  </div>
                </article>
              );
            })}
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
          background: #f4f6f8;
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
          color: #101827;
          font-size: 30px;
          letter-spacing: -0.04em;
        }

        .subtitle {
          margin: 0;
          max-width: 780px;
          color: #5b6472;
          font-size: 15px;
          line-height: 1.6;
        }

        .refreshButton {
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
          grid-template-columns: repeat(3, minmax(0, 1fr));
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

        .metric.warning {
          border-left: 4px solid #b7791f;
        }

        .metric.success {
          border-left: 4px solid #13754a;
        }

        .metric.danger {
          border-left: 4px solid #9f1d1d;
        }

        .listPanel {
          background: #ffffff;
          border: 1px solid #d9dee7;
          padding: 24px;
        }

        .panelHeader {
          margin-bottom: 18px;
        }

        .panelHeader h3 {
          margin: 6px 0 0;
          color: #101827;
          font-size: 22px;
        }

        .emptyText {
          color: #647084;
          font-weight: 700;
        }

        .approvalCard {
          border: 1px solid #d9dee7;
          padding: 18px;
          margin-bottom: 14px;
          background: #fbfcfe;
        }

        .approvalTop {
          display: flex;
          justify-content: space-between;
          gap: 18px;
          margin-bottom: 14px;
        }

        .titleRow {
          display: flex;
          align-items: center;
          gap: 10px;
          margin-bottom: 8px;
        }

        .titleRow h4 {
          margin: 0;
          font-size: 20px;
          color: #101827;
        }

        .message {
          margin: 0;
          color: #647084;
          line-height: 1.6;
        }

        .businessInfo {
          background: #ffffff;
          border: 1px solid #e5e7eb;
          padding: 12px;
          max-width: 860px;
        }

        .businessInfo span {
          display: block;
          margin-bottom: 5px;
          color: #647084;
          font-size: 12px;
          font-weight: 900;
        }

        .businessInfo p {
          margin: 0;
          color: #172033;
          font-size: 14px;
          line-height: 1.5;
          font-weight: 700;
        }

        .cardBadges {
          display: flex;
          align-items: flex-start;
          justify-content: flex-end;
        }

        .cardMeta {
          display: flex;
          flex-wrap: wrap;
          gap: 10px 18px;
          margin-bottom: 12px;
          color: #647084;
          font-size: 13px;
          font-weight: 800;
        }

        .status,
        .risk {
          border-radius: 999px;
          padding: 7px 10px;
          font-size: 12px;
          font-weight: 900;
          white-space: nowrap;
        }

        .status.pending,
        .risk.medium {
          background: #fff7df;
          color: #8a5a00;
          border: 1px solid #f2d38b;
        }

        .status.approved,
        .risk.low {
          background: #eef8f3;
          color: #13754a;
          border: 1px solid #b8e0cb;
        }

        .status.rejected,
        .risk.high {
          background: #fff1f1;
          color: #9f1d1d;
          border: 1px solid #f2c0c0;
        }

        .technicalGrid {
          display: grid;
          grid-template-columns: repeat(2, minmax(0, 1fr));
          gap: 0 24px;
          border-top: 1px solid #e5e7eb;
          border-bottom: 1px solid #e5e7eb;
          margin-top: 12px;
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

        .technicalDetails {
          background: #ffffff;
          border: 1px solid #e5e7eb;
          padding: 12px;
          margin-bottom: 14px;
        }

        .technicalDetails summary {
          cursor: pointer;
          color: #172033;
          font-weight: 900;
        }

        .actions {
          display: flex;
          gap: 10px;
        }

        .actions button {
          height: 38px;
          border: 1px solid #172033;
          background: #172033;
          color: #ffffff;
          border-radius: 8px;
          padding: 0 14px;
          font-weight: 800;
          cursor: pointer;
        }

        .actions button.reject {
          background: #ffffff;
          color: #9f1d1d;
          border-color: #f2c0c0;
        }

        .actions button:disabled {
          opacity: 0.45;
          cursor: not-allowed;
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
          .technicalGrid {
            grid-template-columns: 1fr;
          }
        }
      `}</style>
    </AppShell>
  );
}

function Metric({
  label,
  value,
  tone,
}: {
  label: string;
  value: number;
  tone: "warning" | "success" | "danger";
}) {
  return (
    <div className={`metric ${tone}`}>
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

function translateStatus(status?: string) {
  if (status === "pending") return "En attente";
  if (status === "approved") return "Approuvée";
  if (status === "rejected") return "Rejetée";
  return status || "-";
}

function translateRisk(risk?: string) {
  if (risk === "low") return "Faible";
  if (risk === "medium") return "Moyen";
  if (risk === "high") return "Élevé";
  if (risk === "blocked") return "Bloqué";
  return "Moyen";
}

function approvalSummary(approval: Approval) {
  const target = approval.entity_name || approval.execution_result?.product;
  const document =
    approval.execution_result?.document ||
    getMetadataString(approval.metadata, "document_query") ||
    getMetadataString(approval.metadata, "document_id");
  const subject = target || document;
  const suffix = subject ? ` pour ${subject}` : "";
  const displayTitle = displayApprovalText(approval.title || approval.action || approval.user_message);

  if (displayTitle === "Modification du stock") {
    return `Modification du stock${suffix}`;
  }

  if (displayTitle === "Modification du prix") {
    return `Modification du prix${suffix}`;
  }

  if (approval.action === "toggle_boolean_field") {
    return `Modification d’un champ analytique${suffix}`;
  }

  if (approval.action === "change_price") {
    return `Modification du prix${suffix}`;
  }

  if (approval.action === "change_stock") {
    return `Modification du stock${suffix}`;
  }

  if (approval.action === "change_unit") {
    return `Modification de l’unité${suffix}`;
  }

  if (approval.action === "update_document_line") {
    return `Modification d’une ligne de document${suffix}`;
  }

  if (approval.action === "update_document_partner") {
    return `Modification du client ou fournisseur${suffix}`;
  }

  if (approval.action === "update_document_date") {
    return `Modification d’une date de document${suffix}`;
  }

  if (approval.action === "create_purchase_request") {
    return `Création d’une demande d’achat${suffix}`;
  }

  return `${displayTitle || translateAction(approval.action) || "Action sensible"}${suffix}`;
}

function technicalDetails(approval: Approval) {
  const result = approval.execution_result;
  const metadata = approval.metadata;
  const details = [
    ["Système", approval.source_system || "odoo"],
    ["Agent", formatAgentName(approval.selected_agent)],
    ["Modèle", approval.selected_model],
    ["Action", translateAction(approval.action)],
    ["Type document", documentTypeLabel(getMetadataString(metadata, "target_model") || result?.model)],
    ["Document", result?.document || getMetadataString(metadata, "document_query")],
    ["ID document", result?.record_id || getMetadataString(metadata, "document_id")],
    ["Partenaire", getMetadataString(metadata, "partner_name")],
    ["Ligne", result?.line_id],
    ["Champ", fieldLabel(result?.field || getMetadataString(metadata, "field_name"))],
    ["Valeur demandée", approval.requested_change || result?.requested_value],
    ["Ancien prix", result?.old_price],
    ["Nouveau prix", result?.new_price],
    ["Ancienne valeur", result?.old_value],
    ["Nouvelle valeur", result?.new_value],
    ["Exécuté dans Odoo", approval.executed ? "Oui" : "Non"],
    ["ID de validation", approval.id],
    ["Résultat", result ? formatExecutionResult(result) : ""],
    ["Candidats détectés", formatCandidates(result?.candidates)],
    ["Métadonnées", formatTechnicalObject(metadata)],
  ];

  return details
    .map(([label, value]) => ({
      label: String(label),
      value: formatValue(sanitizeForDisplay(value)),
    }))
    .filter((item) => item.value !== "-");
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

function translateAction(action?: string) {
  const labels: Record<string, string> = {
    change_price: "Modification du prix",
    change_stock: "Modification du stock",
    "Update the stock quantity": "Modification du stock",
    update_stock_quantity: "Modification du stock",
    change_unit: "Modification de l’unité",
    modify_invoice: "Action sensible sur facture",
    create_purchase_request: "Création d’une demande d’achat",
    toggle_boolean_field: "Modification champ analytique",
    update_document_line: "Modification ligne document",
    update_document_partner: "Modification client/fournisseur",
    update_document_date: "Modification date document",
  };

  if (!action) return "-";
  return labels[action] || action;
}

function displayApprovalText(value?: string) {
  if (!value) return "";

  const normalized = value.trim().toLowerCase();
  const labels: Record<string, string> = {
    "update the stock quantity": "Modification du stock",
    "change_price": "Modification du prix",
    "change stock": "Modification du stock",
  };

  return labels[normalized] || value;
}

function getMetadataString(metadata: Record<string, unknown> | undefined, key: string) {
  const value = metadata?.[key];

  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);

  return "";
}

function documentTypeLabel(model?: string) {
  const labels: Record<string, string> = {
    "sale.order": "Bon de commande client",
    "purchase.order": "Bon de commande fournisseur",
    "account.move": "Facture",
    "stock.picking": "Bon de livraison",
  };

  if (!model) return "-";
  return labels[model] || model;
}

function fieldLabel(field?: string) {
  const labels: Record<string, string> = {
    list_price: "Prix de vente",
    price_unit: "Prix unitaire",
    product_uom_qty: "Quantité",
    product_qty: "Quantité",
    quantity: "Quantité",
    partner_id: "Client/fournisseur",
    date_order: "Date de commande",
    date_planned: "Arrivée prévue",
    expected_arrival_date: "Arrivée prévue",
    invoice_date: "Date facture",
    scheduled_date: "Date livraison",
  };

  if (!field) return "-";
  return labels[field] || field;
}

function formatValue(value?: unknown): string {
  if (value === undefined || value === null || value === "") return "-";
  if (typeof value === "boolean") return value ? "Oui" : "Non";
  if (typeof value === "object") return formatTechnicalObject(value);
  return String(value);
}

function formatExecutionResult(result: ExecutionResult): string {
  const status = result.success ? "succès" : "échec";
  const message = sanitizeText(String(result.message || "Aucun message retourné."));
  const oldPrice = formatValue(result.old_price);
  const newPrice = formatValue(result.new_price);
  const oldValue = formatValue(result.old_value);
  const newValue = formatValue(result.new_value);
  const document = formatValue(result.document);
  const field = fieldLabel(result.field);

  return `Statut : ${status}. Document : ${document}. Champ : ${field}. Ancien prix : ${oldPrice}. Nouveau prix : ${newPrice}. Ancienne valeur : ${oldValue}. Nouvelle valeur : ${newValue}. ${message}`;
}

function formatCandidates(candidates?: Candidate[]): string {
  if (!Array.isArray(candidates) || candidates.length === 0) return "";

  return candidates
    .map((candidate) => {
      const name =
        candidate.name ||
        candidate.product_name ||
        candidate.product ||
        candidate.partner ||
        candidate.ref ||
        candidate.id;

      return formatValue(sanitizeForDisplay(name));
    })
    .filter((value) => value !== "-")
    .join(", ");
}

function formatTechnicalObject(value: unknown): string {
  const sanitized = sanitizeForDisplay(value);

  if (!sanitized || typeof sanitized !== "object" || Array.isArray(sanitized)) {
    return "";
  }

  return Object.entries(sanitized)
    .map(([key, entry]): string => `${technicalLabel(key)}: ${formatValue(entry)}`)
    .filter((item) => !item.endsWith(": -"))
    .join(" · ");
}

function technicalLabel(key: string) {
  const labels: Record<string, string> = {
    document_query: "Document",
    document_id: "ID document",
    field_name: "Champ",
    new_value: "Nouvelle valeur",
    old_value: "Ancienne valeur",
    product_name: "Produit",
    target_model: "Type document",
  };

  return labels[key] || key;
}

const SENSITIVE_DISPLAY_KEYS = new Set([
  "db",
  "url",
  "odoo_url",
  "database",
  "database_name",
  "dbname",
  "username",
  "user",
  "uid",
  "error",
  "errors",
  "exception",
  "traceback",
  "provider_error",
  "raw_error",
  "xmlrpc",
  "xml_rpc",
  "diagnostics",
  "api_key",
  "password",
  "token",
  "secret",
]);

function isSensitiveDisplayKey(key: string) {
  const normalized = key.toLowerCase();
  const compact = normalized.replace(/[\s_-]/g, "");

  return (
    SENSITIVE_DISPLAY_KEYS.has(normalized) ||
    compact.includes("url") ||
    compact.includes("database") ||
    compact.includes("dbname") ||
    compact.includes("apikey") ||
    normalized.includes("api_key") ||
    normalized.includes("password") ||
    normalized.includes("token") ||
    normalized.includes("secret") ||
    normalized.includes("traceback") ||
    normalized.includes("xmlrpc") ||
    normalized.includes("xml-rpc") ||
    normalized.includes("provider_error")
  );
}

function sanitizeForDisplay(value: unknown): unknown {
  if (Array.isArray(value)) {
    return value.map((item) => sanitizeForDisplay(item));
  }

  if (typeof value === "string") {
    return sanitizeText(value);
  }

  if (typeof value !== "object" || value === null) {
    return value;
  }

  return Object.fromEntries(
    Object.entries(value)
      .filter(([key]) => !isSensitiveDisplayKey(key))
      .map(([key, entry]) => [key, sanitizeForDisplay(entry)])
  );
}

function sanitizeText(value: string) {
  if (
    /api key|api_key|password|secret|token|\.env|xml-?rpc|traceback|odoo url|database name|username|uid|provider error/i.test(
      value
    )
  ) {
    return "[information masquée]";
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
