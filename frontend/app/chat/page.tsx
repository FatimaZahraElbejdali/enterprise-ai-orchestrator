"use client";

import Link from "next/link";
import Image from "next/image";
import { FormEvent, KeyboardEvent, useEffect, useRef, useState } from "react";
import {
  API_ERROR_MESSAGE,
  ApiRequestError,
  AuthUser,
  BACKEND_UNREACHABLE_MESSAGE,
  approveApproval,
  clearAuth,
  getDepartmentLabel,
  getRoleLabel,
  getStoredUser,
  hasAnyPermission,
  postChatMessage,
  requireAuth,
  rejectApproval,
} from "@/lib/api";

type LooseRecord = Record<string, unknown>;

const SHOW_TECHNICAL_DETAILS =
  process.env.NEXT_PUBLIC_CHAT_DEBUG === "true";

const SUGGESTED_PROMPTS = [
  "Quels fournisseurs apparaissent le plus dans les bons de commande ?",
  "Vérifie l’état des serveurs",
  "Raconte-moi l’histoire du groupe Jamain Baco",
];

type OdooStockResult = {
  product?: unknown;
  internal_reference?: unknown;
  available_stock?: unknown;
  forecast_stock?: unknown;
  sale_price?: unknown;
  unit?: unknown;
  source?: unknown;
};

type OdooDocumentResult = {
  document?: unknown;
  type?: unknown;
  id?: unknown;
  partner?: unknown;
  status?: unknown;
  date?: unknown;
  lines: LooseRecord[];
};

type OdooProductSearchResult = {
  keyword?: unknown;
  found: boolean;
  products: Candidate[];
};

type OdooGenericRecordResult = {
  model?: unknown;
  keyword?: unknown;
  found: boolean;
  ambiguous: boolean;
  records: Candidate[];
  record?: LooseRecord | null;
};

type Candidate = Record<string, unknown>;

type MainAnswer = {
  title: string;
  message: string;
};

type ChatSource = {
  source_type?: string;
  title?: string;
  url?: string;
  label?: string;
};

type ChatTechnicalMetadata = {
  intent?: string | null;
  agent?: string | null;
  capability?: string | null;
  action?: string | null;
  risk?: string | null;
  approval_status?: string | null;
  parser_source?: string | null;
  tool_used?: string | null;
  provider?: string | null;
  model?: string | null;
  permission_decision?: string | null;
  department?: string | null;
  target_system?: string | null;
  odoo_model?: string | null;
  record_count?: number | null;
  selected_model?: string | null;
  candidate_models?: string[] | null;
  fields_used?: string[] | null;
  domain_used?: unknown[] | null;
  count_returned?: number | null;
  failure_reason?: string | null;
  aggregation_field?: string | null;
  odoo_method?: string | null;
  odoo_tool_steps?: Array<Record<string, unknown>>;
  final_odoo_model?: string | null;
  final_record_count?: number | null;
  business_scope_status?: string | null;
  retrieval_query?: string | null;
  classifier_source?: string | null;
  knowledge_scopes?: string[];
  approval_action?: string | null;
  approval_entity?: string | null;
  approval_requested_change?: string | null;
  memory_context_used?: boolean | null;
  resolved_from_previous_model?: string | null;
  resolved_business_object?: string | null;
  follow_up_limit?: number | null;
  pending_context_used?: boolean | null;
  pending_context_type?: string | null;
  original_request?: string | null;
  merged_request?: string | null;
  merged_parameters?: Record<string, unknown> | null;
  cleared_pending_context?: boolean | null;
  pending_context_cleared?: boolean | null;
};

type ChatResponse = {
  status: string;
  response: string;
  requires_approval?: boolean;
  approval_id?: string | null;
  sources?: ChatSource[];
  technical: ChatTechnicalMetadata;
};

type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  content?: string;
  response?: ChatResponse;
  loading?: boolean;
  error?: string;
};

export default function ChatPage() {
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [error, setError] = useState("");
  const [approvalActionLoading, setApprovalActionLoading] = useState<
    "approve" | "reject" | null
  >(null);
  const [approvalActionMessage, setApprovalActionMessage] = useState("");
  const [approvalActionError, setApprovalActionError] = useState("");
  const [currentUser] = useState<AuthUser | null>(() => getStoredUser());
  const messagesEndRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!requireAuth()) return;
  }, []);

  function handleLogout() {
    clearAuth();
    window.location.href = "/login";
  }

  async function submitMessage(rawMessage: string) {
    const cleanMessage = rawMessage.trim();

    if (!cleanMessage || loading) return;

    const userMessageId = createMessageId("user");
    const assistantMessageId = createMessageId("assistant");

    setLoading(true);
    setError("");
    setApprovalActionLoading(null);
    setApprovalActionMessage("");
    setApprovalActionError("");
    setMessage("");
    setMessages((current) => [
      ...current,
      {
        id: userMessageId,
        role: "user",
        content: cleanMessage,
      },
      {
        id: assistantMessageId,
        role: "assistant",
        loading: true,
      },
    ]);

    try {
      const data = await postChatMessage<ChatResponse>(cleanMessage);
      setMessages((current) =>
        current.map((item) =>
          item.id === assistantMessageId
            ? {
                id: assistantMessageId,
                role: "assistant",
                response: data,
              }
            : item
        )
      );
    } catch (err) {
      const errorMessage =
        err instanceof TypeError
          ? BACKEND_UNREACHABLE_MESSAGE
          : err instanceof Error
            ? err.message
            : API_ERROR_MESSAGE;
      setError(errorMessage);
      setMessages((current) =>
        current.map((item) =>
          item.id === assistantMessageId
            ? {
                id: assistantMessageId,
                role: "assistant",
                error: errorMessage,
              }
            : item
        )
      );
    } finally {
      setLoading(false);
    }
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    await submitMessage(message);
  }

  function handleComposerKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key !== "Enter" || event.shiftKey) return;

    event.preventDefault();
    void submitMessage(message);
  }

  async function handleInlineApproval(
    decision: "approve" | "reject",
    response: ChatResponse
  ) {
    const approvalId = getApprovalId(response);

    if (!approvalId || !isPendingApprovalResponse(response)) return;

    setApprovalActionLoading(decision);
    setApprovalActionMessage("");
    setApprovalActionError("");

    try {
      const updatedApproval =
        decision === "approve"
          ? await approveApproval<LooseRecord>(approvalId)
          : await rejectApproval<LooseRecord>(approvalId);
      const status = getStringValue(updatedApproval.status) || (
        decision === "approve" ? "approved" : "rejected"
      );

      setMessages((current) =>
        current.map((item) =>
          item.response && getApprovalId(item.response) === approvalId
            ? {
                ...item,
                response: {
                  ...item.response,
                  technical: {
                    ...item.response.technical,
                    approval_status: status,
                  },
                },
              }
            : item
        )
      );
      setApprovalActionMessage(
        decision === "approve" ? "Demande approuvée." : "Demande refusée."
      );
    } catch (err) {
      setApprovalActionError(formatApprovalActionError(err));
    } finally {
      setApprovalActionLoading(null);
    }
  }

  const canApproveInline = hasAnyPermission(currentUser, [
    "all",
    "approve_odoo_actions",
  ]);
  const latestAssistantModel = getLatestAssistantModel(messages);

  useEffect(() => {
    window.requestAnimationFrame(() => {
      messagesEndRef.current?.scrollIntoView({
        behavior: "smooth",
        block: "end",
      });
    });
  }, [messages, loading]);

  return (
    <main className="pageShell">
      <aside className="sidebar">
        <div>
          <div className="brand">
            <div className="brandMark">
              <Image
	                className="brandLogo"
	                src="/jamain-baco-logo.png"
	                alt="Jamain Baco"
	                width={56}
	                height={40}
	                priority
	              />
            </div>
            <div>
              <p>Jamain Baco</p>
              <h1>Orchestrateur IA</h1>
            </div>
          </div>

          <p className="navLabel">Navigation</p>
          <nav className="nav">
            <Link href="/">
              <span className="navIcon">□</span>
              Tableau de bord
            </Link>
            <Link href="/chat" className="active">
              <span className="navIcon">▱</span>
              Console de chat
            </Link>
            <Link href="/odoo">
              <span className="navIcon">○</span>
              Odoo
            </Link>
            {hasAnyPermission(currentUser, ["all", "view_approvals", "approve_odoo_actions"]) && (
              <Link href="/approvals">
                <span className="navIcon">✓</span>
                Validations
              </Link>
            )}
            {hasAnyPermission(currentUser, ["all", "view_audit_logs"]) && (
              <Link href="/logs">
                <span className="navIcon">≡</span>
                Journaux d’audit
              </Link>
            )}
          </nav>
        </div>

        <div className="sidebarFooter">
          <p>{currentUser?.email || "Utilisateur connecté"}</p>
          <span>Rôle : {getRoleLabel(currentUser)}</span>
          <span>Département : {getDepartmentLabel(currentUser)}</span>
          <button className="logoutButton" type="button" onClick={handleLogout}>
            Se déconnecter
          </button>
        </div>
      </aside>

      <section className="content">
        <header className="topbar">
          <div className="topbarTitle">
            <p className="eyebrow">Console Orchestrateur</p>
            <h2>Chat</h2>
          </div>

          <div className="topbarActions">
            <div className="modelBadge">{latestAssistantModel}</div>
            <div className="headerBadge">
              <span className="badgeDot" />
              Contrôle actif
            </div>
          </div>
        </header>

        <section className="chatViewport" aria-live="polite">
          {messages.length === 0 ? (
            <div className="emptyState">
              <div className="emptyIcon">▱</div>
              <h3>Comment puis-je vous aider ?</h3>
              <p>
                Posez une question à l’orchestrateur ou choisissez une suggestion
                pour commencer.
              </p>
              <div className="suggestions">
                {SUGGESTED_PROMPTS.map((prompt) => (
                  <button
                    className="suggestionChip"
                    disabled={loading}
                    key={prompt}
                    onClick={() => void submitMessage(prompt)}
                    type="button"
                  >
                    {prompt}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="messageList">
              {messages.map((item) => (
                <div className={`messageTurn ${item.role}`} key={item.id}>
                  <div className="messageAvatar">
                    {item.role === "user" ? userInitial(currentUser) : "IA"}
                  </div>
                  <div className="messageBody">
                    <div className="messageMeta">
                      <span>{item.role === "user" ? "Vous" : "Orchestrateur"}</span>
                    </div>

                    {item.role === "user" && (
                      <div className="userBubble">
                        <p>{item.content}</p>
                      </div>
                    )}

                    {item.role === "assistant" && item.loading && (
                      <div className="assistantLoading">
                        <span />
                        <span />
                        <span />
                      </div>
                    )}

                    {item.role === "assistant" && item.error && (
                      <div className="errorBox">{item.error}</div>
                    )}

                    {item.role === "assistant" && item.response && (
                      <AssistantResponseCard
                        response={item.response}
                        approvalActionLoading={approvalActionLoading}
                        approvalActionMessage={approvalActionMessage}
                        approvalActionError={approvalActionError}
                        canApproveInline={canApproveInline}
                        onApproval={handleInlineApproval}
                      />
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
          <div ref={messagesEndRef} />
        </section>

        <section className="inputArea">
          {error && <div className="errorBox composerError">{error}</div>}
          <form className="composer" onSubmit={handleSubmit}>
            <textarea
              id="message"
              value={message}
              disabled={loading}
              onChange={(event) => setMessage(event.target.value)}
              onKeyDown={handleComposerKeyDown}
              placeholder="De quoi avez-vous besoin ?"
              rows={1}
            />

            <button
              aria-label="Envoyer le message"
              className="sendButton"
              disabled={loading || !message.trim()}
              type="submit"
            >
              {loading ? "..." : "➤"}
            </button>
          </form>
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
	          width: 56px;
	          height: 40px;
	          background: #ffffff;
	          display: grid;
	          place-items: center;
	          border-radius: 10px;
	          overflow: hidden;
	          flex: 0 0 56px;
	        }

	        .brandLogo {
	          width: 56px;
	          height: 40px;
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

        .logoutButton {
          margin-top: 12px;
          width: 100%;
          min-height: 38px;
          border: 1px solid rgba(255, 255, 255, 0.22);
          background: transparent;
          color: #ffffff;
          font-weight: 800;
          cursor: pointer;
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

        .messageList {
          display: grid;
          gap: 14px;
          margin-bottom: 18px;
        }

        .messageTurn {
          min-width: 0;
        }

        .messageTurn.user {
          display: flex;
          justify-content: flex-end;
        }

        .userBubble {
          max-width: min(760px, 86%);
          background: #172033;
          color: #ffffff;
          border-radius: 8px;
          padding: 13px 15px;
        }

        .userBubble p {
          margin: 0;
          white-space: pre-wrap;
          line-height: 1.55;
          font-size: 14px;
          font-weight: 700;
        }

        .assistantLoading {
          width: fit-content;
          max-width: min(760px, 86%);
          background: #ffffff;
          border: 1px solid #d9dee7;
          border-radius: 8px;
          padding: 13px 15px;
          color: #647084;
          font-size: 14px;
          font-weight: 800;
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

        .resultAnchor {
          scroll-margin-top: 18px;
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

        .infoCard.danger {
          border-left: 4px solid #9f1d1d;
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
        .warningBadge,
        .dangerBadge {
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

        .dangerBadge {
          background: #fff1f1;
          color: #9f1d1d;
          border: 1px solid #f2c0c0;
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

        .lineTable {
          margin-top: 18px;
          border: 1px solid #d9dee7;
          overflow: hidden;
        }

        .lineHeader,
        .lineRow {
          display: grid;
          grid-template-columns: 2fr 1fr 1fr;
          gap: 12px;
          padding: 12px 14px;
        }

        .lineHeader {
          background: #f8fafc;
          color: #647084;
          font-size: 12px;
          font-weight: 900;
          text-transform: uppercase;
          letter-spacing: 0.08em;
        }

        .lineRow {
          border-top: 1px solid #e5e7eb;
          color: #172033;
          font-size: 13px;
          font-weight: 800;
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
          flex-wrap: wrap;
          gap: 10px;
          margin-top: 18px;
        }

        .approvalActions button {
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

        .approvalActions button.reject {
          background: #ffffff;
          color: #9f1d1d;
          border-color: #f2c0c0;
        }

        .approvalNotice {
          margin: 14px 0 0;
          border: 1px solid #d9dee7;
          background: #f8fafc;
          color: #475569;
          padding: 12px;
          font-size: 14px;
          font-weight: 800;
        }

        .approvalNotice.success {
          border-color: #b8e0cb;
          background: #eef8f3;
          color: #13754a;
        }

        .approvalNotice.danger {
          border-color: #f2c0c0;
          background: #fff1f1;
          color: #9f1d1d;
        }

        .candidateList {
          display: grid;
          gap: 12px;
        }

        .candidateBlock {
          margin-top: 18px;
        }

        .sourceBlock {
          margin-top: 20px;
          border-top: 1px solid #e5e7eb;
          padding-top: 16px;
        }

        .sourceList {
          display: grid;
          gap: 8px;
          margin-top: 10px;
        }

        .sourceItem {
          display: flex;
          justify-content: space-between;
          align-items: center;
          gap: 16px;
          border: 1px solid #e5e7eb;
          background: #fbfcfe;
          padding: 11px 12px;
          color: #334155;
          font-size: 13px;
          font-weight: 800;
        }

        .sourceItem a {
          color: #13754a;
          font-size: 12px;
          font-weight: 900;
          text-decoration: none;
          white-space: nowrap;
        }

        .candidateItem {
          border: 1px solid #e5e7eb;
          padding: 14px;
          background: #fbfcfe;
        }

        .stepList {
          display: grid;
          gap: 10px;
          padding: 14px 0;
          border-bottom: 1px solid #e5e7eb;
        }

        .stepItem {
          display: grid;
          grid-template-columns: 28px 1fr;
          gap: 10px;
          align-items: start;
        }

        .stepItem span {
          width: 24px;
          height: 24px;
          display: grid;
          place-items: center;
          background: #172033;
          color: #ffffff;
          font-size: 12px;
          font-weight: 900;
        }

        .stepItem p {
          margin: 2px 0 0;
          color: #172033;
          font-size: 14px;
          line-height: 1.45;
          font-weight: 700;
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

          .lineHeader,
          .lineRow {
            grid-template-columns: 1fr;
          }

          .nav {
            grid-template-columns: 1fr;
          }
        }

        body {
          background: #0f1628;
          color: #eef4ff;
        }

        .pageShell {
          min-height: 100vh;
          height: 100vh;
          display: grid;
          grid-template-columns: 270px minmax(0, 1fr);
          overflow: hidden;
          background: #0f1628;
        }

        .sidebar {
          min-height: 100vh;
          padding: 0;
          background: #162035;
          border-right: 1px solid #2a3a5c;
          color: #eef4ff;
          position: relative;
        }

        .brand {
          margin: 0;
          padding: 20px 18px;
          border-bottom: 1px solid #2a3a5c;
        }

        .brandMark {
          width: 42px;
          height: 42px;
          flex: 0 0 42px;
          border-radius: 12px;
          background: #4b7fe8;
          color: #ffffff;
          font-weight: 900;
          font-size: 16px;
        }

        .brandMark span {
          display: block;
        }

        .brand p {
          color: #eef4ff;
          font-size: 14px;
          text-transform: none;
          letter-spacing: 0;
          font-weight: 900;
        }

        .brand h1 {
          color: #8a9bbf;
          font-size: 13px;
          font-weight: 700;
        }

        .navLabel {
          margin: 0;
          padding: 22px 16px 8px;
          color: #5f7195;
          font-size: 11px;
          font-weight: 900;
          letter-spacing: 0.1em;
          text-transform: uppercase;
        }

        .nav {
          padding: 0 10px;
          gap: 7px;
        }

        .nav a {
          border: 1px solid transparent;
          color: #8a9bbf;
          font-size: 14px;
          font-weight: 800;
          border-radius: 10px;
          padding: 11px 13px;
        }

        .nav a:hover {
          background: #1e2d4a;
          color: #eef4ff;
        }

        .nav a.active {
          background: rgba(75, 127, 232, 0.15);
          border-color: rgba(75, 127, 232, 0.45);
          color: #76a0ff;
        }

        .sidebarFooter {
          border-top: 1px solid #2a3a5c;
          padding: 16px;
        }

        .sidebarFooter p {
          color: #eef4ff;
        }

        .sidebarFooter span {
          display: block;
          color: #8a9bbf;
        }

        .logoutButton {
          min-height: 34px;
          border-radius: 8px;
          border-color: #2a3a5c;
          color: #8a9bbf;
        }

        .logoutButton:hover {
          border-color: rgba(224, 82, 82, 0.6);
          color: #ff8b8b;
        }

        .content {
          min-height: 0;
          padding: 0;
          display: flex;
          flex-direction: column;
          background: #0f1628;
          overflow: hidden;
        }

        .topbar {
          min-height: 78px;
          display: flex;
          justify-content: space-between;
          align-items: center;
          gap: 18px;
          padding: 18px 30px;
          background: #0f1628;
          border-bottom: 1px solid #2a3a5c;
          flex: 0 0 auto;
        }

        .topbarTitle {
          min-width: 0;
        }

        .topbarTitle h2 {
          margin: 4px 0 0;
          color: #eef4ff;
          font-size: 28px;
          font-weight: 900;
          letter-spacing: -0.03em;
        }

        .topbarActions {
          display: flex;
          align-items: center;
          gap: 12px;
          flex-wrap: wrap;
          justify-content: flex-end;
        }

        .modelBadge {
          min-height: 36px;
          display: inline-flex;
          align-items: center;
          border: 1px solid #2a3a5c;
          background: #162035;
          color: #8a9bbf;
          border-radius: 10px;
          padding: 0 14px;
          font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas,
            "Liberation Mono", monospace;
          font-size: 12px;
          font-weight: 900;
          white-space: nowrap;
        }

        .headerBadge {
          min-height: 36px;
          border-color: rgba(52, 199, 133, 0.35);
          background: rgba(52, 199, 133, 0.08);
          color: #34c785;
        }

        .badgeDot {
          background: #34c785;
          box-shadow: 0 0 0 4px rgba(52, 199, 133, 0.12);
        }

        .chatViewport {
          flex: 1 1 auto;
          min-height: 0;
          overflow-y: auto;
          padding: 28px 30px;
          scroll-behavior: smooth;
        }

        .chatViewport::-webkit-scrollbar {
          width: 6px;
        }

        .chatViewport::-webkit-scrollbar-thumb {
          background: #2a3a5c;
          border-radius: 999px;
        }

        .emptyState {
          min-height: 100%;
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          gap: 14px;
          color: #5f7195;
          text-align: center;
          padding: 40px 16px;
        }

        .emptyIcon {
          width: 58px;
          height: 58px;
          display: grid;
          place-items: center;
          border-radius: 18px;
          border: 1px solid #2a3a5c;
          background: #1e2d4a;
          color: #76a0ff;
          font-size: 28px;
          font-weight: 900;
        }

        .emptyState h3 {
          margin: 6px 0 0;
          color: #8a9bbf;
          font-size: 21px;
          font-weight: 900;
          letter-spacing: -0.02em;
        }

        .emptyState p {
          margin: 0;
          max-width: 460px;
          color: #5f7195;
          font-size: 15px;
          line-height: 1.55;
          font-weight: 700;
        }

        .suggestions {
          display: flex;
          flex-wrap: wrap;
          gap: 10px;
          justify-content: center;
          max-width: 780px;
          margin-top: 12px;
        }

        .suggestionChip {
          height: auto;
          min-height: 38px;
          border-radius: 999px;
          border: 1px solid #2a3a5c;
          background: #162035;
          color: #8a9bbf;
          padding: 8px 14px;
          font-size: 13px;
          line-height: 1.25;
        }

        .suggestionChip:hover:not(:disabled) {
          color: #76a0ff;
          border-color: rgba(75, 127, 232, 0.65);
          background: rgba(75, 127, 232, 0.12);
        }

        .messageList {
          display: flex;
          flex-direction: column;
          gap: 20px;
          margin: 0 auto;
          width: min(920px, 100%);
        }

        .messageTurn {
          display: flex;
          gap: 12px;
          max-width: 820px;
          align-items: flex-start;
        }

        .messageTurn.user {
          align-self: flex-end;
          flex-direction: row-reverse;
        }

        .messageTurn.assistant {
          align-self: flex-start;
        }

        .messageAvatar {
          width: 34px;
          height: 34px;
          display: grid;
          place-items: center;
          flex: 0 0 34px;
          border-radius: 11px;
          background: #2a3a5c;
          color: #8a9bbf;
          font-size: 12px;
          font-weight: 900;
          margin-top: 2px;
        }

        .messageTurn.assistant .messageAvatar {
          background: #4b7fe8;
          color: #ffffff;
        }

        .messageBody {
          min-width: 0;
          display: grid;
          gap: 5px;
        }

        .messageTurn.user .messageBody {
          justify-items: end;
        }

        .messageMeta {
          color: #5f7195;
          font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas,
            "Liberation Mono", monospace;
          font-size: 11px;
          font-weight: 800;
        }

        .userBubble {
          max-width: min(620px, 100%);
          border-radius: 16px 5px 16px 16px;
          background: #4b7fe8;
          color: #ffffff;
          padding: 13px 16px;
        }

        .userBubble p {
          font-weight: 700;
        }

        .assistantLoading {
          display: inline-flex;
          align-items: center;
          gap: 6px;
          width: auto;
          min-height: 46px;
          border-radius: 5px 16px 16px 16px;
          border: 1px solid #2a3a5c;
          background: #162035;
          padding: 0 16px;
        }

        .assistantLoading span {
          width: 7px;
          height: 7px;
          border-radius: 999px;
          background: #8a9bbf;
          animation: chatPulse 1.35s infinite;
        }

        .assistantLoading span:nth-child(2) {
          animation-delay: 0.18s;
        }

        .assistantLoading span:nth-child(3) {
          animation-delay: 0.36s;
        }

        @keyframes chatPulse {
          0%,
          80%,
          100% {
            opacity: 0.25;
          }
          40% {
            opacity: 1;
          }
        }

        .resultPanel,
        .approvalPanel,
        .rawPanel {
          width: min(720px, 100%);
          margin: 0;
          border-radius: 16px;
          border: 1px solid #2a3a5c;
          background: #162035;
          color: #eef4ff;
          padding: 18px;
        }

        .approvalPanel {
          border-color: rgba(183, 121, 31, 0.55);
          background: #1d2740;
        }

        .rawPanel {
          margin-top: 8px;
          background: #101827;
        }

        .rawPanel summary {
          color: #8a9bbf;
        }

        .genericMessage,
        .stepItem p,
        .lineRow {
          color: #eef4ff;
        }

        .detailsTable,
        .sourceBlock {
          border-color: #2a3a5c;
        }

        .sourceItem,
        .candidateItem,
        .metric,
        .lineTable {
          border-color: #2a3a5c;
          background: #101827;
          color: #eef4ff;
        }

        .lineHeader {
          background: #1e2d4a;
          color: #8a9bbf;
        }

        .inputArea {
          flex: 0 0 auto;
          border-top: 1px solid #2a3a5c;
          background: #0f1628;
          padding: 18px 30px 20px;
        }

        .composer {
          width: min(980px, 100%);
          margin: 0 auto;
          display: flex;
          align-items: flex-end;
          gap: 12px;
          border: 1px solid #2a3a5c;
          background: #162035;
          border-radius: 18px;
          padding: 10px 12px 10px 18px;
        }

        .composer:focus-within {
          border-color: #4b7fe8;
          box-shadow: 0 0 0 3px rgba(75, 127, 232, 0.16);
        }

        .composer textarea {
          min-height: 38px;
          max-height: 140px;
          resize: none;
          border: 0;
          background: transparent;
          color: #eef4ff;
          padding: 9px 0;
          font-size: 15px;
          line-height: 1.45;
          box-shadow: none;
        }

        .composer textarea::placeholder {
          color: #5f7195;
        }

        .composer textarea:focus {
          border: 0;
          box-shadow: none;
        }

        .sendButton {
          width: 42px;
          height: 42px;
          flex: 0 0 42px;
          border-radius: 13px;
          border: 0;
          background: #4b7fe8;
          color: #ffffff;
          padding: 0;
          font-size: 18px;
        }

        .sendButton:hover:not(:disabled) {
          background: #6494f0;
        }

        .inputHint {
          width: min(980px, 100%);
          margin: 8px auto 0;
          color: #5f7195;
          font-size: 12px;
          font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas,
            "Liberation Mono", monospace;
        }

        kbd {
          display: inline-block;
          border: 1px solid #2a3a5c;
          border-radius: 5px;
          background: #1e2d4a;
          color: #8a9bbf;
          padding: 1px 6px;
          font-size: 11px;
          font-family: inherit;
        }

        .composerError {
          width: min(980px, 100%);
          margin: 0 auto 10px;
        }

        @media (max-width: 1180px) {
          .pageShell {
            height: auto;
            min-height: 100vh;
            overflow: visible;
            grid-template-columns: 1fr;
          }

          .sidebar {
            min-height: auto;
          }

          .content {
            min-height: calc(100vh - 170px);
          }

          .nav {
            grid-template-columns: repeat(5, minmax(0, 1fr));
          }
        }

        @media (max-width: 720px) {
          .topbar,
          .inputArea,
          .chatViewport {
            padding-left: 18px;
            padding-right: 18px;
          }

          .topbar {
            align-items: flex-start;
            flex-direction: column;
          }

          .messageTurn,
          .messageTurn.user {
            max-width: 100%;
          }

          .messageAvatar {
            display: none;
          }

          .resultPanel,
          .approvalPanel,
          .rawPanel {
            width: 100%;
          }

          .nav {
            grid-template-columns: 1fr;
          }
        }

        .nav a {
          display: flex;
          align-items: center;
          gap: 10px;
        }

        .navIcon {
          width: 18px;
          display: inline-grid;
          place-items: center;
          flex: 0 0 18px;
          color: #5f7195;
          font-size: 15px;
          font-weight: 900;
        }

        .nav a.active .navIcon,
        .nav a:hover .navIcon {
          color: currentColor;
        }

        .chatViewport {
          padding: 26px 28px 18px;
        }

        .messageList {
          width: min(940px, 100%);
          gap: 18px;
          padding-bottom: 4px;
        }

        .messageTurn {
          width: 100%;
          max-width: none;
        }

        .messageTurn.user {
          justify-content: flex-start;
        }

        .messageTurn.assistant {
          justify-content: flex-start;
        }

        .messageTurn.user .messageBody {
          max-width: min(680px, 78%);
        }

        .messageTurn.assistant .messageBody {
          max-width: min(780px, 86%);
        }

        .messageTurn.assistant {
          gap: 10px;
        }

        .messageTurn.user .messageAvatar {
          margin-left: 0;
        }

        .messageTurn.assistant .messageAvatar {
          margin-right: 0;
        }

        .messageMeta {
          padding: 0 2px;
        }

        .userBubble {
          width: fit-content;
          max-width: 100%;
          padding: 12px 15px;
          box-shadow: 0 10px 24px rgba(0, 0, 0, 0.12);
        }

        .resultPanel,
        .approvalPanel,
        .rawPanel {
          width: 100%;
          max-width: 100%;
          border-radius: 15px;
          padding: 17px;
          box-shadow: 0 10px 26px rgba(0, 0, 0, 0.12);
        }

        .assistantLoading {
          min-height: 44px;
          padding: 0 15px;
        }

        .inputArea {
          position: sticky;
          bottom: 0;
          z-index: 5;
          padding: 10px 28px 12px;
        }

        .composer {
          width: min(940px, 100%);
          border-radius: 16px;
          padding: 6px 8px 6px 14px;
        }

        .composer textarea {
          min-height: 32px;
          padding: 6px 0;
        }

        .sendButton {
          width: 36px;
          height: 36px;
          flex-basis: 36px;
          border-radius: 12px;
        }

        .resultPanel .panelHeader h3,
        .approvalPanel .panelHeader h3 {
          color: #eef4ff;
        }

        .inputHint {
          width: min(940px, 100%);
          margin-top: 6px;
          font-size: 11px;
        }

        .emptyState {
          width: min(940px, 100%);
          margin: 0 auto;
        }

        .suggestions {
          max-width: 820px;
        }

        @media (max-width: 720px) {
          .chatViewport {
            padding-bottom: 14px;
          }

          .messageTurn.user .messageBody,
          .messageTurn.assistant .messageBody {
            max-width: 100%;
          }

          .inputArea {
            padding-top: 10px;
            padding-bottom: 12px;
          }
        }
      `}</style>
    </main>
  );
}

function AssistantResponseCard({
  response,
  approvalActionLoading,
  approvalActionMessage,
  approvalActionError,
  canApproveInline,
  onApproval,
}: {
  response: ChatResponse;
  approvalActionLoading: "approve" | "reject" | null;
  approvalActionMessage: string;
  approvalActionError: string;
  canApproveInline: boolean;
  onApproval: (decision: "approve" | "reject", response: ChatResponse) => void;
}) {
  const odooStockResult = normalizeOdooStockResult(response);
  const odooDocumentResult = normalizeOdooDocumentResult(response);
  const odooProductSearchResult = normalizeOdooProductSearchResult(response);
  const odooGenericRecordResult = normalizeOdooGenericRecordResult(response);
  const candidates = normalizeCandidates(response);
  const sources = normalizeSources(response);
  const approvalId = getApprovalId(response);
  const isApprovalPending = isPendingApprovalResponse(response);
  const isApprovalRequired =
    response.requires_approval === true || response.status === "pending_approval";

  const isOdooProductResult = Boolean(odooStockResult && !odooDocumentResult);
  const isOdooDocumentResult = Boolean(odooDocumentResult);
  const isOdooProductSearchResult = Boolean(odooProductSearchResult);
  const isOdooGenericRecordResult = Boolean(odooGenericRecordResult);

  const isSensitiveAction =
    response.status === "pending_approval" || isApprovalRequired;
  const isUnsupported = response.status === "unsupported";
  const isAccessDenied =
    response.status === "access_denied" ||
    response.status === "department_access_denied";
  const isSecurityBlocked =
    response.status === "blocked" ||
    response.technical?.risk === "blocked" ||
    response.technical?.agent === "security_agent" ||
    response.technical?.action === "blocked_sensitive_path";
  const needsClarification = response.status === "clarification_required";
  const statusLabel = formatStatus(response.status);
  const mainAnswer = getMainAnswer(response, {
    odooStockResult,
    odooDocumentResult,
    odooProductSearchResult,
    odooGenericRecordResult,
    statusLabel,
  });
  const showAnswerTitle = Boolean(
    mainAnswer.title &&
      !["Réponse", "Résultat", "Terminé"].includes(mainAnswer.title)
  );

  return (
    <>
      <section
        className={
          isSensitiveAction ? "approvalPanel resultAnchor" : "resultPanel resultAnchor"
        }
      >
        {showAnswerTitle && (
          <div className="panelHeader">
            <div>
              <h3>{mainAnswer.title}</h3>
            </div>
          </div>
        )}

        {isAccessDenied && <p className="genericMessage">{mainAnswer.message}</p>}

        {isSecurityBlocked && !isAccessDenied && !isUnsupported && (
          <p className="genericMessage">{mainAnswer.message}</p>
        )}

        {isUnsupported && !isAccessDenied && !isSecurityBlocked && (
          <p className="genericMessage">{mainAnswer.message}</p>
        )}

        {needsClarification && !isUnsupported && !isAccessDenied && !isSecurityBlocked && (
          <p className="genericMessage">{mainAnswer.message}</p>
        )}

        {isOdooProductResult && !isSensitiveAction && !isUnsupported && !isAccessDenied && !isSecurityBlocked && (
          <p className="genericMessage">{mainAnswer.message}</p>
        )}

        {isOdooProductSearchResult && !isSensitiveAction && !isUnsupported && !isAccessDenied && !isSecurityBlocked && (
          <p className="genericMessage">{mainAnswer.message}</p>
        )}

        {isOdooGenericRecordResult && !isSensitiveAction && !isUnsupported && !isAccessDenied && !isSecurityBlocked && (
          <p className="genericMessage">{mainAnswer.message}</p>
        )}

        {isOdooDocumentResult && !isSensitiveAction && !isUnsupported && !isAccessDenied && !isSecurityBlocked && (
          <p className="genericMessage">{mainAnswer.message}</p>
        )}

        {isSensitiveAction && !isUnsupported && !isAccessDenied && !isSecurityBlocked && (
          <>
            <div className="detailsTable">
              <Detail label="Action" value={getApprovalActionLabel(response)} />
              <Detail label="Élément concerné" value={getApprovalTarget(response)} />
              <Detail
                label="Valeur demandée"
                value={getApprovalRequestedValue(response)}
              />
              <Detail label="Statut" value={getApprovalStatusLabel(response)} />
              {getApprovalCreatedDate(response) && (
                <Detail label="Date" value={getApprovalCreatedDate(response)} />
              )}
            </div>

            {approvalActionMessage && (
              <p className="approvalNotice success">{approvalActionMessage}</p>
            )}

            {approvalActionError && (
              <p className="approvalNotice danger">{approvalActionError}</p>
            )}

            {approvalId && isApprovalPending && canApproveInline && (
              <div className="approvalActions">
                <button
                  type="button"
                  disabled={approvalActionLoading !== null}
                  onClick={() => void onApproval("approve", response)}
                >
                  {approvalActionLoading === "approve" ? "Validation..." : "Approuver"}
                </button>
                <button
                  className="reject"
                  type="button"
                  disabled={approvalActionLoading !== null}
                  onClick={() => void onApproval("reject", response)}
                >
                  {approvalActionLoading === "reject" ? "Refus..." : "Refuser"}
                </button>
              </div>
            )}

            {approvalId && isApprovalPending && !canApproveInline && (
              <p className="approvalNotice">
                Vous n’avez pas la permission de valider cette demande.
              </p>
            )}
          </>
        )}

        {!isOdooProductResult &&
          !isOdooProductSearchResult &&
          !isOdooGenericRecordResult &&
          !isOdooDocumentResult &&
          !isSensitiveAction &&
          !isUnsupported &&
          !isAccessDenied &&
          !isSecurityBlocked &&
          !needsClarification && (
            <p className="genericMessage">{mainAnswer.message}</p>
          )}

        {candidates.length > 0 && !isOdooProductSearchResult && (
          <div className="candidateBlock">
            <p className="eyebrow">Candidats</p>
            <div className="candidateList">
              {candidates.map((candidate, index) => (
                <div
                  className="candidateItem"
                  key={`${formatValue(candidate.id || candidate.record_id || candidate.line_id)}-${index}`}
                >
                  <Detail
                    label="ID"
                    value={formatValue(candidate.id || candidate.record_id || candidate.line_id)}
                  />
                  <Detail
                    label="Nom"
                    value={formatValue(candidate.name || candidate.product || candidate.product_name || candidate.partner)}
                  />
                  <Detail
                    label="Référence"
                    value={formatValue(candidate.default_code || candidate.ref)}
                  />
                  <Detail
                    label="Prix"
                    value={formatValue(candidate.list_price || candidate.price_unit)}
                  />
                  <Detail
                    label="Stock"
                    value={formatValue(candidate.qty_available || candidate.quantity)}
                  />
                </div>
              ))}
            </div>
          </div>
        )}

        {sources.length > 0 && (
          <div className="sourceBlock">
            <p className="eyebrow">Sources</p>
            <div className="sourceList">
              {sources.map((source, index) => (
                <div
                  className="sourceItem"
                  key={`${source.url || source.title || "source"}-${index}`}
                >
                  <span>{formatSourceLabel(source)}</span>
                  {source.url && (
                    <a href={source.url} target="_blank" rel="noreferrer">
                      Voir la source
                    </a>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}
      </section>

      {SHOW_TECHNICAL_DETAILS && (
        <details className="rawPanel">
          <summary>Détails techniques</summary>
          <TechnicalDetails response={response} />
        </details>
      )}
    </>
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

function TechnicalDetails({ response }: { response: ChatResponse }) {
  const technical = isLooseRecord(response.technical) ? response.technical : {};
  const selectedAgent = getStringValue(technical.agent);
  const technicalPayload = sanitizeForDisplay({
    ...technical,
    status: response.status,
    agent: selectedAgent,
  });

  return (
    <div className="detailsTable">
      <Detail label="Statut" value={formatStatus(response.status)} />
      <Detail label="Agent" value={formatAgentName(selectedAgent)} />
      <Detail label="Risque" value={formatRisk(getStringValue(technical.risk))} />
      <Detail
        label="Validation"
        value={
          response.requires_approval
            ? "Validation requise"
            : "Non requise"
        }
      />
      <Detail
        label="Source"
        value={formatParserSource(getStringValue(technical.parser_source))}
      />
      <Detail
        label="Action"
        value={translateAction(getStringValue(technical.capability) || getStringValue(technical.action))}
      />
      <Detail
        label="Données"
        value={formatTechnicalPayload(technicalPayload)}
      />
    </div>
  );
}

function isLooseRecord(value: unknown): value is LooseRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function createMessageId(prefix: string) {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function userInitial(user: AuthUser | null) {
  const source = user?.email || user?.role_label || "U";
  return source.trim().charAt(0).toUpperCase() || "U";
}

function getLatestAssistantModel(messages: ChatMessage[]) {
  const latest = [...messages]
    .reverse()
    .find((item) => item.role === "assistant" && item.response?.technical?.model);

  const model = latest?.response?.technical?.model;

  return isUserFacingModelLabel(model) ? model : "gpt-4.1-mini";
}

function isUserFacingModelLabel(value: unknown): value is string {
  if (typeof value !== "string") return false;

  const label = value.trim();
  const normalized = label.toLowerCase();

  if (!label) return false;

  return !(
    normalized.includes("policy") ||
    normalized.endsWith("_agent") ||
    normalized === "unknown"
  );
}

function getStringValue(value: unknown) {
  return typeof value === "string" ? value : "";
}

function getCanonicalResponseText(response: ChatResponse) {
  return response.response || "";
}

function getNestedRecord(record: LooseRecord, key: string): LooseRecord {
  const value = record[key];
  return isLooseRecord(value) ? value : {};
}

function getApprovalRecord(response: ChatResponse | null): LooseRecord {
  return response?.technical ? response.technical as LooseRecord : {};
}

function getApprovalMetadata(response: ChatResponse | null): LooseRecord {
  const approval = getApprovalRecord(response);
  return getNestedRecord(approval, "metadata");
}

function getApprovalId(response: ChatResponse | null) {
  if (!response) return "";

  return response.approval_id || "";
}

function getApprovalStatus(response: ChatResponse | null) {
  if (!response) return "";

  const approval = getApprovalRecord(response);

  return (
    getStringValue(approval.approval_status) ||
    response.status ||
    ""
  );
}

function isPendingApprovalStatus(status?: string) {
  const normalized = (status || "")
    .trim()
    .toLowerCase()
    .replace(/[_-]/g, " ");

  return [
    "pending",
    "pending approval",
    "requires approval",
    "en attente",
    "en attente de validation",
  ].includes(normalized);
}

function isPendingApprovalResponse(response: ChatResponse | null) {
  return Boolean(getApprovalId(response)) && isPendingApprovalStatus(getApprovalStatus(response));
}

function getApprovalActionLabel(response: ChatResponse) {
  const technical = response.technical || {};

  return translateAction(
    getStringValue(technical.approval_action) ||
      getStringValue(technical.capability) ||
      getStringValue(technical.action)
  );
}

function getApprovalTarget(response: ChatResponse) {
  return formatValue(response.technical?.approval_entity);
}

function getApprovalRequestedValue(response: ChatResponse) {
  return formatValue(response.technical?.approval_requested_change);
}

function getApprovalStatusLabel(response: ChatResponse) {
  return translateStatus(getApprovalStatus(response));
}

function getApprovalCreatedDate(response: ChatResponse) {
  return "";
}

function mergeApprovalResult(currentResult: unknown, updatedApproval: LooseRecord) {
  return sanitizeForDisplay(updatedApproval);
}

function formatApprovalActionError(error: unknown) {
  if (error instanceof ApiRequestError) {
    if (error.status === 401) return "Session expirée. Veuillez vous reconnecter.";
    if (error.status === 403) return "Accès refusé. Votre rôle ne permet pas cette action.";
    return API_ERROR_MESSAGE;
  }

  if (error instanceof TypeError) return BACKEND_UNREACHABLE_MESSAGE;

  return API_ERROR_MESSAGE;
}

function formatDateTime(value?: string) {
  if (!value) return "";

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";

  return new Intl.DateTimeFormat("fr-FR", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

function normalizeOdooStockResult(response: ChatResponse | null): OdooStockResult | null {
  return null;
}

function normalizeOdooProductSearchResult(
  response: ChatResponse | null
): OdooProductSearchResult | null {
  return null;
}

function normalizeOdooGenericRecordResult(
  response: ChatResponse | null
): OdooGenericRecordResult | null {
  return null;
}

function normalizeOdooDocumentResult(response: ChatResponse | null): OdooDocumentResult | null {
  return null;
}

function normalizeDocumentLines(value: unknown): LooseRecord[] {
  if (!Array.isArray(value)) return [];

  return value.filter(isLooseRecord);
}

function normalizeCandidates(response: ChatResponse | null): Candidate[] {
  return [];
}

function normalizeSources(response: ChatResponse | null): ChatSource[] {
  if (!Array.isArray(response?.sources)) return [];

  return response.sources
    .filter((source) => isLooseRecord(source))
    .map((source) => ({
      source_type: getStringValue(source.source_type),
      title: getStringValue(source.title),
      url: getStringValue(source.url),
      label: getStringValue(source.label),
    }))
    .filter((source) => source.title || source.url || source.label);
}

function formatSourceLabel(source: ChatSource) {
  if (source.label) return source.label;

  const title = source.title || source.url || "Source";

  if (source.source_type === "official_web") {
    return `Site officiel Jamain Baco — ${title}`;
  }

  if (source.source_type === "internal_document") {
    return `Document interne — ${title}`;
  }

  return title;
}

const SENSITIVE_DISPLAY_KEYS = new Set([
  "db",
  "database_name",
  "dbname",
  "url",
  "odoo_url",
  "database",
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
  "llm_project_env",
  "database_configured",
  "username_configured",
  "password_or_api_key_configured",
  "password_configured",
  "api_key_configured",
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
    (compact.includes("odoo") && compact.includes("url")) ||
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

function sanitizeTextForDisplay(value: string) {
  if (
    /api key|api_key|password|secret|token|\.env|xml-?rpc|traceback|odoo url|database name|username|uid/i.test(
      value
    )
  ) {
    return "[information masquée]";
  }

  return value;
}

function sanitizeForDisplay(value: unknown): unknown {
  if (Array.isArray(value)) {
    return value.map((item) => sanitizeForDisplay(item));
  }

  if (typeof value === "string") {
    return sanitizeTextForDisplay(value);
  }

  if (!isLooseRecord(value)) {
    return value;
  }

  return Object.fromEntries(
    Object.entries(value)
      .filter(([key]) => !isSensitiveDisplayKey(key))
      .map(([key, entry]) => [key, sanitizeForDisplay(entry)])
  );
}

function formatTechnicalPayload(value: unknown): string {
  const sanitized = sanitizeForDisplay(value);

  if (!isLooseRecord(sanitized)) {
    return formatValue(sanitized);
  }

  const lines = Object.entries(sanitized)
    .filter(([, entry]) => entry !== undefined && entry !== null && entry !== "")
    .map(([key, entry]) => `${formatTechnicalKey(key)}: ${formatTechnicalValue(entry)}`);

  return lines.length > 0 ? lines.join("\n") : "-";
}

function formatTechnicalKey(key: string) {
  const labels: Record<string, string> = {
    approval_status: "validation",
    parser_source: "source",
    parsed_action: "action",
    tool_used: "outil",
  };

  return labels[key] || key;
}

function formatTechnicalValue(value: unknown): string {
  if (Array.isArray(value)) {
    return value.map((item) => formatTechnicalValue(item)).join("; ");
  }

  if (isLooseRecord(value)) {
    return Object.entries(value)
      .filter(([, entry]) => entry !== undefined && entry !== null && entry !== "")
      .map(([key, entry]) => `${formatTechnicalKey(key)}=${formatTechnicalValue(entry)}`)
      .join(", ");
  }

  return formatValue(value);
}

function formatSafeOdooStatus(record: LooseRecord) {
  if (!("connected" in record) && !("mode" in record)) return "";

  const connected = record.connected === true;
  const mode = typeof record.mode === "string" ? record.mode : "-";
  const message = connected
    ? "Connexion réussie à Odoo"
    : "Connexion Odoo indisponible";

  return [
    `Connexion Odoo: ${connected ? "OK" : "Indisponible"}`,
    `Mode: ${mode}`,
    `Message: ${message}`,
  ].join(". ");
}

function mainResultTitle(
  response: ChatResponse,
  odooStockResult: OdooStockResult | null,
  statusLabel: string
) {
  if (response.status === "access_denied") return "Accès refusé";
  if (response.status === "department_access_denied") return "Accès refusé";
  if (
    response.technical?.risk === "blocked" ||
    response.technical?.agent === "security_agent" ||
    response.technical?.action === "blocked_sensitive_path"
  ) {
    return "Requête bloquée";
  }
  if (response.status === "clarification_required") return "Information requise";
  if (response.status === "pending_approval") return "Action nécessitant validation humaine";

  if (odooStockResult?.product) {
    return formatValue(odooStockResult.product);
  }

  const documentResult = normalizeOdooDocumentResult(response);

  if (documentResult?.document) {
    return formatValue(documentResult.document);
  }

  if (response.technical?.action === "inventory_summary") {
    return "Résumé inventaire";
  }

  if (response.technical?.agent === "server_agent") {
    if (response.technical?.action === "blocked_sensitive_path") return "Accès refusé";
    if (response.technical?.action === "list_internal_files") return "Fichiers du serveur interne";
    if (response.technical?.action === "create_internal_file") return "Fichier créé";
    if (response.technical?.action === "read_internal_file") return "Contenu du fichier";
  }

  return statusLabel;
}

function getMainAnswer(
  response: ChatResponse,
  {
    odooStockResult,
    odooDocumentResult,
    odooProductSearchResult,
    odooGenericRecordResult,
    statusLabel,
  }: {
    odooStockResult: OdooStockResult | null;
    odooDocumentResult: OdooDocumentResult | null;
    odooProductSearchResult: OdooProductSearchResult | null;
    odooGenericRecordResult: OdooGenericRecordResult | null;
    statusLabel: string;
  }
): MainAnswer {
  const safeMessage = cleanBusinessMessage(getCanonicalResponseText(response));

  if (
    response.status === "unsupported"
  ) {
    return {
      title: "Action non disponible",
      message:
        "Action non disponible. Cette demande n’est pas encore connectée à un outil backend sécurisé.",
    };
  }

  if (
    response.status === "access_denied" ||
    response.status === "department_access_denied"
  ) {
    return {
      title: "Accès refusé",
      message: "Accès refusé. Votre rôle ne permet pas cette action.",
    };
  }

  if (
    response.status === "blocked" ||
    response.technical?.risk === "blocked" ||
    response.technical?.agent === "security_agent" ||
    response.technical?.action === "blocked_sensitive_path"
  ) {
    return {
      title: "Requête bloquée",
      message: "Demande bloquée pour des raisons de sécurité.",
    };
  }

  if (response.status === "clarification_required") {
    return {
      title: "Précision requise",
      message:
        safeMessage || "Des informations sont nécessaires pour continuer.",
    };
  }

  if (
    response.status === "pending_approval" ||
    response.requires_approval === true
  ) {
    return {
      title: "Validation requise",
      message: "Validation requise",
    };
  }

  if (odooStockResult) {
    return {
      title: "Réponse",
      message: formatOdooStockAnswer(odooStockResult),
    };
  }

  if (odooProductSearchResult) {
    return {
      title: "Réponse",
      message: formatOdooProductSearchAnswer(odooProductSearchResult),
    };
  }

  if (odooGenericRecordResult) {
    return {
      title: "Réponse",
      message: formatOdooGenericRecordAnswer(odooGenericRecordResult),
    };
  }

  if (odooDocumentResult) {
    return {
      title: odooDocumentResult.document
        ? formatValue(odooDocumentResult.document)
        : "Détails du document Odoo",
      message:
        safeMessage ||
        "Le document Odoo a été consulté avec succès. Les champs principaux sont affichés ci-dessous.",
    };
  }

  if (isServerDiagnosticResponse(response)) {
    return {
      title: "Réponse",
      message: formatServerDiagnosticAnswer(response),
    };
  }

  return {
    title: isNormalTextAnswer(response) ? "Réponse" : mainResultTitle(response, odooStockResult, statusLabel),
    message: safeMessage || "Réponse générée par l’orchestrateur.",
  };
}

function isNormalTextAnswer(response: ChatResponse) {
  const technical = isLooseRecord(response.technical) ? response.technical : {};
  const selectedAgent = getStringValue(technical.agent);
  const action =
    getStringValue(technical.action) ||
    getStringValue(technical.tool_used) ||
    "";
  const textActions = new Set([
    "answer_question",
    "answer_general_question",
    "answer_knowledge_question",
    "knowledge_project_answer",
  ]);

  return (
    response.status === "completed" &&
    response.requires_approval !== true &&
    (selectedAgent === "knowledge_agent" ||
      selectedAgent === "general_agent" ||
      textActions.has(action))
  );
}

function isServerDiagnosticResponse(response: ChatResponse) {
  const technical = isLooseRecord(response.technical) ? response.technical : {};
  return getStringValue(technical.agent) === "server_agent";
}

function getResultRecord(response: ChatResponse): LooseRecord {
  return {};
}

function formatServerDiagnosticAnswer(response: ChatResponse) {
  return getCanonicalResponseText(response);
}

function formatOdooStockAnswer(stock: OdooStockResult) {
  return [
    `Produit: ${formatValue(stock.product)}`,
    `Stock disponible: ${formatNumber(stock.available_stock)}`,
    `Stock prévu: ${formatNumber(stock.forecast_stock)}`,
    `Prix: ${formatPrice(stock.sale_price)}`,
  ].join("\n");
}

function formatOdooProductSearchAnswer(search: OdooProductSearchResult) {
  const keyword = formatValue(search.keyword);

  if (!search.found || search.products.length === 0) {
    return `Aucun produit correspondant à "${keyword}" n’a été trouvé dans l’inventaire Odoo.`;
  }

  const lines = search.products.slice(0, 5).map((product) => {
    const name = formatValue(product.name || product.product || product.product_name);
    const details = [
      product.default_code || product.internal_reference
        ? `Référence interne: ${formatValue(product.default_code || product.internal_reference)}`
        : "",
      product.qty_available !== undefined || product.available_stock !== undefined || product.quantity !== undefined
        ? `Stock disponible: ${formatNumber(product.qty_available ?? product.available_stock ?? product.quantity)}`
        : "",
    ].filter(Boolean);

    return details.length > 0 ? `- ${name} | ${details.join(" | ")}` : `- ${name}`;
  });

  return [
    `Produits correspondant à "${keyword}" trouvés dans l’inventaire Odoo:`,
    ...lines,
  ].join("\n");
}

function formatOdooGenericRecordAnswer(result: OdooGenericRecordResult) {
  if (result.ambiguous) {
    return "Plusieurs enregistrements correspondent à votre demande. Veuillez préciser lequel choisir.";
  }

  if (!result.found) {
    return "Aucun enregistrement correspondant trouvé dans Odoo.";
  }

  const records = result.record ? [result.record] : result.records;
  const lines = records.slice(0, 5).map(formatGenericRecordLine);

  return ["Enregistrements Odoo trouvés:", ...lines].join("\n");
}

function formatGenericRecordLine(record: LooseRecord) {
  const name = formatValue(
    record.name ||
      record.document ||
      record.reference ||
      record.record ||
      record.id
  );
  const details = [
    record.internal_reference ? `Référence interne: ${formatValue(record.internal_reference)}` : "",
    record.stock_quantity !== undefined ? `Stock: ${formatNumber(record.stock_quantity)}` : "",
    record.forecast_quantity !== undefined ? `Stock prévu: ${formatNumber(record.forecast_quantity)}` : "",
    record.price !== undefined ? `Prix: ${formatPrice(record.price)}` : "",
    record.type ? `Type: ${formatValue(record.type)}` : "",
    record.phone ? `Téléphone: ${formatValue(record.phone)}` : "",
    record.email ? `Email: ${formatValue(record.email)}` : "",
    record.partner ? `Partenaire: ${formatValue(record.partner)}` : "",
    record.status ? `Statut: ${formatValue(record.status)}` : "",
    record.date ? `Date: ${formatValue(record.date)}` : "",
  ].filter(Boolean);

  return details.length > 0 ? `- ${name} | ${details.join(" | ")}` : `- ${name}`;
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
  const text = formatValue(value);

  if (/\b(dh|mad)\b/i.test(text)) return text;

  return `${text} DH`;
}

function formatAgentName(value?: string) {
  if (!value) return "Non sélectionné";

  const labels: Record<string, string> = {
    support: "Agent Support",
    support_agent: "Agent Support",
    knowledge: "Agent Connaissance",
    knowledge_agent: "Agent Connaissance",
    development: "Agent Développement",
    development_agent: "Agent Développement",
    security: "Agent Sécurité",
    security_agent: "Agent Sécurité",
    server: "Agent Serveur",
    server_agent: "Agent Serveur",
    odoo: "Agent Odoo",
    odoo_agent: "Agent Odoo",
    general: "Agent Général",
    general_agent: "Agent Général",
  };

  return labels[value] || value;
}

function formatAgentResult(value: unknown) {
  if (value === undefined || value === null || value === "") return "-";

  if (typeof value === "string") return sanitizeTextForDisplay(value);

  if (typeof value !== "object") return String(value);

  const rawRecord = value as LooseRecord;
  const safeOdooStatus = formatSafeOdooStatus(rawRecord);

  if (safeOdooStatus) return safeOdooStatus;

  const sanitized = sanitizeForDisplay(value);
  const record = sanitized as LooseRecord;
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

  if ("product_count" in record || "stockable_product_count" in record) {
    return [
      `Produits: ${formatValue(record.product_count)}`,
      `Produits vendables: ${formatValue(record.sale_product_count)}`,
      `Produits stockables: ${formatValue(record.stockable_product_count)}`,
      `Produits avec stock: ${formatValue(record.products_with_stock_count)}`,
      `Produits sans stock: ${formatValue(record.products_without_stock_count)}`,
      `Stock disponible total: ${formatValue(record.total_qty_available)}`,
      `Stock prévisionnel total: ${formatValue(record.total_virtual_available)}`,
    ].join(". ");
  }

  if (typeof record.answer === "string") {
    return record.answer;
  }

  return "Réponse générée par l’orchestrateur.";
}

function translateRisk(value?: string) {
  if (value === "low") return "Faible";
  if (value === "medium") return "Moyen";
  if (value === "high") return "Élevé";
  if (value === "blocked") return "Bloqué";
  return "Non évalué";
}

function formatRisk(value?: string) {
  return translateRisk(value);
}

function translateStatus(status?: string) {
  if (status === "allowed") return "Autorisé";
  if (status === "denied") return "Refusé";
  if (status === "requires_approval") return "Validation requise";
  if (status === "pending") return "En attente de validation";
  if (status === "approved") return "Approuvée";
  if (status === "rejected") return "Refusée";
  if (status === "completed" || status === "online") return "Terminé";
  if (status === "pending_approval") return "En attente de validation";
  if (status === "en attente" || status === "en attente de validation") {
    return "En attente de validation";
  }
  if (status === "access_denied") return "Accès refusé";
  if (status === "not_found") return "Introuvable";
  if (status === "failed" || status === "error") return "Échec";
  if (status === "blocked") return "Bloqué";
  if (!status) return "Traité";
  return status;
}

function formatStatus(status?: string) {
  return translateStatus(status);
}

function cleanBusinessMessage(value?: string) {
  if (!value) return "";

  if (
    /api key|password|secret|token|\.env|traceback|Knowledge Agent received|No specific tool matched|raw|provider error/i.test(
      value
    )
  ) {
    return "Réponse générée par l’orchestrateur.";
  }

  return value;
}

function formatParserSource(value?: string) {
  if (value === "openai") return "OpenAI";
  if (value === "support_fallback") return "Support local";
  if (value === "fallback" || value === "local_rules") return "Fallback local";
  if (value === "test") return "Test";
  return value || "-";
}

function translateAction(value?: string) {
  const labels: Record<string, string> = {
    check_product_stock: "Consultation stock",
    odoo_check_stock: "Consultation stock Odoo",
    odoo_get_product_details: "Consultation produit Odoo",
    odoo_search_products: "Recherche produit Odoo",
    inventory_product_search: "Vérification produit inventaire",
    odoo_search_sale_order: "Recherche commande client",
    odoo_search_purchase_order: "Recherche commande fournisseur",
    odoo_get_document_details_by_id: "Lecture document Odoo",
    odoo_get_purchase_order_details: "Lecture commande fournisseur",
    odoo_get_sale_order_details: "Lecture commande client",
    odoo_get_invoice_details: "Lecture facture",
    odoo_get_delivery_details: "Lecture livraison",
    support_knowledge_base: "Base de connaissance support",
    diagnose_printer_issue: "Diagnostic imprimante",
    diagnose_wifi_issue: "Diagnostic Wi-Fi",
    check_ram_usage: "Diagnostic RAM",
    check_cpu_usage: "Diagnostic CPU",
    check_disk_usage: "Diagnostic disque",
    check_server_health: "Diagnostic serveur",
    server_diagnostic_summary: "Synthèse serveur",
    product_search: "Recherche produit",
    inventory_product_lookup: "Vérification produit inventaire",
    product_details: "Détails produit",
    inventory_summary: "Résumé inventaire",
    update_product_price: "Modification du prix",
    document_search: "Recherche document",
    document_details: "Détails document",
    update_line_price: "Modification prix de ligne",
    update_line_quantity: "Modification quantité de ligne",
    update_partner: "Modification client/fournisseur",
    answer_it_question: "Réponse IT",
    troubleshoot_issue: "Diagnostic support",
    explain_procedure: "Explication procédure",
    list_internal_files: "Liste fichiers internes",
    read_internal_file: "Lecture fichier interne",
    create_internal_file: "Création fichier interne",
    server_status: "Statut serveur",
    blocked_sensitive_path: "Chemin sensible bloqué",
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
