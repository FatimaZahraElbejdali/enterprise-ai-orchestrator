"use client";

import Link from "next/link";
import { FormEvent, useMemo, useState } from "react";

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type ChatResponse = {
  intent?: string;
  agent?: string;
  risk?: string;
  requires_approval?: boolean;
  approval_required?: boolean;
  status?: string;
  message?: string;
  approval_id?: string;
  tool_used?: string | null;
  data?: any;
  result?: any;
};

export default function ChatPage() {
  const [message, setMessage] = useState("Check stock for BACO CLEAN");
  const [loading, setLoading] = useState(false);
  const [response, setResponse] = useState<ChatResponse | null>(null);
  const [error, setError] = useState("");

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();

    const cleanMessage = message.trim();

    if (!cleanMessage) return;

    setLoading(true);
    setError("");
    setResponse(null);

    try {
      const res = await fetch(`${API_BASE}/chat`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          message: cleanMessage,
        }),
      });

      if (!res.ok) {
        throw new Error("Erreur lors de l’appel au backend.");
      }

      const data = await res.json();
      setResponse(data);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Une erreur inconnue est survenue."
      );
    } finally {
      setLoading(false);
    }
  }

  const odooData = response?.data;
  const isApprovalRequired =
    response?.requires_approval === true ||
    response?.approval_required === true;

  const isOdooProductResult =
    response?.intent === "odoo" &&
    odooData &&
    typeof odooData === "object" &&
    ("available_stock" in odooData ||
      "forecast_stock" in odooData ||
      "sale_price" in odooData ||
      "product" in odooData);

  const isSensitiveAction =
    response?.status === "pending_approval" || isApprovalRequired;

  const statusLabel = useMemo(() => {
    if (!response) return "En attente";

    if (response.status === "completed") return "Terminé";
    if (response.status === "pending_approval") return "Validation requise";
    if (response.status === "not_found") return "Introuvable";
    if (response.status === "failed") return "Échec";

    return response.status || "Traité";
  }, [response]);

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
            <Link href="/chat" className="active">
              Console Chat
            </Link>
            <Link href="/odoo">Odoo</Link>
            <Link href="/approvals">Validations</Link>
            <Link href="/logs">Audit Logs</Link>
          </nav>
        </div>

        <div className="sidebarFooter">
          <p>Mode démo sécurisé</p>
          <span>Aucune action sensible n’est exécutée sans validation.</span>
        </div>
      </aside>

      <section className="content">
        <header className="header">
          <div>
            <p className="eyebrow">Console Orchestrateur</p>
            <h2>Chat opérationnel</h2>
            <p className="subtitle">
              Posez une demande métier. L’orchestrateur identifie le système
              cible, le niveau de risque, l’agent à utiliser et la nécessité
              d’une validation humaine.
            </p>
          </div>

          <div className="headerBadge">
            <span className="badgeDot" />
            Contrôle actif
          </div>
        </header>

        <section className="promptPanel">
          <form onSubmit={handleSubmit}>
            <label htmlFor="message">Demande utilisateur</label>
            <textarea
              id="message"
              value={message}
              onChange={(event) => setMessage(event.target.value)}
              placeholder="Exemple : Check stock for BACO CLEAN"
              rows={4}
            />

            <div className="buttonRow">
              <button type="submit" disabled={loading}>
                {loading ? "Traitement..." : "Envoyer"}
              </button>

              <button
                type="button"
                className="secondary"
                onClick={() =>
                  setMessage("Change price of BACO CLEAN to 25 DH")
                }
              >
                Tester action sensible
              </button>

              <button
                type="button"
                className="secondary"
                onClick={() => setMessage("Check stock for BACO CLEAN")}
              >
                Tester lecture Odoo
              </button>
            </div>
          </form>
        </section>

        {error && <div className="errorBox">{error}</div>}

        {response && (
          <>
            <section className="decisionGrid">
              <InfoCard
                label="Intent"
                value={response.intent || "Non détecté"}
              />
              <InfoCard
                label="Agent"
                value={response.agent || "Non sélectionné"}
              />
              <InfoCard
                label="Risque"
                value={translateRisk(response.risk)}
              />
              <InfoCard
                label="Validation"
                value={
                  isApprovalRequired ? "Requise" : "Non requise"
                }
                tone={isApprovalRequired ? "warning" : "success"}
              />
            </section>

            {isOdooProductResult && !isSensitiveAction && (
              <section className="resultPanel">
                <div className="panelHeader">
                  <div>
                    <p className="eyebrow">Résultat Odoo</p>
                    <h3>{odooData.product || "Produit Odoo"}</h3>
                  </div>

                  <span className="sourceBadge">
                    {odooData.source || "real_odoo"}
                  </span>
                </div>

                <div className="productGrid">
                  <Metric
                    label="Stock disponible"
                    value={formatValue(odooData.available_stock)}
                  />
                  <Metric
                    label="Stock prévu"
                    value={formatValue(odooData.forecast_stock)}
                  />
                  <Metric
                    label="Prix de vente"
                    value={formatPrice(odooData.sale_price)}
                  />
                  <Metric
                    label="Unité"
                    value={formatValue(odooData.unit)}
                  />
                </div>

                <div className="detailsTable">
                  <Detail
                    label="Produit"
                    value={formatValue(odooData.product)}
                  />
                  <Detail
                    label="Référence interne"
                    value={formatValue(odooData.internal_reference)}
                  />
                  <Detail
                    label="ID Odoo"
                    value={formatValue(odooData.product_id)}
                  />
                  <Detail
                    label="Outil utilisé"
                    value={response.tool_used || "odoo_check_stock"}
                  />
                  <Detail label="Statut" value={statusLabel} />
                  <Detail label="Validation" value="Non requise" />
                </div>
              </section>
            )}

            {isSensitiveAction && (
              <section className="approvalPanel">
                <div className="panelHeader">
                  <div>
                    <p className="eyebrow">Action sensible détectée</p>
                    <h3>Validation humaine requise</h3>
                  </div>

                  <span className="warningBadge">Bloquée</span>
                </div>

                <p className="approvalMessage">
                  {response.message ||
                    "Cette action nécessite une validation humaine avant exécution."}
                </p>

                <div className="detailsTable">
                  <Detail
                    label="Action"
                    value={translateAction(odooData?.action)}
                  />
                  <Detail
                    label="Produit"
                    value={formatValue(odooData?.product)}
                  />
                  <Detail
                    label="Valeur demandée"
                    value={formatValue(odooData?.requested_value)}
                  />
                  <Detail
                    label="ID validation"
                    value={response.approval_id || "-"}
                  />
                  <Detail label="Exécuté dans Odoo" value="Non" />
                  <Detail label="Statut" value={statusLabel} />
                </div>

                <div className="approvalActions">
                  <Link href="/approvals">Voir les validations</Link>
                  <Link href="/logs">Voir les logs d’audit</Link>
                </div>
              </section>
            )}

            {!isOdooProductResult && !isSensitiveAction && (
              <section className="resultPanel">
                <div className="panelHeader">
                  <div>
                    <p className="eyebrow">Résultat Agent</p>
                    <h3>{statusLabel}</h3>
                  </div>
                </div>

                <p className="genericMessage">
                  {response.message || "Réponse traitée par l’orchestrateur."}
                </p>
              </section>
            )}

            <details className="rawPanel">
              <summary>Réponse brute</summary>
              <pre>{JSON.stringify(response, null, 2)}</pre>
            </details>
          </>
        )}
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
          letter-spacing: -0.04em;
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
          line-height: 1.1;
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
          align-items: flex-start;
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

        .headerBadge {
          height: 38px;
          display: inline-flex;
          align-items: center;
          gap: 8px;
          padding: 0 13px;
          border-radius: 999px;
          border: 1px solid #b8e0cb;
          background: #eef8f3;
          color: #13754a;
          font-size: 13px;
          font-weight: 800;
          white-space: nowrap;
        }

        .badgeDot {
          width: 8px;
          height: 8px;
          border-radius: 50%;
          background: #13754a;
        }

        .promptPanel,
        .resultPanel,
        .approvalPanel,
        .rawPanel {
          background: #ffffff;
          border: 1px solid #d9dee7;
          padding: 24px;
          margin-bottom: 18px;
        }

        label {
          display: block;
          margin-bottom: 10px;
          color: #334155;
          font-size: 13px;
          font-weight: 900;
        }

        textarea {
          width: 100%;
          resize: vertical;
          border: 1px solid #cbd5e1;
          border-radius: 8px;
          padding: 14px;
          font-size: 15px;
          font-family: inherit;
          color: #111827;
          background: #ffffff;
          outline: none;
        }

        textarea:focus {
          border-color: #172033;
          box-shadow: 0 0 0 3px rgba(23, 32, 51, 0.08);
        }

        .buttonRow {
          display: flex;
          flex-wrap: wrap;
          gap: 10px;
          margin-top: 14px;
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

        button:disabled {
          cursor: not-allowed;
          opacity: 0.6;
        }

        button.secondary {
          background: #ffffff;
          color: #172033;
          border-color: #cbd5e1;
        }

        .errorBox {
          border: 1px solid #f2c0c0;
          background: #fff1f1;
          color: #9f1d1d;
          padding: 14px;
          margin-bottom: 18px;
          font-weight: 700;
        }

        .decisionGrid {
          display: grid;
          grid-template-columns: repeat(4, minmax(0, 1fr));
          gap: 14px;
          margin-bottom: 18px;
        }

        .infoCard {
          background: #ffffff;
          border: 1px solid #d9dee7;
          padding: 18px;
          min-height: 110px;
        }

        .infoCard p {
          margin: 0 0 12px;
          color: #647084;
          font-size: 12px;
          text-transform: uppercase;
          letter-spacing: 0.08em;
          font-weight: 900;
        }

        .infoCard h3 {
          margin: 0;
          color: #101827;
          font-size: 21px;
          letter-spacing: -0.03em;
        }

        .infoCard.success {
          border-left: 4px solid #13754a;
        }

        .infoCard.warning {
          border-left: 4px solid #b7791f;
        }

        .panelHeader {
          display: flex;
          align-items: flex-start;
          justify-content: space-between;
          gap: 16px;
          margin-bottom: 20px;
        }

        .panelHeader h3 {
          margin: 6px 0 0;
          color: #101827;
          font-size: 24px;
          letter-spacing: -0.04em;
        }

        .sourceBadge,
        .warningBadge {
          border-radius: 999px;
          padding: 8px 11px;
          font-size: 12px;
          font-weight: 900;
          white-space: nowrap;
        }

        .sourceBadge {
          background: #eef8f3;
          color: #13754a;
          border: 1px solid #b8e0cb;
        }

        .warningBadge {
          background: #fff7df;
          color: #8a5a00;
          border: 1px solid #f2d38b;
        }

        .productGrid {
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

        .detailsTable {
          border-top: 1px solid #e5e7eb;
        }

        .detail {
          display: grid;
          grid-template-columns: 190px 1fr;
          gap: 16px;
          border-bottom: 1px solid #e5e7eb;
          padding: 13px 0;
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

        .approvalPanel {
          border-left: 4px solid #b7791f;
        }

        .approvalMessage,
        .genericMessage {
          margin: 0 0 18px;
          color: #475569;
          font-size: 15px;
          line-height: 1.6;
        }

        .approvalActions {
          display: flex;
          gap: 10px;
          margin-top: 18px;
        }

        .approvalActions a {
          height: 40px;
          display: inline-flex;
          align-items: center;
          justify-content: center;
          padding: 0 14px;
          border-radius: 8px;
          background: #172033;
          color: #ffffff;
          text-decoration: none;
          font-size: 14px;
          font-weight: 800;
        }

        .rawPanel summary {
          cursor: pointer;
          color: #172033;
          font-weight: 900;
        }

        pre {
          margin: 16px 0 0;
          max-height: 420px;
          overflow: auto;
          background: #0f172a;
          color: #e5e7eb;
          padding: 16px;
          border-radius: 8px;
          font-size: 12px;
          line-height: 1.6;
        }

        @media (max-width: 1180px) {
          .pageShell {
            grid-template-columns: 1fr;
          }

          .sidebar {
            min-height: auto;
            position: relative;
          }

          .nav {
            grid-template-columns: repeat(5, minmax(0, 1fr));
          }

          .sidebarFooter {
            display: none;
          }

          .decisionGrid,
          .productGrid {
            grid-template-columns: repeat(2, minmax(0, 1fr));
          }
        }

        @media (max-width: 720px) {
          .content {
            padding: 18px;
          }

          .header {
            flex-direction: column;
          }

          .decisionGrid,
          .productGrid {
            grid-template-columns: 1fr;
          }

          .detail {
            grid-template-columns: 1fr;
            gap: 4px;
          }

          .nav {
            grid-template-columns: 1fr;
          }
        }
      `}</style>
    </main>
  );
}

function InfoCard({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: "success" | "warning";
}) {
  return (
    <div className={`infoCard ${tone || ""}`}>
      <p>{label}</p>
      <h3>{value}</h3>
    </div>
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
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "190px 1fr",
        gap: "16px",
        borderBottom: "1px solid #e5e7eb",
        padding: "13px 0",
      }}
    >
      <span
        style={{
          color: "#647084",
          fontSize: "13px",
          fontWeight: 800,
        }}
      >
        {label}
      </span>

      <span
        style={{
          color: "#172033",
          fontSize: "13px",
          fontWeight: 800,
          wordBreak: "break-word",
        }}
      >
        {value}
      </span>
    </div>
  );
}

function formatValue(value: any) {
  if (value === undefined || value === null || value === "") return "-";
  return String(value);
}

function formatPrice(value: any) {
  if (value === undefined || value === null || value === "") return "-";
  return `${value} DH`;
}

function translateRisk(value?: string) {
  if (value === "low") return "Faible";
  if (value === "medium") return "Moyen";
  if (value === "high") return "Élevé";
  return "Non évalué";
}

function translateAction(value?: string) {
  const labels: Record<string, string> = {
    change_price: "Modification du prix",
    change_stock: "Modification du stock",
    change_unit: "Modification de l’unité",
    modify_invoice: "Modification facture",
    check_stock: "Consultation stock",
    check_price: "Consultation prix",
    check_unit: "Consultation unité",
    check_product_details: "Consultation produit",
  };

  if (!value) return "-";
  return labels[value] || value;
}