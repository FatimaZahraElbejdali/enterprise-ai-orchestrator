"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

type AuditLog = {
  user_message?: string;
  intent?: string;
  risk_level?: string;
  classification_confidence?: number;
  selected_agent?: string;
  selected_model?: string;
  approval_required?: boolean;
  approval_status?: string;
  approval_id?: string | null;
  classifier_source?: string;
  classifier_error?: string | null;
  execution_plan?: string[];
  timestamp?: string;
};

export default function LogsPage() {
  const [logs, setLogs] = useState<AuditLog[]>([]);
  const [loading, setLoading] = useState(true);

  async function loadLogs() {
    const response = await fetch("http://localhost:8000/logs");
    const data = await response.json();

    const sortedLogs = [...data].reverse();

    setLogs(sortedLogs);
    setLoading(false);
  }

  useEffect(() => {
    loadLogs();
  }, []);

  return (
    <main className="min-h-screen bg-gradient-to-br from-slate-950 via-slate-950 to-slate-900 text-white">
      <div className="max-w-6xl mx-auto px-8 py-10">
        <Link href="/" className="text-sm text-cyan-400 hover:text-cyan-300">
          ← Retour au tableau de bord
        </Link>

        <header className="mt-8 mb-8">
          <p className="text-sm text-cyan-400 font-medium mb-2">
            Audit Trail
          </p>

          <h1 className="text-4xl font-bold tracking-tight mb-3">
            Journaux d’audit
          </h1>

          <p className="text-slate-400 text-lg">
            Suivre les actions, décisions et réponses générées par le système.
          </p>
        </header>

        {loading ? (
          <p className="text-slate-400">Chargement...</p>
        ) : logs.length === 0 ? (
          <div className="rounded-2xl border border-slate-800 bg-slate-900/80 p-6">
            <p className="text-slate-400">Aucun journal trouvé.</p>
          </div>
        ) : (
          <section className="space-y-4">
            {logs.map((log, index) => (
              <div
                key={index}
                className="rounded-2xl border border-slate-800 bg-slate-900/80 p-6 shadow-lg shadow-black/20"
              >
                <div className="mb-4 flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                  <div>
                    <h2 className="text-xl font-semibold mb-2">
                      {log.intent || "Unknown intent"}
                    </h2>

                    <p className="text-slate-400">
                      {log.user_message || "No message"}
                    </p>
                  </div>

                  <span className="rounded-full bg-slate-800 px-3 py-1 text-xs text-slate-300">
                    {log.approval_status || "logged"}
                  </span>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-sm text-slate-300">
                  <p>
                    <span className="text-slate-500">Risk: </span>
                    {log.risk_level || "-"}
                  </p>

                  <p>
                    <span className="text-slate-500">Agent: </span>
                    {log.selected_agent || "-"}
                  </p>

                  <p>
                    <span className="text-slate-500">Model: </span>
                    {log.selected_model || "-"}
                  </p>

                  <p>
                    <span className="text-slate-500">Approval: </span>
                    {log.approval_required ? "Required" : "Not required"}
                  </p>

                  <p>
                    <span className="text-slate-500">Classifier: </span>
                    {log.classifier_source || "-"}
                  </p>

                  <p>
                    <span className="text-slate-500">Confidence: </span>
                    {log.classification_confidence !== undefined
                      ? `${Math.round(log.classification_confidence * 100)}%`
                      : "-"}
                  </p>
                </div>

                {log.execution_plan && log.execution_plan.length > 0 && (
                  <div className="mt-4 rounded-xl bg-slate-950/70 p-4">
                    <p className="mb-2 text-sm text-slate-500">
                      Execution Plan
                    </p>

                    <ol className="space-y-2 text-sm text-slate-300">
                      {log.execution_plan.map((step, stepIndex) => (
                        <li key={stepIndex}>
                          {stepIndex + 1}. {step}
                        </li>
                      ))}
                    </ol>
                  </div>
                )}
              </div>
            ))}
          </section>
        )}
      </div>
    </main>
  );
}