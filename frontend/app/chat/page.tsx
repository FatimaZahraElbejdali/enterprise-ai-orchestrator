"use client";

import Link from "next/link";
import { FormEvent, useMemo, useState } from "react";

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type LooseRecord = Record<string, unknown>;

type OdooStockResult = {
  product?: unknown;
  internal_reference?: unknown;
  available_stock?: unknown;
  forecast_stock?: unknown;
  sale_price?: unknown;
  unit?: unknown;
  source?: unknown;
};

type ChatResponse = {
  intent?: string;
  agent?: string;
  selected_agent?: string;
  risk?: string;
  risk_level?: string;
  parser_source?: string;
  language?: string | null;
  parsed_action?: string;
  document_type?: string | null;
  document_reference?: string | null;
  document_id?: number | null;
  partner_name?: string | null;
  product_name?: string | null;
  line_product?: string | null;
  field?: string | null;
  technical_field?: string | null;
  new_value?: unknown;
  needs_clarification?: boolean;
  requires_approval?: boolean;
  approval_required?: boolean;
  status?: string;
  message?: string;
  approval_id?: string;
  tool_used?: string | null;
  data?: LooseRecord;
  result?: unknown;
  agent_result?: {
    agent?: string;
    tool_used?: string | null;
    result?: unknown;
  };
  response?: {
    provider?: string;
    model?: string;
    success?: boolean;
    content?: string;
    error?: string | null;
  };
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

  const odooStockResult = normalizeOdooStockResult(response);
  const selectedAgent =
    response?.agent ||
    response?.selected_agent ||
    response?.agent_result?.agent;
  const selectedRisk = response?.risk || response?.risk_level;
  const selectedTool = response?.tool_used || response?.agent_result?.tool_used;
  const localAgentResult = response?.agent_result?.result || response?.result;
  const isApprovalRequired =
    response?.requires_approval === true ||
    response?.approval_required === true;

  const isOdooProductResult = Boolean(
    response?.intent === "odoo" && odooStockResult
  );

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
                Tester validation Odoo
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
                value={formatAgentName(selectedAgent)}
              />
              <InfoCard
                label="Risque"
                value={translateRisk(selectedRisk)}
              />
              <InfoCard
                label="Validation"
                value={
                  isApprovalRequired ? "Requise" : "Non requise"
                }
                tone={isApprovalRequired ? "warning" : "success"}
              />
            </section>

            {response.parser_source && (
              <section className="analysisPanel">
                <div className="detailsTable">
                  <Detail
                    label="Source d’analyse"
                    value={formatParserSource(response.parser_source)}
                  />
                  <Detail
                    label="Action détectée"
                    value={translateAction(response.parsed_action)}
                  />
                  <Detail
                    label="Validation requise"
                    value={isApprovalRequired ? "Oui" : "Non"}
                  />
                  <Detail
                    label="Document"
                    value={
                      response.document_reference ||
                      formatValue(response.document_id)
                    }
                  />
                  <Detail
                    label="Produit"
                    value={formatValue(
                      response.product_name || response.line_product
                    )}
                  />
                </div>
              </section>
            )}

            {isOdooProductResult && !isSensitiveAction && (
              <section className="resultPanel">
                <div className="panelHeader">
                  <div>
                    <p className="eyebrow">Résultat Odoo</p>
                    <h3>
                      {odooStockResult?.product
                        ? formatValue(odooStockResult.product)
                        : "Produit Odoo"}
                    </h3>
                  </div>

                  <span className="sourceBadge">
                    {formatValue(odooStockResult?.source || "real_odoo")}
                  </span>
                </div>

                <div className="productGrid">
                  <Metric
                    label="Stock disponible"
                    value={formatNumber(odooStockResult?.available_stock)}
                  />
                  <Metric
                    label="Stock prévisionnel"
                    value={formatNumber(odooStockResult?.forecast_stock)}
                  />
                  <Metric
                    label="Prix de vente"
                    value={formatPrice(odooStockResult?.sale_price)}
                  />
                  <Metric
                    label="Unité"
                    value={formatValue(odooStockResult?.unit)}
                  />
                </div>

                <div className="detailsTable">
                  <Detail
                    label="Produit"
                    value={formatValue(odooStockResult?.product)}
                  />
                  <Detail
                    label="Référence interne"
                    value={formatValue(odooStockResult?.internal_reference)}
                  />
                  <Detail
                    label="Stock disponible"
                    value={formatNumber(odooStockResult?.available_stock)}
                  />
                  <Detail
                    label="Stock prévisionnel"
                    value={formatNumber(odooStockResult?.forecast_stock)}
                  />
                  <Detail
                    label="Prix de vente"
                    value={formatPrice(odooStockResult?.sale_price)}
                  />
                  <Detail
                    label="Unité"
                    value={formatValue(odooStockResult?.unit)}
                  />
                  <Detail
                    label="Source"
                    value={formatValue(odooStockResult?.source || "real_odoo")}
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

                {localAgentResult && (
                  <div className="detailsTable">
                    <Detail
                      label="Agent"
                      value={formatAgentName(selectedAgent)}
                    />
                    <Detail
                      label="Outil utilisé"
                      value={selectedTool || "Aucun"}
                    />
                    <Detail
                      label="Diagnostic"
                      value={formatAgentResult(localAgentResult)}
                    />
                  </div>
                )}
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
        .analysisPanel,
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

function isLooseRecord(value: unknown): value is LooseRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function normalizeOdooStockResult(response: ChatResponse | null): OdooStockResult | null {
  const result = isLooseRecord(response?.result) ? response.result : null;
  const data = isLooseRecord(response?.data) ? response.data : null;

  const hasResultStock =
    result &&
    ("stock_quantity" in result ||
      "forecast_quantity" in result ||
      "sale_price" in result ||
      "product" in result);

  const hasDataStock =
    data &&
    ("available_stock" in data ||
      "forecast_stock" in data ||
      "sale_price" in data ||
      "product" in data);

  if (!hasResultStock && !hasDataStock) {
    return null;
  }

  return {
    product: result?.product ?? data?.product,
    internal_reference:
      result?.internal_reference ?? data?.internal_reference,
    available_stock: result?.stock_quantity ?? data?.available_stock,
    forecast_stock: result?.forecast_quantity ?? data?.forecast_stock,
    sale_price: result?.sale_price ?? data?.sale_price,
    unit: result?.unit ?? data?.unit,
    source: result?.source ?? data?.source,
  };
}

function formatValue(value: unknown) {
  if (value === undefined || value === null || value === "") return "-";
  return String(value);
}

function formatNumber(value: unknown) {
  if (typeof value === "number" && Number.isFinite(value)) {
    return Number.isInteger(value) ? String(value) : String(value);
  }

  return formatValue(value);
}

function formatPrice(value: unknown) {
  if (value === undefined || value === null || value === "") return "-";
  return `${value} DH`;
}

function formatAgentName(value?: string) {
  if (!value) return "Non sélectionné";

  const labels: Record<string, string> = {
    support: "Support",
    support_agent: "Support",
    knowledge: "Connaissance",
    knowledge_agent: "Connaissance",
    development: "Développement",
    development_agent: "Développement",
    security: "Sécurité",
    security_agent: "Sécurité",
    server: "Serveur",
    server_agent: "Serveur",
    odoo: "Odoo",
    odoo_agent: "Odoo",
    general: "Général",
    general_agent: "Général",
  };

  return labels[value] || value;
}

function formatAgentResult(value: unknown) {
  if (value === undefined || value === null || value === "") return "-";

  if (typeof value === "string") return value;

  if (typeof value !== "object") return String(value);

  const record = value as LooseRecord;
  const diagnosis = record.diagnosis;
  const suggestedSteps = record.suggested_steps;

  if (typeof diagnosis === "string" && Array.isArray(suggestedSteps)) {
    return `${diagnosis}. Actions recommandées: ${suggestedSteps.join("; ")}.`;
  }

  const summary = record.summary;
  const nextSteps = record.next_steps || record.recommended_actions;

  if (typeof summary === "string" && Array.isArray(nextSteps)) {
    return `${summary} Actions recommandées: ${nextSteps.join("; ")}.`;
  }

  return JSON.stringify(value);
}

function translateRisk(value?: string) {
  if (value === "low") return "Faible";
  if (value === "medium") return "Moyen";
  if (value === "high") return "Élevé";
  return "Non évalué";
}

function formatParserSource(value?: string) {
  if (value === "openai") return "OpenAI";
  if (value === "fallback" || value === "local_rules") return "Fallback local";
  if (value === "test") return "Test";
  return value || "-";
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
    search_document: "Consultation document",
    read_document: "Consultation document",
    update_document_line: "Modification d’une ligne de document",
    update_document_partner: "Modification client/fournisseur",
    update_document_date: "Modification date document",
    toggle_boolean_field: "Modification champ analytique",
  };

  if (!value) return "-";
  return labels[value] || value;
}
