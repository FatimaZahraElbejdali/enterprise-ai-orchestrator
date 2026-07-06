"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import Image from "next/image";
import {
  API_BASE_URL,
  AuthUser,
  authHeaders,
  clearAuth,
  getRoleLabel,
  getStoredUser,
  requireAuth,
} from "@/lib/api";

type OdooStatus = {
  connected?: boolean;
  mode?: string;
};

type ApprovalItem = {
  status?: string;
  [key: string]: unknown;
};

type AuditLog = unknown;

type OdooBadge = {
  label: "Odoo connecté" | "Odoo indisponible" | "Connexion requise" | "Session expirée";
  tone: "success" | "danger" | "warning";
};

const actions = [
  { title: "Chat IA", href: "/chat" },
  { title: "Odoo", href: "/odoo" },
  { title: "Validations", href: "/approvals" },
  { title: "Journaux d’audit", href: "/logs" },
];

export default function Home() {
  const [odooStatus, setOdooStatus] = useState<OdooStatus | null>(null);
  const [odooBadge, setOdooBadge] = useState<OdooBadge>({
    label: "Connexion requise",
    tone: "warning",
  });
  const [approvals, setApprovals] = useState<ApprovalItem[]>([]);
  const [logs, setLogs] = useState<AuditLog[]>([]);
  const [currentUser] = useState<AuthUser | null>(() => getStoredUser());

  function handleLogout() {
    clearAuth();
    window.location.href = "/login";
  }

  useEffect(() => {
    if (!requireAuth()) return;

    async function loadDashboard() {
      try {
        const [odooRes, approvalsRes, logsRes] = await Promise.allSettled([
          fetch(`${API_BASE_URL}/odoo/status`, {
            cache: "no-store",
            headers: authHeaders(),
          }),
          fetch(`${API_BASE_URL}/approvals`, {
            cache: "no-store",
            headers: authHeaders(),
          }),
          fetch(`${API_BASE_URL}/logs`, {
            cache: "no-store",
            headers: authHeaders(),
          }),
        ]);

        if (odooRes.status === "fulfilled") {
          if (odooRes.value.status === 401) {
            setOdooStatus(null);
            setOdooBadge({ label: "Session expirée", tone: "warning" });
          } else if (odooRes.value.ok) {
            const data = await odooRes.value.json();
            setOdooStatus(data);
            setOdooBadge(
              data?.connected
                ? { label: "Odoo connecté", tone: "success" }
                : { label: "Odoo indisponible", tone: "danger" },
            );
          } else {
            setOdooStatus(null);
            setOdooBadge({ label: "Odoo indisponible", tone: "danger" });
          }
        } else {
          setOdooStatus(null);
          setOdooBadge({ label: "Odoo indisponible", tone: "danger" });
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
        setOdooStatus(null);
        setOdooBadge({ label: "Odoo indisponible", tone: "danger" });
      }
    }

    loadDashboard();
  }, []);

  const pendingApprovals = useMemo(() => {
    return approvals.filter((item) => item.status === "pending").length;
  }, [approvals]);

  return (
    <main className="dashboard-shell">
      <style>{`
        .dashboard-shell {
          min-height: 100vh;
          background:
            linear-gradient(180deg, #f8fafc 0%, #f3f6fa 100%);
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
          color: #ffffff;
          padding: 26px 20px 22px;
          display: flex;
          flex-direction: column;
          justify-content: space-between;
          border-right: 1px solid rgba(255, 255, 255, 0.08);
        }

        .brand {
          display: grid;
          grid-template-columns: 56px 1fr;
          align-items: center;
          column-gap: 12px;
        }

        .brand-mark {
          width: 56px;
          height: 56px;
          display: grid;
          place-items: center;
          border-radius: 8px;
          background: #ffffff;
        }

        .brand-logo {
          width: 48px;
          height: 48px;
          object-fit: contain;
          display: block;
        }

        .brand-kicker {
          margin: 0;
          color: #9ca3af;
          font-size: 12px;
          font-weight: 700;
          grid-column: 2;
        }

        .brand-title {
          margin: -2px 0 0;
          font-size: 20px;
          line-height: 1.15;
          font-weight: 800;
          letter-spacing: 0;
          grid-column: 2;
        }

        .sidebar-nav {
          margin-top: 30px;
          display: grid;
          gap: 6px;
        }

        .sidebar-link {
          color: #d1d5db;
          text-decoration: none;
          padding: 11px 12px;
          border-radius: 8px;
          font-size: 14px;
          font-weight: 700;
        }

        .sidebar-link:hover,
        .sidebar-link.active {
          background: rgba(255, 255, 255, 0.08);
          color: #ffffff;
        }

        .sidebar-footer {
          border-top: 1px solid rgba(255, 255, 255, 0.12);
          padding-top: 18px;
          color: #a7b0be;
          font-size: 12px;
          line-height: 1.7;
        }

        .logout-button {
          margin-top: 12px;
          min-height: 36px;
          width: 100%;
          border: 1px solid rgba(255, 255, 255, 0.22);
          border-radius: 8px;
          background: transparent;
          color: #ffffff;
          font-weight: 800;
          cursor: pointer;
        }

        .main {
          padding: 28px 34px;
          display: flex;
          align-items: flex-start;
        }

        .main-inner {
          width: 100%;
          max-width: 1120px;
          margin: 0 auto;
          display: grid;
          gap: 20px;
        }

        .header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          gap: 22px;
          min-height: 96px;
          padding: 22px 24px;
          margin-bottom: 2px;
          background: #ffffff;
          border: 1px solid #dfe5ed;
          border-radius: 10px;
          box-shadow: 0 14px 30px rgba(17, 24, 39, 0.05);
        }

        .header > div:first-child {
          min-width: 280px;
        }

        .page-title {
          margin: 0;
          color: #111827;
          font-size: 32px;
          line-height: 1.1;
          font-weight: 850;
          letter-spacing: 0;
        }

        .page-subtitle {
          margin: 9px 0 0;
          color: #667085;
          font-size: 15px;
          line-height: 1.45;
        }

        .header-actions {
          display: flex;
          align-items: center;
          justify-content: flex-end;
          gap: 9px;
          flex-wrap: wrap;
          max-width: 520px;
        }

        .status-badge {
          min-height: 38px;
          display: inline-flex;
          align-items: center;
          gap: 8px;
          padding: 0 13px;
          border-radius: 999px;
          font-size: 13px;
          font-weight: 800;
          white-space: nowrap;
        }

        .status-badge.success {
          color: #166534;
          background: #dcfce7;
          border: 1px solid #bbf7d0;
        }

        .status-badge.danger {
          color: #991b1b;
          background: #fee2e2;
          border: 1px solid #fecaca;
        }

        .status-badge.warning {
          color: #92400e;
          background: #fef3c7;
          border: 1px solid #fde68a;
        }

        .status-dot {
          width: 8px;
          height: 8px;
          border-radius: 999px;
          background: currentColor;
        }

        .button {
          min-height: 38px;
          display: inline-flex;
          align-items: center;
          justify-content: center;
          text-decoration: none;
          padding: 0 14px;
          border-radius: 8px;
          font-size: 13px;
          font-weight: 800;
          white-space: nowrap;
        }

        .button.primary {
          background: #111827;
          color: #ffffff;
          border: 1px solid #111827;
          box-shadow: 0 8px 18px rgba(17, 24, 39, 0.12);
        }

        .button.secondary {
          background: #ffffff;
          color: #111827;
          border: 1px solid #d9e0ea;
        }

        .button:hover {
          transform: translateY(-1px);
        }

        .stats {
          display: grid;
          grid-template-columns: repeat(3, minmax(0, 1fr));
          gap: 16px;
          margin: 0;
        }

        .stat-card,
        .action-card {
          background: #ffffff;
          border: 1px solid #dfe5ed;
          border-radius: 8px;
          box-shadow: 0 10px 24px rgba(17, 24, 39, 0.045);
        }

        .stat-card {
          min-height: 126px;
          padding: 22px;
          display: flex;
          flex-direction: column;
          justify-content: space-between;
        }

        .stat-label {
          margin: 0;
          color: #667085;
          font-size: 13px;
          font-weight: 750;
          line-height: 1.35;
        }

        .stat-value {
          margin: 0;
          color: #111827;
          font-size: 36px;
          line-height: 1;
          font-weight: 850;
          font-variant-numeric: tabular-nums;
        }

        .section-title {
          margin: 4px 0 12px;
          color: #111827;
          font-size: 18px;
          font-weight: 850;
        }

        .actions-grid {
          display: grid;
          grid-template-columns: repeat(4, minmax(0, 1fr));
          gap: 16px;
        }

        .action-card {
          min-height: 104px;
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 14px;
          padding: 18px 20px;
          color: inherit;
          text-decoration: none;
          transition:
            border-color 160ms ease,
            box-shadow 160ms ease,
            transform 160ms ease;
        }

        .action-card:hover {
          border-color: #b8c3d1;
          box-shadow: 0 16px 28px rgba(17, 24, 39, 0.08);
          transform: translateY(-2px);
        }

        .action-title {
          color: #111827;
          font-size: 16px;
          font-weight: 850;
        }

        .action-arrow {
          width: 30px;
          height: 30px;
          display: grid;
          place-items: center;
          border-radius: 999px;
          background: #f1f5f9;
          color: #667085;
          font-size: 18px;
          line-height: 1;
          transition:
            background 160ms ease,
            color 160ms ease,
            transform 160ms ease;
        }

        .action-card:hover .action-arrow {
          background: #111827;
          color: #ffffff;
          transform: translateX(2px);
        }

        @media (max-width: 980px) {
          .dashboard-layout {
            grid-template-columns: 1fr;
          }

          .sidebar {
            position: static;
            height: auto;
            display: block;
          }

          .sidebar-footer {
            margin-top: 24px;
          }

          .sidebar-nav {
            grid-template-columns: repeat(4, minmax(0, 1fr));
          }

          .main {
            min-height: auto;
          }
        }

        @media (max-width: 760px) {
          .main {
            padding: 22px;
          }

          .header {
            flex-direction: column;
            align-items: stretch;
            min-height: auto;
            padding: 20px;
          }

          .header-actions {
            justify-content: stretch;
            width: 100%;
            max-width: none;
          }

          .header-actions > * {
            flex: 1 1 auto;
          }

          .stats,
          .actions-grid,
          .sidebar-nav {
            grid-template-columns: 1fr;
          }

          .stat-card,
          .action-card {
            min-height: 96px;
          }
        }
      `}</style>

      <div className="dashboard-layout">
        <aside className="sidebar">
          <div>
            <div className="brand">
              <div className="brand-mark">
                <Image
                  className="brand-logo"
                  src="/jamain-baco-logo.png"
                  alt="Jamain Baco"
                  width={48}
                  height={48}
                />
              </div>
              <p className="brand-kicker">Jamain Baco</p>
              <h2 className="brand-title">Orchestrateur IA</h2>
            </div>

            <nav className="sidebar-nav">
              {actions.map((action) => (
                <Link
                  key={action.title}
                  className="sidebar-link"
                  href={action.href}
                >
                  {action.title}
                </Link>
              ))}
            </nav>
          </div>

          <div className="sidebar-footer">
            <span>{currentUser?.email || "Utilisateur connecté"}</span>
            <br />
            <span>Rôle : {getRoleLabel(currentUser)}</span>
            <button className="logout-button" type="button" onClick={handleLogout}>
              Se déconnecter
            </button>
          </div>
        </aside>

        <section className="main">
          <div className="main-inner">
            <header className="header">
              <div>
                <h1 className="page-title">Tableau de bord opérationnel</h1>
                <p className="page-subtitle">Supervision de l’orchestrateur IA.</p>
              </div>

              <div className="header-actions">
                <span className={`status-badge ${odooBadge.tone}`}>
                  <span className="status-dot" />
                  {odooBadge.label}
                </span>
                <Link href="/chat" className="button primary">
                  Ouvrir le chat
                </Link>
                <Link href="/odoo" className="button secondary">
                  Ouvrir Odoo
                </Link>
              </div>
            </header>

            <section className="stats">
              <StatCard label="Validations en attente" value={pendingApprovals} />
              <StatCard label="Événements d’audit" value={logs.length} />
              <StatCard label="Systèmes connectés" value={odooStatus?.connected ? 1 : 0} />
            </section>

            <section>
              <h3 className="section-title">Actions rapides</h3>
              <div className="actions-grid">
                {actions.map((action) => (
                  <Link
                    key={action.title}
                    href={action.href}
                    className="action-card"
                  >
                    <span className="action-title">{action.title}</span>
                    <span className="action-arrow">→</span>
                  </Link>
                ))}
              </div>
            </section>
          </div>
        </section>
      </div>
    </main>
  );
}

function StatCard({ label, value }: { label: string; value: number }) {
  return (
    <div className="stat-card">
      <p className="stat-label">{label}</p>
      <p className="stat-value">{value}</p>
    </div>
  );
}
