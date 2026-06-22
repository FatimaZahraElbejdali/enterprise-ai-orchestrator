"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { API_BASE_URL } from "@/lib/api";

type OdooStatus = {
  connected?: boolean;
  mode?: string;
};

type ApprovalItem = {
  id?: string;
  status?: string;
  user_message?: string;
  selected_agent?: string;
  selected_model?: string;
  [key: string]: unknown;
};

type AuditLog =
  | string
  | {
      user_message?: string;
      message?: string;
      title?: string;
      intent?: string;
      agent?: string;
      selected_agent?: string;
      approval_status?: string;
      status?: string;
      requires_approval?: boolean;
      risk_level?: string;
      [key: string]: unknown;
    };

const modules = [
  {
    title: "Chat",
    description: "Interroger Odoo, le support IT et les agents internes.",
    href: "/chat",
    code: "IA",
    tone: "blue",
  },
  {
    title: "ERP Odoo",
    description: "Consulter les produits, stocks et documents métiers.",
    href: "/odoo",
    code: "ERP",
    tone: "green",
  },
  {
    title: "Validations",
    description: "Approuver ou refuser les actions sensibles.",
    href: "/approvals",
    code: "VAL",
    tone: "amber",
  },
  {
    title: "Journaux d’audit",
    description: "Suivre les décisions, agents et actions exécutées.",
    href: "/logs",
    code: "AUD",
    tone: "slate",
  },
];

const controls = [
  {
    label: "Routage intelligent",
    detail: "Agent sélectionné selon l’intention",
    tone: "blue",
  },
  {
    label: "Validation humaine",
    detail: "Requise pour les actions sensibles",
    tone: "amber",
  },
  {
    label: "Journal d’audit",
    detail: "Traçabilité des interactions",
    tone: "slate",
  },
  {
    label: "Accès sécurisé",
    detail: "Aucune donnée sensible exposée",
    tone: "green",
  },
];

const agentLabels: Record<string, string> = {
  odoo_agent: "Agent Odoo",
  support_agent: "Agent Support",
  server_agent: "Agent Serveur",
  knowledge_agent: "Agent Connaissance",
  development_agent: "Agent Développement",
  security_agent: "Agent Sécurité",
  general_agent: "Agent Général",
  odoo: "Agent Odoo",
  support: "Agent Support",
  server: "Agent Serveur",
  knowledge: "Agent Connaissance",
  development: "Agent Développement",
  security: "Agent Sécurité",
  general: "Agent Général",
};

const approvalLabels: Record<string, string> = {
  pending: "Validation requise",
  approved: "Validé",
  rejected: "Refusé",
  not_required: "Validation non requise",
  not_required_read_only: "Validation non requise",
  required: "Validation requise",
  completed: "Terminé",
  failed: "Échec",
};

function labelFromMap(
  value: unknown,
  labels: Record<string, string>,
  fallback: string,
) {
  if (typeof value !== "string") {
    return fallback;
  }

  return labels[value] || labels[value.toLowerCase()] || fallback;
}

function formatOdooSource(mode?: string) {
  if (!mode) {
    return "Non renseigné";
  }

  const normalized = mode.toLowerCase();

  if (normalized.includes("mock") || normalized.includes("demo")) {
    return "Mode démo";
  }

  return "Odoo réel";
}

export default function Home() {
  const [odooStatus, setOdooStatus] = useState<OdooStatus | null>(null);
  const [dashboardError, setDashboardError] = useState("");
  const [odooError, setOdooError] = useState("");
  const [approvals, setApprovals] = useState<ApprovalItem[]>([]);
  const [logs, setLogs] = useState<AuditLog[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function loadDashboard() {
      try {
        const backendRes = await fetch(`${API_BASE_URL}/status`, {
          cache: "no-store",
        });

        if (!backendRes.ok) {
          throw new Error("Backend inaccessible");
        }

        const [odooRes, approvalsRes, logsRes] = await Promise.allSettled([
          fetch(`${API_BASE_URL}/odoo/status`, { cache: "no-store" }),
          fetch(`${API_BASE_URL}/approvals`, { cache: "no-store" }),
          fetch(`${API_BASE_URL}/logs`, { cache: "no-store" }),
        ]);

        if (odooRes.status === "fulfilled" && odooRes.value.ok) {
          setOdooStatus(await odooRes.value.json());
          setOdooError("");
        } else {
          setOdooStatus(null);
          setOdooError("Odoo indisponible");
        }

        if (approvalsRes.status === "fulfilled" && approvalsRes.value.ok) {
          const data = await approvalsRes.value.json();
          setApprovals(Array.isArray(data) ? data : data.approvals || []);
        }

        if (logsRes.status === "fulfilled" && logsRes.value.ok) {
          const data = await logsRes.value.json();
          setLogs(Array.isArray(data) ? data : data.logs || []);
        }
      } catch {
        setDashboardError("Backend inaccessible");
        setOdooStatus(null);
        setOdooError("");
      } finally {
        setLoading(false);
      }
    }

    loadDashboard();
  }, []);

  const pendingApprovals = useMemo(() => {
    return approvals.filter((item) => item.status === "pending").length;
  }, [approvals]);

  const cleanLogs = logs
    .filter((log) => {
      const title =
        typeof log === "string"
          ? log
          : log.user_message ||
            log.title ||
            log.message ||
            log.intent ||
            log.selected_agent ||
            "";

      const normalized = String(title).trim().toLowerCase();

      return (
        normalized &&
        normalized !== "string" &&
        normalized !== "undefined" &&
        normalized !== "null"
      );
    })
    .slice(0, 5);

  const isConnected = Boolean(odooStatus?.connected);
  const statusMessage =
    dashboardError ||
    odooError ||
    (loading
      ? "Chargement du statut Odoo..."
      : isConnected
        ? "Connexion Odoo active"
        : "Odoo indisponible");
  const odooSource = formatOdooSource(odooStatus?.mode);

  return (
    <main className="dashboard-shell">
      <style>{`
        .dashboard-shell {
          min-height: 100vh;
          background:
            linear-gradient(180deg, #f8fafc 0%, #eef2f6 100%);
          color: #111827;
          font-family: var(--font-geist-sans), Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        }

        .dashboard-layout {
          display: grid;
          grid-template-columns: 248px minmax(0, 1fr);
          min-height: 100vh;
        }

        .sidebar {
          position: sticky;
          top: 0;
          height: 100vh;
          background: #111827;
          color: white;
          padding: 24px 20px;
          display: flex;
          flex-direction: column;
          justify-content: space-between;
          border-right: 1px solid rgba(255, 255, 255, 0.08);
        }

        .brand-mark {
          width: 38px;
          height: 38px;
          display: grid;
          place-items: center;
          margin-bottom: 24px;
          border-radius: 8px;
          background: #ffffff;
          color: #111827;
          font-size: 15px;
          font-weight: 850;
          letter-spacing: 0;
        }

        .brand-kicker {
          font-size: 12px;
          color: #9ca3af;
          margin-bottom: 8px;
          font-weight: 650;
        }

        .brand-title {
          font-size: 22px;
          line-height: 1.15;
          font-weight: 780;
          letter-spacing: 0;
        }

        .brand-subtitle {
          margin-top: 14px;
          color: #a7b0be;
          font-size: 13px;
          line-height: 1.6;
        }

        .sidebar-nav {
          margin-top: 32px;
          display: grid;
          gap: 6px;
        }

        .sidebar-link {
          display: flex;
          align-items: center;
          justify-content: space-between;
          color: #d1d5db;
          text-decoration: none;
          padding: 10px 10px 10px 12px;
          border-radius: 8px;
          font-size: 14px;
          font-weight: 620;
          transition: 0.16s ease;
        }

        .sidebar-link:hover {
          background: rgba(255, 255, 255, 0.08);
          color: white;
        }

        .sidebar-arrow {
          width: 22px;
          height: 22px;
          display: grid;
          place-items: center;
          border-radius: 6px;
          color: #9ca3af;
          background: rgba(255, 255, 255, 0.05);
        }

        .sidebar-footer {
          border-top: 1px solid rgba(255, 255, 255, 0.12);
          padding-top: 18px;
          font-size: 12px;
          color: #a7b0be;
          line-height: 1.7;
        }

        .main {
          padding: 26px 28px;
          min-width: 0;
        }

        .main-inner {
          width: min(100%, 1400px);
          margin: 0 auto;
        }

        .topbar {
          display: flex;
          justify-content: space-between;
          align-items: center;
          gap: 28px;
          margin-bottom: 20px;
        }

        .page-label {
          display: inline-flex;
          align-items: center;
          gap: 8px;
          font-size: 13px;
          color: #667085;
          font-weight: 700;
        }

        .page-title {
          margin-top: 8px;
          font-size: clamp(32px, 3.1vw, 42px);
          line-height: 1.04;
          font-weight: 820;
          letter-spacing: 0;
          color: #111827;
        }

        .page-summary {
          margin-top: 12px;
          max-width: 650px;
          color: #667085;
          line-height: 1.55;
          font-size: 15px;
        }

        .topbar-actions {
          display: flex;
          gap: 10px;
          align-items: center;
          flex-wrap: nowrap;
          justify-content: flex-end;
          padding-top: 2px;
          min-width: max-content;
        }

        .status-pill {
          display: inline-flex;
          align-items: center;
          gap: 8px;
          min-height: 40px;
          padding: 0 14px;
          border-radius: 999px;
          font-size: 13px;
          font-weight: 760;
          background: ${isConnected ? "#dcfce7" : "#fee2e2"};
          color: ${isConnected ? "#166534" : "#991b1b"};
          border: 1px solid ${isConnected ? "#bbf7d0" : "#fecaca"};
        }

        .status-dot {
          width: 8px;
          height: 8px;
          border-radius: 999px;
          background: ${isConnected ? "#22c55e" : "#ef4444"};
          box-shadow: 0 0 0 4px ${isConnected ? "rgba(34, 197, 94, 0.14)" : "rgba(239, 68, 68, 0.14)"};
        }

        .primary-button,
        .secondary-button {
          min-height: 40px;
          display: inline-flex;
          align-items: center;
          justify-content: center;
          gap: 8px;
          text-decoration: none;
          padding: 0 14px;
          border-radius: 8px;
          font-size: 13px;
          font-weight: 780;
          transition: 0.16s ease;
          white-space: nowrap;
        }

        .primary-button {
          background: #111827;
          color: white;
          border: 1px solid #111827;
        }

        .primary-button:hover {
          background: #263244;
          border-color: #263244;
        }

        .secondary-button {
          background: white;
          color: #111827;
          border: 1px solid #d9e0ea;
        }

        .secondary-button:hover {
          border-color: #b7c1cf;
          background: #f8fafc;
        }

        .dashboard-grid {
          display: grid;
          grid-template-columns: minmax(0, 1fr) 360px;
          gap: 18px;
          align-items: start;
        }

        .primary-stack,
        .side-stack {
          display: grid;
          gap: 18px;
          min-width: 0;
        }

        .card {
          background: rgba(255, 255, 255, 0.94);
          border: 1px solid #dfe5ed;
          border-radius: 8px;
          box-shadow: 0 12px 32px rgba(17, 24, 39, 0.055);
        }

        .command-panel {
          padding: 22px;
          overflow: hidden;
        }

        .command-top {
          display: grid;
          grid-template-columns: minmax(0, 1fr) 250px;
          gap: 20px;
          align-items: stretch;
        }

        .section-kicker {
          display: inline-flex;
          align-items: center;
          gap: 8px;
          font-size: 12px;
          font-weight: 820;
          letter-spacing: 0.08em;
          color: #475467;
          text-transform: uppercase;
        }

        .kicker-line {
          width: 22px;
          height: 2px;
          background: #2563eb;
          border-radius: 999px;
        }

        .command-title {
          margin-top: 10px;
          max-width: 640px;
          font-size: clamp(24px, 2.35vw, 32px);
          line-height: 1.12;
          letter-spacing: 0;
          color: #111827;
          font-weight: 820;
        }

        .command-text {
          margin-top: 12px;
          max-width: 640px;
          color: #667085;
          line-height: 1.55;
          font-size: 14px;
        }

        .connection-tile {
          background: #111827;
          color: white;
          border-radius: 8px;
          padding: 16px;
          display: flex;
          flex-direction: column;
          justify-content: space-between;
          min-height: 158px;
        }

        .connection-label {
          color: #cbd5e1;
          font-size: 12px;
          font-weight: 750;
          text-transform: uppercase;
          letter-spacing: 0.08em;
        }

        .connection-value {
          margin-top: 12px;
          font-size: 26px;
          font-weight: 820;
          color: ${isConnected ? "#6ee7b7" : "#fca5a5"};
        }

        .connection-detail {
          margin-top: 8px;
          color: #cbd5e1;
          font-size: 13px;
          line-height: 1.5;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }

        .connection-actions {
          display: grid;
          grid-template-columns: 1fr;
          gap: 8px;
          margin-top: 18px;
        }

        .dark-button {
          min-height: 38px;
          display: inline-flex;
          align-items: center;
          justify-content: center;
          gap: 8px;
          border-radius: 8px;
          text-decoration: none;
          color: #111827;
          background: white;
          font-size: 13px;
          font-weight: 800;
        }

        .control-grid {
          margin-top: 18px;
          display: grid;
          grid-template-columns: repeat(4, minmax(0, 1fr));
          gap: 8px;
        }

        .control {
          background: #f8fafc;
          border: 1px solid #e3e8ef;
          border-radius: 8px;
          padding: 12px;
          min-width: 0;
        }

        .control-top {
          display: flex;
          align-items: center;
          gap: 8px;
          margin-bottom: 8px;
        }

        .control-dot {
          width: 9px;
          height: 9px;
          border-radius: 999px;
          flex: 0 0 auto;
        }

        .control-dot.blue { background: #2563eb; }
        .control-dot.green { background: #16a34a; }
        .control-dot.amber { background: #d97706; }
        .control-dot.slate { background: #64748b; }

        .control-title {
          min-width: 0;
          font-size: 12px;
          line-height: 1.25;
          font-weight: 780;
          color: #111827;
        }

        .control-status {
          font-size: 11px;
          color: #667085;
          font-weight: 650;
        }

        .metrics {
          display: grid;
          grid-template-columns: repeat(3, minmax(0, 1fr));
          gap: 12px;
        }

        .metric {
          padding: 16px;
          min-width: 0;
        }

        .metric-label {
          font-size: 13px;
          color: #667085;
          font-weight: 760;
        }

        .metric-row {
          margin-top: 12px;
          display: flex;
          align-items: flex-end;
          justify-content: space-between;
          gap: 14px;
        }

        .metric-value {
          font-size: 31px;
          line-height: 0.9;
          font-weight: 850;
          color: #111827;
          letter-spacing: 0;
        }

        .metric-detail {
          font-size: 12px;
          color: #667085;
          text-align: right;
          line-height: 1.35;
        }

        .panel {
          padding: 20px;
          min-width: 0;
        }

        .panel-header {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 14px;
          margin-bottom: 16px;
        }

        .panel-title {
          font-size: 18px;
          font-weight: 820;
          color: #111827;
          letter-spacing: 0;
        }

        .panel-link {
          font-size: 13px;
          color: #2563eb;
          text-decoration: none;
          font-weight: 780;
          white-space: nowrap;
        }

        .module-grid {
          display: grid;
          grid-template-columns: repeat(2, minmax(0, 1fr));
          gap: 12px;
        }

        .module-card {
          display: flex;
          flex-direction: column;
          justify-content: space-between;
          min-height: 144px;
          text-decoration: none;
          color: inherit;
          border-radius: 8px;
          background: #f8fafc;
          border: 1px solid #e3e8ef;
          padding: 16px;
          transition: 0.16s ease;
        }

        .module-card:hover {
          transform: translateY(-2px);
          border-color: #b8c3d1;
          background: white;
          box-shadow: 0 14px 26px rgba(17, 24, 39, 0.08);
        }

        .module-top {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 20px;
        }

        .module-code {
          min-width: 42px;
          height: 34px;
          display: inline-flex;
          align-items: center;
          justify-content: center;
          font-size: 12px;
          font-weight: 850;
          color: #344054;
          background: white;
          border: 1px solid #d9e0ea;
          padding: 0 10px;
          border-radius: 8px;
        }

        .module-card[data-tone="blue"] .module-code { color: #1d4ed8; background: #eff6ff; border-color: #bfdbfe; }
        .module-card[data-tone="green"] .module-code { color: #15803d; background: #f0fdf4; border-color: #bbf7d0; }
        .module-card[data-tone="amber"] .module-code { color: #b45309; background: #fffbeb; border-color: #fde68a; }

        .module-arrow {
          width: 28px;
          height: 28px;
          display: grid;
          place-items: center;
          border-radius: 8px;
          color: #111827;
          background: white;
          border: 1px solid #e3e8ef;
        }

        .module-title {
          font-size: 19px;
          font-weight: 820;
          color: #111827;
        }

        .module-desc {
          margin-top: 9px;
          color: #667085;
          font-size: 13px;
          line-height: 1.5;
        }

        .activity-list {
          display: grid;
          gap: 8px;
        }

        .activity-item {
          background: #f8fafc;
          border: 1px solid #e3e8ef;
          border-radius: 8px;
          padding: 12px;
        }

        .activity-title-row {
          display: flex;
          gap: 10px;
          align-items: flex-start;
          min-width: 0;
        }

        .activity-indicator {
          width: 8px;
          height: 8px;
          margin-top: 6px;
          border-radius: 999px;
          background: #2563eb;
          flex: 0 0 auto;
        }

        .activity-title {
          color: #111827;
          font-size: 13px;
          line-height: 1.35;
          font-weight: 760;
          display: -webkit-box;
          -webkit-line-clamp: 2;
          -webkit-box-orient: vertical;
          overflow: hidden;
        }

        .activity-detail {
          margin-top: 5px;
          color: #667085;
          font-size: 12px;
          padding-left: 18px;
        }

        .info-table {
          display: grid;
        }

        .info-row {
          display: flex;
          justify-content: space-between;
          gap: 20px;
          font-size: 13px;
          padding: 12px 0;
          border-bottom: 1px solid #edf1f5;
        }

        .info-row:first-child {
          border-top: 1px solid #edf1f5;
        }

        .info-label {
          color: #667085;
          font-weight: 700;
        }

        .info-value {
          color: #111827;
          font-weight: 780;
          text-align: right;
          max-width: 260px;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }

        .message-box {
          margin-top: 16px;
          background: #f8fafc;
          border: 1px solid #edf1f5;
          border-radius: 8px;
          padding: 13px;
          color: #667085;
          font-size: 13px;
          line-height: 1.6;
        }

        .empty {
          background: #f8fafc;
          border: 1px dashed #b8c3d1;
          border-radius: 8px;
          padding: 14px;
          font-size: 13px;
          color: #667085;
          line-height: 1.5;
        }

        @media (max-width: 1180px) {
          .dashboard-grid,
          .command-top {
            grid-template-columns: 1fr;
          }

          .side-stack {
            grid-template-columns: repeat(2, minmax(0, 1fr));
          }
        }

        @media (max-width: 1050px) {
          .dashboard-layout {
            grid-template-columns: 1fr;
          }

          .sidebar {
            position: static;
            height: auto;
            display: block;
          }

          .sidebar-footer {
            display: none;
          }

          .sidebar-nav {
            grid-template-columns: repeat(4, minmax(0, 1fr));
          }

          .brand-subtitle {
            max-width: 560px;
          }
        }

        @media (max-width: 760px) {
          .main {
            padding: 20px;
          }

          .topbar {
            align-items: stretch;
            flex-direction: column;
          }

          .topbar-actions {
            justify-content: stretch;
            flex-wrap: wrap;
            min-width: 0;
          }

          .topbar-actions > * {
            flex: 1 1 auto;
          }

          .metrics,
          .control-grid,
          .module-grid,
          .side-stack,
          .sidebar-nav {
            grid-template-columns: 1fr;
          }

          .command-panel,
          .panel {
            padding: 18px;
          }

          .metric-row {
            align-items: flex-start;
            flex-direction: column;
          }

          .metric-detail {
            text-align: left;
          }
        }
      `}</style>

      <div className="dashboard-layout">
        <aside className="sidebar">
          <div>
            <div>
              <div className="brand-mark">JB</div>
              <p className="brand-kicker">Jamain Baco</p>
              <h2 className="brand-title">
                Orchestrateur IA
                <br />
                d’entreprise
              </h2>
              <p className="brand-subtitle">
                Accès contrôlé aux systèmes internes, journal d’audit et
                validation humaine.
              </p>
            </div>

            <nav className="sidebar-nav">
              {modules.map((module) => (
                <Link
                  key={module.title}
                  className="sidebar-link"
                  href={module.href}
                >
                  {module.title}
                  <span className="sidebar-arrow">→</span>
                </Link>
              ))}
            </nav>
          </div>

          <div className="sidebar-footer">
            Sécurisé par conception
            <br />
            Accès contrôlé · Journal d’audit · Validation humaine
          </div>
        </aside>

        <section className="main">
          <div className="main-inner">
            <header className="topbar">
              <div>
                <p className="page-label">
                  <span className="status-dot" />
                  Plateforme IA d’entreprise
                </p>
                <h1 className="page-title">Tableau de bord opérationnel</h1>
                <p className="page-summary">
                  Supervisez les agents, les validations humaines, les journaux
                  d’audit et la connexion Odoo depuis une interface centrale.
                </p>
              </div>

              <div className="topbar-actions">
                <span className="status-pill">
                  <span className="status-dot" />
                  {isConnected ? "Odoo connecté" : "Odoo indisponible"}
                </span>

                <Link href="/odoo" className="secondary-button">
                  Ouvrir Odoo
                </Link>

                <Link href="/chat" className="primary-button">
                  Ouvrir le chat
                </Link>
              </div>
            </header>

            <section className="dashboard-grid">
              <div className="primary-stack">
                <section className="card command-panel">
                  <div className="command-top">
                    <div>
                      <p className="section-kicker">
                        <span className="kicker-line" />
                        Opérations IA sécurisées
                      </p>
                      <h2 className="command-title">
                        Orchestrateur IA sécurisé pour Odoo et les systèmes
                        internes
                      </h2>
                      <p className="command-text">
                        L’orchestrateur analyse les demandes des utilisateurs,
                        sélectionne l’agent approprié, applique les règles de
                        risque et déclenche une validation humaine avant toute
                        action sensible.
                      </p>
                    </div>

                    <div className="connection-tile">
                      <div>
                        <p className="connection-label">Intégration Odoo</p>
                        <p className="connection-value">
                          {isConnected ? "Connecté" : "Indisponible"}
                        </p>
                        <p className="connection-detail">
                          {statusMessage}
                        </p>
                      </div>

                      <div className="connection-actions">
                        <Link href="/odoo" className="dark-button">
                          Ouvrir le connecteur →
                        </Link>
                      </div>
                    </div>
                  </div>

                  <div className="control-grid">
                    {controls.map((control) => (
                      <Control
                        key={control.label}
                        label={control.label}
                        detail={control.detail}
                        tone={control.tone}
                      />
                    ))}
                  </div>
                </section>

                <section className="metrics">
                  <Metric
                    label="Validations en attente"
                    value={String(pendingApprovals)}
                    detail="File de validation humaine"
                  />
                  <Metric
                    label="Événements d’audit"
                    value={String(logs.length)}
                    detail="Interactions enregistrées"
                  />
                  <Metric
                    label="Systèmes connectés"
                    value={isConnected ? "1" : "0"}
                    detail={isConnected ? "Odoo ERP actif" : "Connecteur inactif"}
                  />
                </section>

                <section className="card panel">
                  <div className="panel-header">
                    <h3 className="panel-title">Modules opérationnels</h3>
                  </div>

                  <div className="module-grid">
                    {modules.map((module) => (
                      <Link
                        key={module.title}
                        href={module.href}
                        className="module-card"
                        data-tone={module.tone}
                      >
                        <div>
                          <div className="module-top">
                            <span className="module-code">{module.code}</span>
                            <span className="module-arrow">→</span>
                          </div>

                          <h4 className="module-title">{module.title}</h4>
                          <p className="module-desc">{module.description}</p>
                        </div>
                      </Link>
                    ))}
                  </div>
                </section>
              </div>

              <aside className="side-stack">
                <section className="card panel">
                  <div className="panel-header">
                    <h3 className="panel-title">Activité récente</h3>
                    <Link href="/logs" className="panel-link">
                      Voir tout
                    </Link>
                  </div>

                  {cleanLogs.length > 0 ? (
                    <div className="activity-list">
                      {cleanLogs.map((log, index) => (
                        <Activity key={index} log={log} />
                      ))}
                    </div>
                  ) : (
                    <p className="empty">
                      Aucun événement d’audit pour le moment. Les interactions
                      apparaîtront ici après utilisation de l’orchestrateur.
                    </p>
                  )}
                </section>

                <section className="card panel">
                  <div className="panel-header">
                    <h3 className="panel-title">Détails Odoo</h3>
                    <span className="panel-link">
                      {isConnected ? "Actif" : "Indisponible"}
                    </span>
                  </div>

                  <div className="info-table">
                    <Info
                      label="Connexion"
                      value={isConnected ? "Connecté" : "Déconnecté"}
                    />
                    <Info
                      label="Source"
                      value={isConnected ? odooSource : "Non disponible"}
                    />
                    <Info
                      label="Statut"
                      value={
                        dashboardError ||
                        odooError ||
                        (isConnected ? "Actif" : "Indisponible")
                      }
                    />
                  </div>

                  <p className="message-box">
                    {statusMessage}
                  </p>
                </section>
              </aside>
            </section>
          </div>
        </section>
      </div>
    </main>
  );
}

function Control({
  label,
  detail,
  tone,
}: {
  label: string;
  detail: string;
  tone: string;
}) {
  return (
    <div className="control">
      <div className="control-top">
        <span className={`control-dot ${tone}`} />
        <p className="control-title">{label}</p>
      </div>
      <p className="control-status">{detail}</p>
    </div>
  );
}

function Metric({
  label,
  value,
  detail,
}: {
  label: string;
  value: string;
  detail: string;
}) {
  return (
    <div className="card metric">
      <p className="metric-label">{label}</p>
      <div className="metric-row">
        <p className="metric-value">{value}</p>
        <p className="metric-detail">{detail}</p>
      </div>
    </div>
  );
}

function Info({ label, value }: { label: string; value: string }) {
  return (
    <div className="info-row">
      <span className="info-label">{label}</span>
      <span className="info-value">{value}</span>
    </div>
  );
}

function Activity({ log }: { log: AuditLog }) {
  const title =
    typeof log === "string"
      ? log
      : log.user_message || log.title || log.message || log.intent || "Événement système";

  const agentValue =
    typeof log === "string" ? undefined : log.selected_agent || log.agent || log.intent;
  const validationValue =
    typeof log === "string"
      ? undefined
      : log.approval_status ||
        log.status ||
        (log.requires_approval ? "pending" : "not_required");

  const detail =
    typeof log === "string"
      ? "Événement enregistré"
      : `${labelFromMap(agentValue, agentLabels, "Agent interne")} · ${labelFromMap(
          validationValue,
          approvalLabels,
          "Statut enregistré",
        )}`;

  return (
    <div className="activity-item">
      <div className="activity-title-row">
        <span className="activity-indicator" />
        <p className="activity-title">{title}</p>
      </div>
      <p className="activity-detail">{detail}</p>
    </div>
  );
}
