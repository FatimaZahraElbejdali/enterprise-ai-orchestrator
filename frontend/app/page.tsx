"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import AppShell from "@/components/AppShell";
import {
  API_BASE_URL,
  AuthUser,
  apiFetch,
  clearAuth,
  getDepartmentLabel,
  getRoleLabel,
  getStoredUser,
  requireAuth,
  validateAuthSession,
} from "@/lib/api";

type OdooStatus = {
  connected?: boolean;
  mode?: string;
};

type ApprovalItem = {
  status?: string;
  created_at?: string;
  [key: string]: unknown;
};

type AuditLog = {
  event_type?: string;
  title?: string;
  message?: string;
  status?: string;
  created_at?: string;
  timestamp?: string;
  [key: string]: unknown;
};

type OdooBadge = {
  label: "Odoo connecté" | "Odoo indisponible" | "Connexion requise" | "Session expirée";
  tone: "success" | "danger" | "warning";
};

type NavAction = {
  title: string;
  href: string;
  icon: IconName;
};

type IconName = "dashboard" | "chat" | "odoo" | "approval" | "logs" | "document" | "logout";

const actions: NavAction[] = [
  { title: "Tableau de bord", href: "/", icon: "dashboard" },
  { title: "Console de chat", href: "/chat", icon: "chat" },
  { title: "Odoo", href: "/odoo", icon: "odoo" },
  { title: "Validations", href: "/approvals", icon: "approval" },
  { title: "Journaux d’audit", href: "/logs", icon: "logs" },
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
    void validateAuthSession("/");

    async function loadDashboard() {
      try {
        const [odooRes, approvalsRes, logsRes] = await Promise.allSettled([
          apiFetch(`${API_BASE_URL}/odoo/status`, {
            cache: "no-store",
          }),
          apiFetch(`${API_BASE_URL}/approvals`, {
            cache: "no-store",
          }),
          apiFetch(`${API_BASE_URL}/logs`, {
            cache: "no-store",
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

  const todayApprovals = useMemo(() => countToday(approvals), [approvals]);
  const blockedActions = useMemo(() => countBlockedActions(logs), [logs]);
  const agentStates = [
    ["Agent Odoo", "Actif"],
    ["Agent Support", "Actif"],
    ["Agent Serveur", "Actif"],
    ["Agent Connaissance", "Actif"],
    ["Validation humaine", "Active"],
    ["Journal d’audit", "Actif"],
  ];
  const recentActivities = useMemo(() => {
    const logItems = logs.slice(0, 4).map((log) => ({
      label: activityLabel(log),
      time: relativeTime(log.created_at || log.timestamp),
      tone: activityTone(log),
    }));

    if (logItems.length > 0) return logItems;

    return [
      {
        label: odooStatus?.connected ? "Connexion Odoo active" : "Connexion Odoo indisponible",
        time: "maintenant",
        tone: odooStatus?.connected ? "ok" : "err",
      },
      {
        label: `${pendingApprovals} validation${pendingApprovals > 1 ? "s" : ""} en attente`,
        time: "chargé",
        tone: pendingApprovals > 0 ? "warn" : "ok",
      },
      {
        label: "Session tableau de bord ouverte",
        time: "maintenant",
        tone: "info",
      },
    ];
  }, [logs, odooStatus?.connected, pendingApprovals]);

  return (
    <AppShell
      active="dashboard"
      eyebrow="Tableau de bord"
      title="Tableau de bord opérationnel"
      subtitle="Supervision des validations, systèmes connectés et journaux de l’orchestrateur."
      badges={[{ label: odooBadge.label, tone: odooBadge.tone }]}
      actions={
        <>
          <Link href="/chat" className="app-button primary">
            Ouvrir la console
          </Link>
          <Link href="/odoo" className="app-button">
            Odoo
          </Link>
        </>
      }
    >
      <style>{`
        .dashboard-page {
          --brand-blue: #123f8c;
          --brand-blue-mid: #1d5fc3;
          --brand-blue-soft: #e9f0fb;
          --brand-blue-xsoft: #f5f8fd;
          --brand-border: #d7deea;
          --sidebar-bg: #0f1b2d;
          --sidebar-panel: #14223a;
          --sidebar-border: #243653;
          --sidebar-muted: #8da0bd;
          --surface: #ffffff;
          --page-bg: #f4f6f9;
          --text-strong: #191a3d;
          --text-muted: #5e6090;
          --text-faint: #989ac0;
          --red: #d94040;
          --red-bg: #fdeceb;
          --green: #159862;
          --green-bg: #e6f7f0;
          --amber: #bf760c;
          --amber-bg: #fff2dc;
          min-height: 100vh;
          background: var(--page-bg);
          color: var(--text-strong);
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
          background: var(--sidebar-bg);
          border-right: 1px solid var(--sidebar-border);
          display: flex;
          flex-direction: column;
        }

        .brand {
          min-height: 94px;
          display: flex;
          align-items: center;
          gap: 12px;
          padding: 20px 18px;
          border-bottom: 1px solid var(--sidebar-border);
        }

        .brand-mark {
          width: 52px;
          height: 52px;
          border-radius: 10px;
          display: grid;
          place-items: center;
          background: #ffffff;
          overflow: hidden;
          flex: 0 0 auto;
        }

        .brand-logo {
          width: 52px;
          height: 52px;
          object-fit: contain;
          display: block;
        }

        .brand-name {
          margin: 0;
          color: #f7fbff;
          font-size: 14px;
          font-weight: 800;
          line-height: 1.15;
        }

        .brand-subtitle {
          margin: 3px 0 0;
          color: var(--sidebar-muted);
          font-size: 12px;
          font-weight: 650;
        }

        .sidebar-nav {
          flex: 1;
          padding: 18px 12px;
        }

        .nav-label,
        .section-label {
          color: var(--sidebar-muted);
          font-size: 11px;
          font-weight: 800;
          letter-spacing: 0.12em;
          text-transform: uppercase;
        }

        .nav-label {
          padding: 0 10px 10px;
        }

        .nav-list {
          display: grid;
          gap: 6px;
        }

        .nav-item {
          min-height: 40px;
          display: flex;
          align-items: center;
          gap: 11px;
          padding: 9px 11px;
          border-radius: 10px;
          color: #c8d4e8;
          text-decoration: none;
          font-size: 14px;
          font-weight: 750;
          transition: background 160ms ease, color 160ms ease;
        }

        .nav-item svg {
          color: var(--sidebar-muted);
          flex: 0 0 auto;
          transition: color 160ms ease;
        }

        .nav-item:hover {
          background: var(--sidebar-panel);
          color: #ffffff;
        }

        .nav-item:hover svg,
        .nav-item.active svg {
          color: var(--brand-blue);
        }

        .nav-item.active {
          background: rgba(29, 95, 195, 0.18);
          color: #9fc2ff;
        }

        .sidebar-footer {
          padding: 14px 12px 18px;
          border-top: 1px solid var(--sidebar-border);
        }

        .user-card {
          min-width: 0;
          display: grid;
          grid-template-columns: 34px minmax(0, 1fr);
          align-items: start;
          gap: 10px;
          padding: 10px;
          border-radius: 10px;
        }

        .avatar {
          width: 34px;
          height: 34px;
          border-radius: 999px;
          display: grid;
          place-items: center;
          background: var(--brand-blue);
          color: #ffffff;
          font-size: 13px;
          font-weight: 850;
          position: relative;
          flex: 0 0 auto;
        }

        .avatar::after {
          content: "";
          position: absolute;
          right: 0;
          bottom: 1px;
          width: 9px;
          height: 9px;
          border-radius: 999px;
          background: var(--green);
          border: 2px solid var(--surface);
        }

        .user-info {
          min-width: 0;
          flex: 1;
        }

        .user-email {
          overflow-wrap: anywhere;
          color: #ffffff;
          font-size: 12px;
          font-weight: 800;
          line-height: 1.25;
        }

        .user-role {
          margin-top: 2px;
          color: var(--sidebar-muted);
          font-size: 11px;
          line-height: 1.35;
        }

        .logout-button {
          grid-column: 1 / -1;
          width: 100%;
          min-height: 38px;
          border: 1px solid var(--sidebar-border);
          border-radius: 10px;
          background: #ffffff;
          color: var(--brand-blue);
          cursor: pointer;
          display: inline-flex;
          align-items: center;
          justify-content: center;
          gap: 8px;
          padding: 9px 12px;
          font-size: 12px;
          font-weight: 850;
          transition: color 160ms ease, background 160ms ease;
        }

        .logout-button:hover {
          background: var(--red-bg);
          color: var(--red);
          border-color: rgba(217, 64, 64, 0.28);
        }

        .main {
          min-width: 0;
          display: flex;
          flex-direction: column;
        }

        .hero {
          position: relative;
          overflow: hidden;
          background: var(--brand-blue);
          padding: 34px 42px 36px;
        }

        .hero-inner {
          position: relative;
          z-index: 1;
          max-width: 1220px;
        }

        .hero-eyebrow {
          color: rgba(255, 255, 255, 0.42);
          font-size: 11px;
          font-weight: 850;
          letter-spacing: 0.16em;
          text-transform: uppercase;
        }

        .hero-title {
          margin: 10px 0 16px;
          color: #ffffff;
          font-size: 34px;
          line-height: 1.08;
          letter-spacing: -0.02em;
          font-weight: 900;
        }

        .hero-actions {
          display: flex;
          align-items: center;
          gap: 10px;
          flex-wrap: wrap;
        }

        .button,
        .status-badge {
          min-height: 44px;
          display: inline-flex;
          align-items: center;
          justify-content: center;
          gap: 8px;
          border-radius: 11px;
          padding: 0 18px;
          font-size: 14px;
          font-weight: 850;
          text-decoration: none;
          transition: transform 160ms ease, box-shadow 160ms ease, background 160ms ease;
        }

        .button:hover {
          transform: translateY(-1px);
        }

        .button.primary {
          background: #ffffff;
          color: var(--brand-blue);
          box-shadow: 0 12px 24px rgba(12, 13, 65, 0.18);
        }

        .button.primary:hover {
          background: var(--brand-blue-xsoft);
          box-shadow: 0 16px 30px rgba(12, 13, 65, 0.22);
        }

        .button.secondary {
          background: transparent;
          color: #ffffff;
          border: 1.5px solid rgba(255, 255, 255, 0.18);
        }

        .button.secondary:hover {
          background: rgba(255, 255, 255, 0.08);
        }

        .status-badge {
          min-height: 38px;
          border-radius: 999px;
          padding: 0 15px;
          font-size: 13px;
        }

        .status-badge.success {
          color: #86efac;
          background: rgba(21, 152, 98, 0.15);
          border: 1px solid rgba(21, 152, 98, 0.34);
        }

        .status-badge.danger {
          color: #ff8a8a;
          background: rgba(217, 64, 64, 0.15);
          border: 1px solid rgba(217, 64, 64, 0.34);
        }

        .status-badge.warning {
          color: #ffd28a;
          background: rgba(191, 118, 12, 0.16);
          border: 1px solid rgba(191, 118, 12, 0.34);
        }

        .status-dot {
          width: 8px;
          height: 8px;
          border-radius: 999px;
          background: currentColor;
        }

        .content {
          flex: 1;
          padding: 30px 42px 44px;
          overflow-y: auto;
        }

        .content-inner {
          max-width: 1220px;
          display: grid;
          gap: 28px;
        }

        .section-label {
          margin-bottom: 14px;
        }

        .stat-grid {
          display: grid;
          grid-template-columns: repeat(4, minmax(0, 1fr));
          gap: 16px;
        }

        .stat-card,
        .panel {
          background: var(--surface);
          border: 1px solid var(--brand-border);
          border-radius: 16px;
          box-shadow: 0 12px 28px rgba(40, 41, 143, 0.06);
        }

        .stat-card {
          min-height: 150px;
          padding: 22px;
          position: relative;
          overflow: hidden;
          display: flex;
          flex-direction: column;
          justify-content: space-between;
          transition: transform 180ms ease, box-shadow 180ms ease;
        }

        .stat-card:hover {
          transform: translateY(-2px);
          box-shadow: 0 18px 34px rgba(40, 41, 143, 0.1);
        }

        .stat-card::before {
          content: "";
          position: absolute;
          top: 0;
          left: 0;
          right: 0;
          height: 3px;
          background: var(--card-accent, var(--brand-blue));
        }

        .stat-card.warn { --card-accent: var(--amber); }
        .stat-card.ok { --card-accent: var(--green); }
        .stat-card.err { --card-accent: var(--red); }

        .stat-header {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 14px;
        }

        .stat-label {
          margin: 0;
          color: var(--text-muted);
          font-size: 14px;
          font-weight: 850;
        }

        .stat-icon {
          width: 34px;
          height: 34px;
          display: grid;
          place-items: center;
          border-radius: 10px;
        }

        .stat-icon.warn { color: var(--amber); background: var(--amber-bg); }
        .stat-icon.ok { color: var(--green); background: var(--green-bg); }
        .stat-icon.err { color: var(--red); background: var(--red-bg); }

        .stat-value {
          margin: 4px 0 0;
          color: var(--text-strong);
          font-size: 42px;
          line-height: 1;
          font-weight: 900;
          letter-spacing: -0.04em;
          font-variant-numeric: tabular-nums;
        }

        .stat-footer {
          display: flex;
          align-items: center;
          gap: 8px;
          flex-wrap: wrap;
        }

        .stat-tag {
          display: inline-flex;
          align-items: center;
          min-height: 24px;
          padding: 0 10px;
          border-radius: 999px;
          font-size: 12px;
          font-weight: 850;
        }

        .stat-tag.warn { color: var(--amber); background: var(--amber-bg); }
        .stat-tag.ok { color: var(--green); background: var(--green-bg); }
        .stat-tag.err { color: var(--red); background: var(--red-bg); }

        .stat-sub {
          color: var(--text-faint);
          font-size: 13px;
          font-weight: 650;
        }

        .dashboard-bottom {
          display: grid;
          grid-template-columns: minmax(0, 1fr) minmax(320px, 360px);
          gap: 18px;
          align-items: start;
        }

        .recent-panel {
          grid-column: 2;
        }

        .agents-panel {
          grid-column: 1;
        }

        .panel {
          overflow: hidden;
        }

        .panel-header {
          min-height: 58px;
          padding: 16px 20px;
          border-bottom: 1px solid var(--brand-border);
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 14px;
        }

        .panel-title {
          color: var(--text-strong);
          font-size: 15px;
          font-weight: 900;
        }

        .panel-link {
          color: var(--brand-blue);
          font-size: 13px;
          font-weight: 850;
          text-decoration: none;
        }

        .feed-list {
          padding: 0;
        }

        .feed-item {
          display: flex;
          gap: 12px;
          padding: 14px 20px;
          border-bottom: 1px solid var(--brand-border);
          transition: background 160ms ease;
        }

        .feed-item:last-child {
          border-bottom: 0;
        }

        .feed-item:hover {
          background: var(--brand-blue-xsoft);
        }

        .feed-pip {
          width: 8px;
          height: 8px;
          border-radius: 999px;
          flex: 0 0 auto;
          margin-top: 6px;
        }

        .feed-pip.warn { background: var(--amber); }
        .feed-pip.err { background: var(--red); }
        .feed-pip.ok { background: var(--green); }
        .feed-pip.info { background: var(--text-faint); }

        .feed-body {
          min-width: 0;
        }

        .feed-msg {
          color: var(--text-strong);
          font-size: 14px;
          font-weight: 750;
          line-height: 1.35;
        }

        .feed-time {
          margin-top: 3px;
          color: var(--text-faint);
          font-size: 12px;
          font-weight: 700;
        }

        .agent-grid {
          display: grid;
          grid-template-columns: repeat(2, minmax(0, 1fr));
          gap: 0;
          padding: 6px 20px 18px;
        }

        .agent-row {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 12px;
          min-height: 46px;
          border-bottom: 1px solid var(--brand-border);
          padding: 0 12px 0 0;
          color: var(--text-strong);
          font-size: 14px;
          font-weight: 760;
        }

        .agent-row:nth-last-child(-n + 2) {
          border-bottom: 0;
        }

        .agent-status {
          display: inline-flex;
          align-items: center;
          gap: 7px;
          color: var(--green);
          font-size: 12px;
          font-weight: 850;
          white-space: nowrap;
        }

        .agent-status::before {
          content: "";
          width: 7px;
          height: 7px;
          border-radius: 999px;
          background: currentColor;
        }

        @media (max-width: 1040px) {
          .dashboard-layout {
            grid-template-columns: 1fr;
          }

          .sidebar {
            position: static;
            height: auto;
          }

          .sidebar-nav {
            padding-bottom: 10px;
          }

          .nav-list {
            grid-template-columns: repeat(5, minmax(0, 1fr));
          }

          .sidebar-footer {
            padding-top: 8px;
          }

	          .dashboard-bottom {
	            grid-template-columns: 1fr;
	          }

	          .recent-panel {
	            grid-column: auto;
	          }

          .agents-panel {
            grid-column: auto;
          }
        }

        @media (max-width: 780px) {
          .hero,
          .content {
            padding-left: 22px;
            padding-right: 22px;
          }

          .hero-title {
            font-size: 28px;
          }

          .hero-actions {
            align-items: stretch;
          }

          .hero-actions > * {
            flex: 1 1 180px;
          }

	          .stat-grid,
          .agent-grid,
	          .nav-list {
	            grid-template-columns: 1fr;
	          }
        }
      `}</style>

      <div className="dashboard-page">
              <section>
                <div className="section-label">Métriques clés</div>
                <div className="stat-grid">
                  <StatCard
                    label="Validations en attente"
                    value={pendingApprovals}
                    tone="warn"
                    icon="approval"
                    tag={pendingApprovals > 0 ? "Action requise" : "À jour"}
                    sub={`${todayApprovals} ajoutée${todayApprovals > 1 ? "s" : ""} aujourd’hui`}
                  />
                  <StatCard
                    label="Événements d’audit"
                    value={logs.length}
                    tone="ok"
                    icon="document"
                    tag="Normal"
                    sub="Journal actif"
                  />
                  <StatCard
                    label="Systèmes connectés"
                    value={odooStatus?.connected ? 1 : 0}
                    tone={odooStatus?.connected ? "ok" : "err"}
                    icon="odoo"
                    tag={odooStatus?.connected ? "En ligne" : "Hors ligne"}
                    sub={odooStatus?.connected ? "Odoo accessible" : "Odoo inaccessible"}
                  />
                  <StatCard
                    label="Actions bloquées"
                    value={blockedActions}
                    tone={blockedActions > 0 ? "err" : "ok"}
                    icon="approval"
                    tag={blockedActions > 0 ? "Surveillé" : "Aucune alerte"}
                    sub="Politique de sécurité"
                  />
                </div>
              </section>

              <section className="dashboard-bottom">
                <div className="panel agents-panel">
                  <div className="panel-header">
                    <div>
                      <div className="panel-title">État des agents</div>
                      <div className="stat-sub">Modules configurés dans l’orchestrateur</div>
                    </div>
                  </div>
                  <div className="agent-grid">
                    {agentStates.map(([label, state]) => (
                      <div className="agent-row" key={label}>
                        <span>{label}</span>
                        <span className="agent-status">{state}</span>
                      </div>
                    ))}
                  </div>
                </div>
                <div className="panel recent-panel">
                  <div className="panel-header">
                    <div className="panel-title">Activité récente</div>
                    <Link className="panel-link" href="/logs">
                      Voir tout →
                    </Link>
                  </div>
                  <div className="feed-list">
                    {recentActivities.map((activity, index) => (
                      <div className="feed-item" key={`${activity.label}-${index}`}>
                        <span className={`feed-pip ${activity.tone}`} />
                        <span className="feed-body">
                          <span className="feed-msg">{activity.label}</span>
                          <span className="feed-time">{activity.time}</span>
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              </section>
      </div>
    </AppShell>
  );
}

function StatCard({
  label,
  value,
  tone,
  icon,
  tag,
  sub,
}: {
  label: string;
  value: number;
  tone: "warn" | "ok" | "err";
  icon: IconName;
  tag: string;
  sub: string;
}) {
  return (
    <div className={`stat-card ${tone}`}>
      <div className="stat-header">
        <p className="stat-label">{label}</p>
        <span className={`stat-icon ${tone}`}>
          <Icon name={icon} size={17} />
        </span>
      </div>
      <p className="stat-value">{formatNumber(value)}</p>
      <div className="stat-footer">
        <span className={`stat-tag ${tone}`}>{tag}</span>
        <span className="stat-sub">{sub}</span>
      </div>
    </div>
  );
}

function Icon({ name, size = 16 }: { name: IconName; size?: number }) {
  const common = {
    width: size,
    height: size,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.9,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    "aria-hidden": true,
  };

  if (name === "dashboard") {
    return (
      <svg {...common}>
        <rect x="3" y="3" width="7" height="7" rx="1.5" />
        <rect x="14" y="3" width="7" height="7" rx="1.5" />
        <rect x="3" y="14" width="7" height="7" rx="1.5" />
        <rect x="14" y="14" width="7" height="7" rx="1.5" />
      </svg>
    );
  }

  if (name === "chat") {
    return (
      <svg {...common}>
        <path d="M21 15a2 2 0 0 1-2 2H8l-5 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
      </svg>
    );
  }

  if (name === "odoo") {
    return (
      <svg {...common}>
        <circle cx="12" cy="12" r="3" />
        <path d="M12 2v3" />
        <path d="M12 19v3" />
        <path d="m4.93 4.93 2.12 2.12" />
        <path d="m16.95 16.95 2.12 2.12" />
        <path d="M2 12h3" />
        <path d="M19 12h3" />
        <path d="m4.93 19.07 2.12-2.12" />
        <path d="m16.95 7.05 2.12-2.12" />
      </svg>
    );
  }

  if (name === "approval") {
    return (
      <svg {...common}>
        <path d="M9 12l2 2 4-4" />
        <circle cx="12" cy="12" r="9" />
      </svg>
    );
  }

  if (name === "document") {
    return (
      <svg {...common}>
        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
        <path d="M14 2v6h6" />
        <path d="M16 13H8" />
        <path d="M16 17H8" />
      </svg>
    );
  }

  if (name === "logout") {
    return (
      <svg {...common}>
        <path d="M10 17l5-5-5-5" />
        <path d="M15 12H3" />
        <path d="M21 3v18" />
      </svg>
    );
  }

  return (
    <svg {...common}>
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <path d="M14 2v6h6" />
      <path d="M12 18v-6" />
      <path d="m9 15 3 3 3-3" />
    </svg>
  );
}

function userInitial(user: AuthUser | null) {
  const source = user?.email || user?.role_label || "U";
  return source.trim().charAt(0).toUpperCase() || "U";
}

function countToday(items: ApprovalItem[]) {
  const today = new Date().toISOString().slice(0, 10);
  return items.filter((item) => {
    const createdAt = typeof item.created_at === "string" ? item.created_at : "";
    return createdAt.startsWith(today);
  }).length;
}

function activityLabel(log: AuditLog) {
  const title = stringValue(log.title);
  const message = stringValue(log.message);
  const eventType = stringValue(log.event_type);

  if (title) return displayAuditLabel(title);
  if (message) return displayAuditLabel(message);
  if (eventType) return displayAuditLabel(eventType);
  return "Événement d’audit enregistré";
}

function activityTone(log: AuditLog): "warn" | "ok" | "err" | "info" {
  const value = `${stringValue(log.status)} ${stringValue(log.event_type)}`.toLowerCase();

  if (value.includes("error") || value.includes("failed") || value.includes("denied") || value.includes("blocked")) {
    return "err";
  }

  if (value.includes("pending") || value.includes("approval")) {
    return "warn";
  }

  if (value.includes("completed") || value.includes("success") || value.includes("read")) {
    return "ok";
  }

  return "info";
}

function relativeTime(value?: string) {
  if (!value) return "récemment";

  const timestamp = new Date(value).getTime();

  if (Number.isNaN(timestamp)) return "récemment";

  const diffMs = Date.now() - timestamp;
  const minute = 60 * 1000;
  const hour = 60 * minute;
  const day = 24 * hour;

  if (diffMs < minute) return "à l’instant";
  if (diffMs < hour) return `il y a ${Math.max(1, Math.floor(diffMs / minute))} min`;
  if (diffMs < day) return `il y a ${Math.floor(diffMs / hour)} h`;
  return `il y a ${Math.floor(diffMs / day)} j`;
}

function formatNumber(value: number) {
  return new Intl.NumberFormat("fr-FR").format(value);
}

function countBlockedActions(logs: AuditLog[]) {
  return logs.filter((log) => {
    const status = stringValue(log.status).toLowerCase();
    const eventType = stringValue(log.event_type).toLowerCase();
    return (
      status.includes("blocked") ||
      status.includes("denied") ||
      eventType.includes("permission_denied") ||
      eventType.includes("unsupported_action")
    );
  }).length;
}

function displayAuditLabel(value: string) {
  const normalized = value.trim();
  const labels: Record<string, string> = {
    answer_question: "Question répondue",
    odoo_read: "Lecture Odoo",
    approval_required: "Validation requise",
    permission_denied: "Accès refusé",
    unsupported_action: "Action non prise en charge",
    official_web_ingestion: "Ingestion site officiel",
    ai_model_call: "Appel modèle IA",
  };

  return labels[normalized] || normalized.replaceAll("_", " ");
}

function stringValue(value: unknown) {
  return typeof value === "string" ? value : "";
}
