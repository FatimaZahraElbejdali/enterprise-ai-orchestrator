"use client";

import { useState } from "react";
import Link from "next/link";

type ChatResponse = {
  intent?: string;
  risk_level?: string;
  classification_confidence?: number;
  selected_agent?: string;
  selected_model?: string;
  execution_plan?: string[];
  approval_required?: boolean;
  approval_status?: string;
  classifier_source?: string;
  classifier_error?: string;
  approval?: unknown;
  agent_result?: {
    agent?: string;
    tool_used?: string;
    result?: {
      diagnosis?: string;
      suggested_steps?: string[];
      [key: string]: unknown;
    };
    [key: string]: unknown;
  };
  response?: string;
};

export default function ChatPage() {
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<ChatResponse | null>(null);
  const [error, setError] = useState("");

  async function sendMessage() {
    if (!message.trim()) return;

    setLoading(true);
    setError("");
    setResult(null);

    try {
      const response = await fetch("http://localhost:8000/chat", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ message }),
      });

      if (!response.ok) {
        throw new Error("Backend request failed");
      }

      const data = await response.json();
      setResult(data);
    } catch {
      setError("Impossible de contacter le backend FastAPI.");
    } finally {
      setLoading(false);
    }
  }

  function handleKeyDown(event: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      sendMessage();
    }
  }

  return (
    <main className="min-h-screen bg-gradient-to-br from-slate-950 via-slate-950 to-slate-900 text-white">
      <div className="max-w-6xl mx-auto px-8 py-10">
        <Link href="/" className="text-sm text-cyan-400 hover:text-cyan-300">
          ← Retour au tableau de bord
        </Link>

        <header className="mt-8 mb-10">
          <p className="text-sm text-cyan-400 font-medium mb-2">
            Orchestrator Chat
          </p>

          <h1 className="text-4xl font-bold tracking-tight mb-3">Chat</h1>

          <p className="text-slate-400 text-lg">
            Comment puis-je vous aider ?
          </p>
        </header>

        <section className="max-w-4xl mb-8">
          <div className="rounded-2xl border border-slate-800 bg-slate-900/80 p-4 shadow-lg shadow-black/20">
            <div className="flex flex-col gap-3 md:flex-row md:items-end">
              <textarea
                rows={2}
                className="flex-1 resize-none rounded-xl border border-slate-800 bg-slate-950 p-4 text-white placeholder:text-slate-500 outline-none transition focus:border-cyan-500"
                placeholder="Décrivez votre demande..."
                value={message}
                onChange={(event) => setMessage(event.target.value)}
                onKeyDown={handleKeyDown}
              />

              <button
                onClick={sendMessage}
                disabled={loading || !message.trim()}
                className="h-[58px] rounded-xl bg-cyan-500 px-6 text-sm font-semibold text-slate-950 transition hover:bg-cyan-400 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {loading ? "Envoi..." : "Envoyer"}
              </button>
            </div>

            {error && <p className="mt-4 text-sm text-red-400">{error}</p>}
          </div>
        </section>

        {result && (
          <section className="space-y-6">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <InfoCard label="Intent" value={result.intent} />
              <InfoCard label="Risk Level" value={result.risk_level} />
              <InfoCard
                label="Confidence"
                value={
                  result.classification_confidence !== undefined
                    ? `${Math.round(result.classification_confidence * 100)}%`
                    : "-"
                }
              />
              <InfoCard label="Agent" value={result.selected_agent} />
              <InfoCard label="Model" value={result.selected_model} />
              <InfoCard
                label="Approval"
                value={result.approval_required ? "Required" : "Not required"}
              />
            </div>

            {result.execution_plan && result.execution_plan.length > 0 && (
              <div className="rounded-2xl border border-slate-800 bg-slate-900/80 p-6 shadow-lg shadow-black/20">
                <h2 className="text-2xl font-semibold mb-4">
                  Execution Plan
                </h2>

                <ol className="space-y-3">
                  {result.execution_plan.map((step, index) => (
                    <li key={index} className="flex gap-3 text-slate-300">
                      <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-cyan-500/10 text-sm font-semibold text-cyan-400">
                        {index + 1}
                      </span>

                      <span>{step}</span>
                    </li>
                  ))}
                </ol>
              </div>
            )}

            <div className="rounded-2xl border border-slate-800 bg-slate-900/80 p-6 shadow-lg shadow-black/20">
              <h2 className="text-2xl font-semibold mb-4">Agent Result</h2>

              <div className="space-y-3 text-slate-300">
                <p>
                  <span className="text-slate-500">Approval status: </span>
                  {result.approval_status || "-"}
                </p>

                <p>
                  <span className="text-slate-500">Tool used: </span>
                  {result.agent_result?.tool_used || "-"}
                </p>

                {result.agent_result?.result?.diagnosis && (
                  <p>
                    <span className="text-slate-500">Diagnosis: </span>
                    {result.agent_result.result.diagnosis}
                  </p>
                )}

                {result.agent_result?.result?.suggested_steps && (
                  <div>
                    <p className="text-slate-500 mb-2">Suggested steps:</p>
                    <ul className="list-disc list-inside space-y-1">
                      {result.agent_result.result.suggested_steps.map(
                        (step, index) => (
                          <li key={index}>{step}</li>
                        )
                      )}
                    </ul>
                  </div>
                )}
              </div>
            </div>

            <details className="rounded-2xl border border-slate-800 bg-slate-900/80 p-6 shadow-lg shadow-black/20">
              <summary className="cursor-pointer text-xl font-semibold">
                Raw Response
              </summary>

              <pre className="mt-4 overflow-x-auto rounded-xl bg-slate-950 p-4 text-sm text-slate-300">
                {JSON.stringify(result, null, 2)}
              </pre>
            </details>
          </section>
        )}
      </div>
    </main>
  );
}

function InfoCard({
  label,
  value,
}: {
  label: string;
  value?: string | number | boolean;
}) {
  return (
    <div className="rounded-2xl border border-slate-800 bg-slate-900/80 p-5 shadow-lg shadow-black/20">
      <p className="text-slate-400 text-sm mb-2">{label}</p>
      <p className="text-xl font-semibold">{String(value ?? "-")}</p>
    </div>
  );
}