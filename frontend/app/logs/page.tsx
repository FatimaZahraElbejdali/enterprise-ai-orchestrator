"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

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
  status?: string;
  risk?: string;
  approval_status?: string;
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

export default function LogsPage() {
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [loading, setLoading] = useState(true);

  async function loadLogs() {
    setLoading(true);

    try {
      const res = await fetch(`${API_BASE}/logs`, {
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
      }
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void loadLogs();
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
          log.approval_status === "pending"
      ).length,
    [logs]
  );

  return (
    <main className="pageShell">
      <aside className="sidebar">
        <div>
          <div className="brand">
            <div className="brandMark">JB</div>
            <div>
              <p>Jamain Baco</p>
              <h1>AI Orchestrator</h1>
            </div>
          </div>

          <nav className="nav">
            <Link href="/">Tableau de bord</Link>
            <Link href="/chat">Console Chat</Link>
            <Link href="/odoo">Odoo</Link>
            <Link href="/approvals">Validations</Link>
            <Link href="/logs" className="active">
              Audit Logs
            </Link>
          </nav>
        </div>

        <div className="sidebarFooter">
          <p>Traçabilité</p>
          <span>
            Les actions de l’orchestrateur sont enregistrées pour audit.
          </span>
        </div>
      </aside>

      <section className="content">
        <header className="header">
          <div>
            <p className="eyebrow">Journal d’audit</p>
            <h2>Traçabilité des actions</h2>
            <p className="subtitle">
              Suivi des consultations Odoo, demandes sensibles, décisions
              d’approbation et actions bloquées par la politique de sécurité.
            </p>
          </div>

          <button onClick={loadLogs}>Actualiser</button>
        </header>

        <section className="metrics">
          <Metric label="Événements" value={logs.length} />
          <Metric label="Lectures Odoo" value={odooReads} />
          <Metric label="Validations" value={approvalEvents} />
          <Metric label="Actions bloquées" value={blockedActions} />
        </section>

        <section className="panel">
          <div className="panelHeader">
            <div>
              <p className="eyebrow">Historique</p>
              <h3>Événements récents</h3>
            </div>
          </div>

          {loading && <p className="empty">Chargement des logs...</p>}

          {!loading && logs.length === 0 && (
            <p className="empty">Aucun événement d’audit propre à afficher.</p>
          )}

          {!loading &&
            logs.map((log, index) => (
              <article className="logCard" key={log.id || index}>
                <div className="logTop">
                  <div>
                    <div className="titleRow">
                      <h4>{log.title || translateEvent(log.event_type)}</h4>
                      <span className={`status ${normalizeStatus(log.status)}`}>
                        {translateStatus(log.status)}
                      </span>
                    </div>

                    <p className="logMessage">
                      {log.message ||
                        log.user_message ||
                        "Événement enregistré par l’orchestrateur."}
                    </p>
                  </div>

                  <span className={`risk ${log.risk || "low"}`}>
                    Risque {translateRisk(log.risk)}
                  </span>
                </div>

                <div className="detailsGrid">
                  <Detail label="Système" value={log.system || "-"} />
                  <Detail label="Agent" value={log.agent || "-"} />
                  <Detail label="Action" value={translateAction(log.action)} />
                  <Detail label="Produit" value={log.product || "-"} />
                  <Detail
                    label="Validation"
                    value={translateApproval(log.approval_status)}
                  />
                  <Detail
                    label="Exécuté"
                    value={log.executed === true ? "Oui" : "Non / lecture seule"}
                  />
                  <Detail
                    label="Valeur demandée"
                    value={formatValue(log.requested_value)}
                  />
                  <Detail label="Date" value={formatDate(log.timestamp)} />
                  <Detail
                    label="Ancien prix"
                    value={formatValue(log.execution_result?.old_price)}
                  />
                  <Detail
                    label="Nouveau prix"
                    value={formatValue(log.execution_result?.new_price)}
                  />
                </div>

                {log.user_message && (
                  <div className="requestBox">
                    <span>Demande utilisateur</span>
                    <p>{log.user_message}</p>
                  </div>
                )}

                {log.execution_result && (
                  <div className="requestBox">
                    <span>Résultat Odoo</span>
                    <p>{formatExecutionResult(log.execution_result)}</p>
                  </div>
                )}
              </article>
            ))}
        </section>
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
          width: 44px;
          height: 44px;
          background: #ffffff;
          color: #101827;
          display: grid;
          place-items: center;
          font-weight: 900;
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
        }

        .panelHeader h3 {
          margin: 6px 0 0;
          font-size: 22px;
          color: #101827;
        }

        .empty {
          color: #647084;
          font-weight: 700;
        }

        .logCard {
          border: 1px solid #d9dee7;
          background: #fbfcfe;
          padding: 22px;
          margin-bottom: 16px;
        }

        .logTop {
          display: flex;
          justify-content: space-between;
          gap: 18px;
          margin-bottom: 18px;
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

        .logMessage {
          margin: 0;
          color: #647084;
          line-height: 1.6;
        }

        .status,
        .risk {
          border-radius: 999px;
          padding: 7px 10px;
          font-size: 12px;
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
          border-top: 1px solid #e5e7eb;
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
          .detailsGrid {
            grid-template-columns: 1fr;
          }
        }
      `}</style>
    </main>
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
    odoo_read: "Consultation Odoo",
    approval_required: "Validation requise",
    approval_decision: "Décision de validation",
    odoo_write_executed: "Écriture Odoo exécutée",
    odoo_status: "Vérification Odoo",
  };

  if (!event) return "Événement système";
  return labels[event] || event;
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
  if (status === "not_found") return "Introuvable";
  if (status === "failed") return "Échec";
  return status || "Journalisé";
}

function translateRisk(risk?: string) {
  if (risk === "low") return "faible";
  if (risk === "medium") return "moyen";
  if (risk === "high") return "élevé";
  return "faible";
}

function translateApproval(value?: string) {
  if (value === "not_required") return "Non requise";
  if (value === "pending") return "En attente";
  if (value === "approved") return "Approuvée";
  if (value === "rejected") return "Rejetée";
  return "-";
}

function translateAction(action?: string) {
  const labels: Record<string, string> = {
    check_stock: "Consultation stock",
    check_price: "Consultation prix",
    check_unit: "Consultation unité",
    check_product_details: "Consultation produit",
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

function formatExecutionResult(result: ExecutionResult) {
  const status = result.success ? "succès" : "échec";
  const oldPrice = formatValue(result.old_price);
  const newPrice = formatValue(result.new_price);
  const message = result.message || "Aucun message retourné.";

  return `Statut: ${status}. Ancien prix: ${oldPrice}. Nouveau prix: ${newPrice}. ${message}`;
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
