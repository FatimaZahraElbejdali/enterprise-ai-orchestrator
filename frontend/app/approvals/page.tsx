"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

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
  requested_change?: string;
  executed?: boolean;
  metadata?: Record<string, any>;
};

export default function ApprovalsPage() {
  const [approvals, setApprovals] = useState<Approval[]>([]);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState<string | null>(null);

  async function loadApprovals() {
    setLoading(true);

    try {
      const res = await fetch(`${API_BASE}/approvals`, {
        cache: "no-store",
      });

      if (res.ok) {
        const data = await res.json();
        setApprovals(Array.isArray(data) ? data : []);
      }
    } finally {
      setLoading(false);
    }
  }

  async function updateApproval(id: string, decision: "approve" | "reject") {
    setActionLoading(id);

    try {
      const res = await fetch(`${API_BASE}/approvals/${id}/${decision}`, {
        method: "POST",
      });

      if (res.ok) {
        await loadApprovals();
      }
    } finally {
      setActionLoading(null);
    }
  }

  useEffect(() => {
    loadApprovals();
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
            <Link href="/approvals" className="active">
              Validations
            </Link>
            <Link href="/logs">Audit Logs</Link>
          </nav>
        </div>

        <div className="sidebarFooter">
          <p>Contrôle humain</p>
          <span>
            Les actions sensibles sont bloquées jusqu’à validation.
          </span>
        </div>
      </aside>

      <section className="content">
        <header className="header">
          <div>
            <p className="eyebrow">Workflow de validation</p>
            <h2>Demandes d’approbation</h2>
            <p className="subtitle">
              Les demandes sensibles détectées par l’orchestrateur sont
              enregistrées ici avant toute exécution dans Odoo.
            </p>
          </div>

          <button className="refreshButton" onClick={loadApprovals}>
            Actualiser
          </button>
        </header>

        <section className="metrics">
          <Metric label="En attente" value={pendingCount} tone="warning" />
          <Metric label="Approuvées" value={approvedCount} tone="success" />
          <Metric label="Rejetées" value={rejectedCount} tone="danger" />
        </section>

        <section className="listPanel">
          <div className="panelHeader">
            <div>
              <p className="eyebrow">Actions sensibles</p>
              <h3>File de validation</h3>
            </div>
          </div>

          {loading && <p className="emptyText">Chargement...</p>}

          {!loading && approvals.length === 0 && (
            <p className="emptyText">
              Aucune demande de validation pour le moment.
            </p>
          )}

          {!loading &&
            approvals.map((approval) => {
              const isPending = approval.status === "pending";

              return (
                <article className="approvalCard" key={approval.id}>
                  <div className="approvalTop">
                    <div>
                      <div className="titleRow">
                        <h4>
                          {approval.title ||
                            translateAction(approval.action) ||
                            "Action sensible"}
                        </h4>
                        <span className={`status ${approval.status}`}>
                          {translateStatus(approval.status)}
                        </span>
                      </div>

                      <p className="message">
                        {approval.description ||
                          approval.user_message ||
                          "Demande enregistrée par l’orchestrateur."}
                      </p>
                    </div>

                    <span className={`risk ${approval.risk || "medium"}`}>
                      Risque {translateRisk(approval.risk)}
                    </span>
                  </div>

                  <div className="detailsGrid">
                    <Detail label="Système" value={approval.source_system || "odoo"} />
                    <Detail label="Agent" value={approval.selected_agent || "-"} />
                    <Detail label="Action" value={translateAction(approval.action)} />
                    <Detail label="Produit" value={approval.entity_name || "-"} />
                    <Detail
                      label="Valeur demandée"
                      value={approval.requested_change || "-"}
                    />
                    <Detail
                      label="Exécuté dans Odoo"
                      value={approval.executed ? "Oui" : "Non"}
                    />
                    <Detail
                      label="Date"
                      value={formatDate(approval.timestamp)}
                    />
                    <Detail
                      label="ID validation"
                      value={approval.id}
                    />
                  </div>

                  {approval.user_message && (
                    <div className="requestBox">
                      <span>Demande originale</span>
                      <p>{approval.user_message}</p>
                    </div>
                  )}

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
                      Rejeter
                    </button>
                  </div>
                </article>
              );
            })}
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
          padding: 22px;
          margin-bottom: 16px;
          background: #fbfcfe;
        }

        .approvalTop {
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

        .message {
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
          margin-bottom: 16px;
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
          .detailsGrid {
            grid-template-columns: 1fr;
          }
        }
      `}</style>
    </main>
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
  if (risk === "low") return "faible";
  if (risk === "medium") return "moyen";
  if (risk === "high") return "élevé";
  return "moyen";
}

function translateAction(action?: string) {
  const labels: Record<string, string> = {
    change_price: "Modification du prix",
    change_stock: "Modification du stock",
    change_unit: "Modification de l’unité",
    modify_invoice: "Action sensible sur facture",
    create_purchase_request: "Création d’une demande d’achat",
  };

  if (!action) return "-";
  return labels[action] || action;
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