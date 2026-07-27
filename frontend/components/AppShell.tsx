"use client";

import Image from "next/image";
import Link from "next/link";
import { ReactNode } from "react";
import {
  AuthUser,
  clearAuth,
  getDepartmentLabel,
  getRoleLabel,
  getStoredUser,
  hasAnyPermission,
} from "@/lib/api";

type ActiveRoute = "dashboard" | "chat" | "odoo" | "approvals" | "logs";
type BadgeTone = "success" | "warning" | "danger" | "neutral";

type HeaderBadge = {
  label: string;
  tone?: BadgeTone;
};

type AppShellProps = {
  active: ActiveRoute;
  eyebrow?: string;
  title: string;
  subtitle?: string;
  badges?: HeaderBadge[];
  actions?: ReactNode;
  children: ReactNode;
  contentClassName?: string;
};

type NavigationItem = {
  key: ActiveRoute;
  label: string;
  href: string;
  icon: string;
  permissions?: string[];
};

const navigationItems: NavigationItem[] = [
  { key: "dashboard", label: "Tableau de bord", href: "/", icon: "□" },
  { key: "chat", label: "Console IA", href: "/chat", icon: "▱" },
  { key: "odoo", label: "Intégration Odoo", href: "/odoo", icon: "▭" },
  {
    key: "approvals",
    label: "Validations",
    href: "/approvals",
    icon: "✓",
    permissions: ["all", "view_approvals", "approve_odoo_actions"],
  },
  {
    key: "logs",
    label: "Journaux d’audit",
    href: "/logs",
    icon: "≡",
    permissions: ["all", "view_audit_logs"],
  },
];

export default function AppShell({
  active,
  eyebrow,
  title,
  subtitle,
  badges = [],
  actions,
  children,
  contentClassName = "",
}: AppShellProps) {
  const currentUser = getStoredUser();
  const visibleNavigation = navigationItems.filter((item) =>
    item.permissions ? hasAnyPermission(currentUser, item.permissions) : true,
  );

  function handleLogout() {
    clearAuth();
    window.location.href = "/login";
  }

  return (
    <>
      <main className={`app-shell ${contentClassName}`}>
        <aside className="app-sidebar">
          <div>
            <div className="app-brand">
              <div className="app-brand-mark">
                <Image
                  className="app-brand-logo"
                  src="/jamain-baco-logo.png"
                  alt="Jamain Baco"
                  width={56}
                  height={56}
                  priority
                />
              </div>
              <div>
                <p className="app-brand-name">Jamain Baco</p>
                <p className="app-brand-subtitle">Orchestrateur IA</p>
              </div>
            </div>

            <nav className="app-nav" aria-label="Navigation principale">
              <p className="app-nav-label">Navigation</p>
              {visibleNavigation.map((item) => (
                <Link
                  className={`app-nav-item ${active === item.key ? "active" : ""}`}
                  href={item.href}
                  key={item.key}
                >
                  <span className="app-nav-icon" aria-hidden="true">
                    {item.icon}
                  </span>
                  <span>{item.label}</span>
                </Link>
              ))}
            </nav>
          </div>

          <div className="app-sidebar-footer">
            <div className="app-user-summary">
              <div className="app-user-avatar" aria-hidden="true">
                {userInitial(currentUser)}
              </div>
              <div>
                <p className="app-user-email">
                  {currentUser?.email || "Utilisateur connecté"}
                </p>
                <p className="app-user-meta">{getRoleLabel(currentUser)}</p>
                <p className="app-user-meta">{getDepartmentLabel(currentUser)}</p>
              </div>
            </div>
            <button className="app-logout-button" type="button" onClick={handleLogout}>
              <span aria-hidden="true">↗</span>
              Se déconnecter
            </button>
          </div>
        </aside>

        <section className="app-workspace">
          <header className="app-page-header">
            <div>
              {eyebrow && <p className="app-eyebrow">{eyebrow}</p>}
              <h1>{title}</h1>
              {subtitle && <p className="app-subtitle">{subtitle}</p>}
            </div>

            {(badges.length > 0 || actions) && (
              <div className="app-header-actions">
                {badges.map((badge) => (
                  <span
                    className={`app-status-badge ${badge.tone || "neutral"}`}
                    key={badge.label}
                  >
                    <span className="app-status-dot" />
                    {badge.label}
                  </span>
                ))}
                {actions}
              </div>
            )}
          </header>

          <div className="app-page-body">{children}</div>
        </section>
      </main>

      <style jsx global>{`
        .app-shell {
          --app-navy: #0f1b2d;
          --app-navy-border: #223450;
          --app-blue: #123f8c;
          --app-workspace: #f4f6f8;
          --app-border: #d9dee8;
          --app-text: #172033;
          --app-success: #168a4a;
          --app-warning: #b76b08;
          --app-danger: #c92a2a;
          display: grid;
          grid-template-columns: 260px minmax(0, 1fr);
          min-height: 100vh;
          background: var(--app-workspace);
          color: var(--app-text);
          font-family: Inter, ui-sans-serif, system-ui, -apple-system,
            BlinkMacSystemFont, "Segoe UI", sans-serif;
        }

        .app-sidebar {
          position: sticky;
          top: 0;
          height: 100vh;
          display: flex;
          flex-direction: column;
          justify-content: space-between;
          background: var(--app-navy);
          border-right: 1px solid var(--app-navy-border);
          color: #dbe4f0;
        }

        .app-brand {
          min-height: 96px;
          display: flex;
          align-items: center;
          gap: 14px;
          padding: 22px 20px;
          border-bottom: 1px solid var(--app-navy-border);
        }

        .app-brand-mark {
          width: 58px;
          height: 58px;
          display: grid;
          place-items: center;
          overflow: hidden;
          flex: 0 0 auto;
        }

        .app-brand-logo {
          width: 58px;
          height: 58px;
          object-fit: contain;
          display: block;
        }

        .app-brand-name {
          margin: 0;
          color: #ffffff;
          font-weight: 800;
          font-size: 18px;
          line-height: 1.2;
        }

        .app-brand-subtitle {
          margin: 4px 0 0;
          color: #7f90ab;
          font-weight: 700;
          font-size: 14px;
        }

        .app-nav {
          display: grid;
          gap: 6px;
          padding: 24px 16px;
        }

        .app-nav-label {
          margin: 0 0 10px 4px;
          color: #7f90ab;
          text-transform: uppercase;
          letter-spacing: 0.12em;
          font-size: 12px;
          font-weight: 800;
        }

        .app-nav-item {
          display: flex;
          align-items: center;
          gap: 12px;
          min-height: 44px;
          padding: 11px 12px;
          border-radius: 8px;
          color: #91a2bd;
          text-decoration: none;
          font-weight: 700;
        }

        .app-nav-item:hover {
          background: rgba(255, 255, 255, 0.05);
          color: #d8e5f6;
        }

        .app-nav-item.active {
          background: #12294a;
          color: #83b8ff;
          border-left: 3px solid #2f7be5;
          padding-left: 9px;
        }

        .app-nav-icon {
          width: 18px;
          display: inline-flex;
          justify-content: center;
          color: currentColor;
          font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
        }

        .app-sidebar-footer {
          padding: 18px 16px 20px;
          border-top: 1px solid var(--app-navy-border);
        }

        .app-user-summary {
          display: grid;
          grid-template-columns: 38px minmax(0, 1fr);
          gap: 12px;
          align-items: center;
          margin-bottom: 14px;
        }

        .app-user-avatar {
          width: 38px;
          height: 38px;
          border-radius: 999px;
          display: grid;
          place-items: center;
          background: #17395f;
          color: #a7d2ff;
          border: 1px solid #244667;
          font-weight: 800;
        }

        .app-user-email,
        .app-user-meta {
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }

        .app-user-email {
          margin: 0;
          color: #ffffff;
          font-size: 13px;
          font-weight: 800;
        }

        .app-user-meta {
          margin: 2px 0 0;
          color: #8190aa;
          font-size: 12px;
          font-weight: 650;
        }

        .app-logout-button {
          width: 100%;
          display: inline-flex;
          align-items: center;
          justify-content: center;
          gap: 8px;
          min-height: 42px;
          border: 1px solid #2c3f5e;
          border-radius: 8px;
          background: #111f34;
          color: #c8d5e8;
          cursor: pointer;
          font-weight: 800;
        }

        .app-logout-button:hover {
          background: #172941;
          color: #ffffff;
        }

        .app-workspace {
          min-width: 0;
          min-height: 100vh;
          display: flex;
          flex-direction: column;
          background: var(--app-workspace);
        }

        .app-page-header {
          min-height: 84px;
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 24px;
          padding: 18px 32px;
          background: #ffffff;
          border-bottom: 1px solid var(--app-border);
        }

        .app-page-header h1 {
          margin: 0;
          color: #172033;
          font-size: 24px;
          line-height: 1.2;
          font-weight: 850;
        }

        .app-eyebrow {
          margin: 0 0 4px;
          color: #8b95a7;
          text-transform: uppercase;
          letter-spacing: 0.12em;
          font-size: 12px;
          font-weight: 800;
        }

        .app-subtitle {
          margin: 7px 0 0;
          max-width: 760px;
          color: #667085;
          font-size: 15px;
          line-height: 1.5;
        }

        .app-header-actions {
          display: flex;
          align-items: center;
          justify-content: flex-end;
          gap: 10px;
          flex-wrap: wrap;
        }

        .app-status-badge {
          min-height: 34px;
          display: inline-flex;
          align-items: center;
          gap: 8px;
          border: 1px solid var(--app-border);
          border-radius: 999px;
          background: #ffffff;
          color: #475467;
          padding: 7px 12px;
          font-size: 13px;
          font-weight: 800;
          white-space: nowrap;
        }

        .app-status-badge.success {
          color: var(--app-success);
          border-color: #bde7d0;
          background: #f0fbf5;
        }

        .app-status-badge.warning {
          color: var(--app-warning);
          border-color: #f6d69f;
          background: #fff8eb;
        }

        .app-status-badge.danger {
          color: var(--app-danger);
          border-color: #fac5c5;
          background: #fff2f2;
        }

        .app-status-badge.neutral {
          color: #475467;
          background: #f8fafc;
        }

        .app-status-dot {
          width: 8px;
          height: 8px;
          border-radius: 999px;
          background: currentColor;
        }

        .app-page-body {
          flex: 1;
          min-width: 0;
          padding: 28px 32px 40px;
        }

        .app-button {
          display: inline-flex;
          align-items: center;
          justify-content: center;
          gap: 8px;
          min-height: 38px;
          border: 1px solid #cfd8e6;
          border-radius: 8px;
          background: #ffffff;
          color: var(--app-blue);
          padding: 8px 14px;
          text-decoration: none;
          font-size: 14px;
          font-weight: 800;
        }

        .app-button.primary {
          border-color: var(--app-blue);
          background: var(--app-blue);
          color: #ffffff;
        }

        .app-button:hover {
          border-color: var(--app-blue);
        }

        @media (max-width: 900px) {
          .app-shell {
            grid-template-columns: 1fr;
          }

          .app-sidebar {
            position: static;
            height: auto;
          }

          .app-brand {
            min-height: auto;
          }

          .app-nav {
            grid-template-columns: repeat(2, minmax(0, 1fr));
            padding-top: 14px;
          }

          .app-nav-label {
            grid-column: 1 / -1;
          }

          .app-page-header {
            align-items: flex-start;
            flex-direction: column;
            padding: 20px;
          }

          .app-header-actions {
            justify-content: flex-start;
          }

          .app-page-body {
            padding: 20px;
          }
        }
      `}</style>
    </>
  );
}

function userInitial(user: AuthUser | null) {
  const source = user?.email || user?.role_label || "U";
  return source.trim().charAt(0).toUpperCase();
}
