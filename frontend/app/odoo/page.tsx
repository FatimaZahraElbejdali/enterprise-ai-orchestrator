"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import AppShell from "@/components/AppShell";
import {
  API_ERROR_MESSAGE,
  API_BASE_URL,
  AuthUser,
  BACKEND_UNREACHABLE_MESSAGE,
  apiFetch,
  clearAuth,
  getDepartmentLabel,
  getRoleLabel,
  getStoredUser,
  hasAnyPermission,
  requireAuth,
  validateAuthSession,
} from "@/lib/api";

type OdooStatus = {
  connected?: boolean;
  mode?: string;
};

type ProductResult = {
  source?: string;
  product?: string;
  product_id?: number | string;
  internal_reference?: string;
  stock_quantity?: number;
  forecast_quantity?: number;
  sale_price?: number;
  unit?: string;
  warehouse?: string;
  found?: boolean;
};

export default function OdooPage() {
  const [status, setStatus] = useState<OdooStatus | null>(null);
  const [productName, setProductName] = useState("BACO CLEAN");
  const [product, setProduct] = useState<ProductResult | null>(null);
  const [loadingStatus, setLoadingStatus] = useState(true);
  const [loadingProduct, setLoadingProduct] = useState(false);
  const [error, setError] = useState("");
  const [currentUser] = useState<AuthUser | null>(() => getStoredUser());

  function handleLogout() {
    clearAuth();
    window.location.href = "/login";
  }

  async function loadStatus() {
    setLoadingStatus(true);

    try {
      const res = await apiFetch(`${API_BASE_URL}/odoo/status`, {
        cache: "no-store",
      });

      if (res.ok) {
        setStatus(await res.json());
      } else {
        setError(API_ERROR_MESSAGE);
      }
    } finally {
      setLoadingStatus(false);
    }
  }

  async function searchProduct(event?: FormEvent) {
    event?.preventDefault();

    const cleanName = productName.trim();

    if (!cleanName) return;

    setLoadingProduct(true);
    setError("");
    setProduct(null);

    try {
      const res = await apiFetch(
        `${API_BASE_URL}/odoo/stock/${encodeURIComponent(cleanName)}`,
        {
          cache: "no-store",
        }
      );

      if (!res.ok) {
        throw new Error(API_ERROR_MESSAGE);
      }

      const data = await res.json();
      setProduct(data);
    } catch (err) {
      setError(
        err instanceof TypeError
          ? BACKEND_UNREACHABLE_MESSAGE
          : err instanceof Error
            ? err.message
            : API_ERROR_MESSAGE
      );
    } finally {
      setLoadingProduct(false);
    }
  }

  useEffect(() => {
    if (!requireAuth()) return;
    void validateAuthSession("/odoo");

    const timer = window.setTimeout(() => {
      void loadStatus();
    }, 0);

    return () => window.clearTimeout(timer);
  }, []);

  const connected = Boolean(status?.connected);

  return (
    <AppShell
      active="odoo"
      eyebrow="Intégration ERP"
      title="Console Odoo"
      subtitle="Consultation sécurisée des données Odoo. Les lectures sont directes, les écritures restent soumises à validation humaine."
      badges={[{ label: connected ? "Connecté" : "Non connecté", tone: connected ? "success" : "danger" }]}
    >
        <section className="topGrid">
          <div className="panel">
            <div className="panelHeader">
              <div>
                <p className="eyebrow">État système</p>
                <h3>Connexion & environnement</h3>
              </div>
            </div>

            {loadingStatus && <p className="empty">Vérification...</p>}

            {!loadingStatus && (
              <div className="details">
	                <Detail
	                  label="Statut"
	                  value={connected ? "Connecté" : "Non connecté"}
	                />
	                <Detail
	                  label="Hôte"
	                  value={connected ? "Serveur Odoo configuré" : "Non disponible"}
	                />
	                <Detail
	                  label="Base de données"
	                  value={connected ? "Base de test" : "Non disponible"}
	                />
	                <Detail
	                  label="Utilisateur API"
	                  value={connected ? "Compte technique" : "Non disponible"}
	                />
	                <Detail
	                  label="Message"
	                  value={connected ? "Connexion opérationnelle" : "Odoo indisponible"}
	                />
	              </div>
	            )}
	          </div>

	          <div className="panel">
	            <div className="panelHeader">
	              <div>
	                <p className="eyebrow">Sécurité</p>
	                <h3>Mode d’accès</h3>
	              </div>
	            </div>

	            <div className="accessList">
	              <div className="accessItem ok">Lectures Odoo: exécution directe, sans validation.</div>
	              <div className="accessItem warn">Écritures Odoo: interception obligatoire + validation humaine.</div>
	              <div className="accessItem warn">Actions sensibles: journalisées et soumises à approbation.</div>
	            </div>
	          </div>
	        </section>

	        <section className="panel productSearchPanel">
	          <div className="panelHeader">
	            <div>
	              <p className="eyebrow">Consultation</p>
	              <h3>Recherche produit</h3>
	            </div>
	          </div>

	            <form onSubmit={searchProduct}>
	              <label htmlFor="productName">Nom du produit</label>
              <input
                id="productName"
                value={productName}
                onChange={(event) => setProductName(event.target.value)}
                placeholder="Exemple : BACO CLEAN"
              />

              <div className="buttonRow">
                <button type="submit" disabled={loadingProduct}>
                  {loadingProduct ? "Recherche..." : "Vérifier le produit"}
                </button>

                <Link href="/chat" className="secondaryButton">
                  Tester dans le chat
                </Link>
              </div>
            </form>

            <div className="policyBox">
              <strong>Règle de sécurité</strong>
              <p>
                La consultation produit est une action en lecture seule :
                aucune validation n’est requise et aucune donnée Odoo n’est
                modifiée.
              </p>
	            </div>
	        </section>

        {error && <div className="errorBox">{error}</div>}

        {product && (
          <section className="productPanel">
            <div className="panelHeader">
              <div>
                <p className="eyebrow">Résultat Odoo</p>
                <h3>
                  {product.found
                    ? product.product || "Produit Odoo"
                    : "Produit introuvable"}
                </h3>
              </div>

              <span className="sourceBadge">
	                {product.source ? "Connecteur Odoo sécurisé" : "Odoo"}
              </span>
            </div>

            {product.found ? (
              <>
                <div className="metrics">
                  <Metric
                    label="Stock disponible"
                    value={formatValue(product.stock_quantity)}
                  />
                  <Metric
                    label="Stock prévu"
                    value={formatValue(product.forecast_quantity)}
                  />
                  <Metric
                    label="Prix de vente"
                    value={formatPrice(product.sale_price)}
                  />
                  <Metric label="Unité" value={formatValue(product.unit)} />
                </div>

                <div className="details">
                  <Detail label="Produit" value={formatValue(product.product)} />
                  <Detail
                    label="Référence interne"
                    value={formatValue(product.internal_reference)}
                  />
                  <Detail
                    label="ID Odoo"
                    value={formatValue(product.product_id)}
                  />
                  <Detail
                    label="Entrepôt"
                    value={formatValue(product.warehouse)}
                  />
                  <Detail
                    label="Source"
                    value={formatValue(product.source)}
                  />
                  <Detail label="Validation" value="Non requise" />
                </div>
              </>
            ) : (
              <p className="empty">
                Aucun produit correspondant n’a été trouvé dans Odoo.
              </p>
            )}
          </section>
        )}
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

        .connectionBadge {
          height: 38px;
          display: inline-flex;
          align-items: center;
          gap: 8px;
          padding: 0 13px;
          border-radius: 999px;
          font-size: 13px;
          font-weight: 900;
          white-space: nowrap;
        }

        .connectionBadge span {
          width: 8px;
          height: 8px;
          border-radius: 50%;
          background: currentColor;
        }

        .connectionBadge.ok {
          background: #eef8f3;
          color: #13754a;
          border: 1px solid #b8e0cb;
        }

        .connectionBadge.bad {
          background: #fff1f1;
          color: #9f1d1d;
          border: 1px solid #f2c0c0;
        }

        .topGrid {
          display: grid;
          grid-template-columns: 0.9fr 1.1fr;
          gap: 18px;
          margin-bottom: 18px;
        }

        .panel,
        .productPanel {
          background: #ffffff;
          border: 1px solid #d9dee7;
          padding: 24px;
        }

        .panelHeader {
          display: flex;
          justify-content: space-between;
          align-items: flex-start;
          gap: 16px;
          margin-bottom: 18px;
        }

        .panelHeader h3 {
          margin: 6px 0 0;
          font-size: 22px;
          color: #101827;
        }

        .accessList {
          display: grid;
          gap: 0;
          border-top: 1px solid #e5e7eb;
        }

        .accessItem {
          min-height: 48px;
          display: flex;
          align-items: center;
          gap: 10px;
          border-bottom: 1px solid #e5e7eb;
          color: #334155;
          font-size: 14px;
          font-weight: 800;
        }

        .accessItem:last-child {
          border-bottom: 0;
        }

        .accessItem::before {
          content: "";
          width: 8px;
          height: 8px;
          border-radius: 999px;
          background: currentColor;
          flex: 0 0 auto;
        }

        .accessItem.ok {
          color: #13754a;
        }

        .accessItem.warn {
          color: #a35b13;
        }

        .details {
          border-top: 1px solid #e5e7eb;
        }

        .detail {
          display: grid;
          grid-template-columns: 170px 1fr;
          gap: 14px;
          padding: 13px 0;
          border-bottom: 1px solid #e5e7eb;
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

        label {
          display: block;
          margin-bottom: 10px;
          color: #334155;
          font-size: 13px;
          font-weight: 900;
        }

        input {
          width: 100%;
          height: 44px;
          border: 1px solid #cbd5e1;
          border-radius: 8px;
          padding: 0 13px;
          font-size: 15px;
          color: #111827;
          outline: none;
        }

        input:focus {
          border-color: #172033;
          box-shadow: 0 0 0 3px rgba(23, 32, 51, 0.08);
        }

        .buttonRow {
          display: flex;
          flex-wrap: wrap;
          gap: 10px;
          margin-top: 14px;
        }

        button,
        .secondaryButton {
          height: 40px;
          display: inline-flex;
          align-items: center;
          justify-content: center;
          border-radius: 8px;
          padding: 0 16px;
          font-size: 14px;
          font-weight: 800;
          text-decoration: none;
          cursor: pointer;
        }

        button {
          border: 1px solid #172033;
          background: #172033;
          color: #ffffff;
        }

        button:disabled {
          opacity: 0.6;
          cursor: not-allowed;
        }

        .secondaryButton {
          border: 1px solid #cbd5e1;
          background: #ffffff;
          color: #172033;
        }

        .policyBox {
          margin-top: 18px;
          border: 1px solid #b8e0cb;
          background: #eef8f3;
          padding: 14px;
        }

        .policyBox strong {
          color: #13754a;
          font-size: 13px;
        }

        .policyBox p {
          margin: 6px 0 0;
          color: #475569;
          font-size: 13px;
          line-height: 1.5;
        }

        .errorBox {
          border: 1px solid #f2c0c0;
          background: #fff1f1;
          color: #9f1d1d;
          padding: 14px;
          margin-bottom: 18px;
          font-weight: 700;
        }

        .sourceBadge {
          background: #eef8f3;
          color: #13754a;
          border: 1px solid #b8e0cb;
          border-radius: 999px;
          padding: 8px 11px;
          font-size: 12px;
          font-weight: 900;
          white-space: nowrap;
        }

        .metrics {
          display: grid;
          grid-template-columns: repeat(4, minmax(0, 1fr));
          gap: 14px;
          margin-bottom: 20px;
        }

        .metric {
          border: 1px solid #e5e7eb;
          background: #fbfcfe;
          padding: 18px;
        }

        .metric p {
          margin: 0 0 8px;
          color: #647084;
          font-size: 12px;
          font-weight: 900;
          text-transform: uppercase;
          letter-spacing: 0.08em;
        }

        .metric h4 {
          margin: 0;
          color: #101827;
          font-size: 26px;
          letter-spacing: -0.04em;
        }

        .empty {
          color: #647084;
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

          .topGrid,
          .metrics {
            grid-template-columns: 1fr;
          }
        }
      `}</style>
    </AppShell>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="metric">
      <p>{label}</p>
      <h4>{value}</h4>
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

function formatValue(value: unknown) {
  if (value === undefined || value === null || value === "") return "-";
  return String(value);
}

function formatPrice(value: unknown) {
  if (value === undefined || value === null || value === "") return "-";
  return `${value} DH`;
}
