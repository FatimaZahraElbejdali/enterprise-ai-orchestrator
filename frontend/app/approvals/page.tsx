"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

type Approval = {
  id: string;
  timestamp?: string;
  status: string;
  user_message?: string;
  intent?: string;
  selected_agent?: string;
  selected_model?: string;
};

export default function ApprovalsPage() {
  const [approvals, setApprovals] = useState<Approval[]>([]);
  const [loading, setLoading] = useState(true);

  async function loadApprovals() {
    const response = await fetch("http://localhost:8000/approvals");
    const data = await response.json();

    const sortedApprovals = [...data].sort((a, b) => {
      const dateA = new Date(a.timestamp || 0).getTime();
      const dateB = new Date(b.timestamp || 0).getTime();
      return dateB - dateA;
    });

    setApprovals(sortedApprovals);
    setLoading(false);
  }

  async function updateApproval(id: string, action: "approve" | "reject") {
    await fetch(`http://localhost:8000/approvals/${id}/${action}`, {
      method: "POST",
    });

    await loadApprovals();
  }

  useEffect(() => {
    loadApprovals();
  }, []);

  return (
    <main className="min-h-screen bg-gradient-to-br from-slate-950 via-slate-950 to-slate-900 text-white">
      <div className="max-w-6xl mx-auto px-8 py-10">
        <Link href="/" className="text-sm text-cyan-400 hover:text-cyan-300">
          ← Retour au tableau de bord
        </Link>

        <header className="mt-8 mb-8">
          <p className="text-sm text-cyan-400 font-medium mb-2">
            Human Approval Workflow
          </p>

          <h1 className="text-4xl font-bold tracking-tight mb-3">
            Approbations
          </h1>

          <p className="text-slate-400 text-lg">
            Consulter et gérer les demandes nécessitant une validation humaine.
          </p>
        </header>

        {loading ? (
          <p className="text-slate-400">Chargement...</p>
        ) : approvals.length === 0 ? (
          <div className="rounded-2xl border border-slate-800 bg-slate-900/80 p-6">
            <p className="text-slate-400">Aucune demande d’approbation.</p>
          </div>
        ) : (
          <section className="space-y-4">
            {approvals.map((approval) => (
              <div
                key={approval.id}
                className="rounded-2xl border border-slate-800 bg-slate-900/80 p-6 shadow-lg shadow-black/20"
              >
                <div className="flex flex-col gap-6 md:flex-row md:items-start md:justify-between">
                  <div>
                    <div className="mb-3 flex items-center gap-3">
                      <h2 className="text-2xl font-semibold">
                        {approval.intent || "Unknown"}
                      </h2>

                      <span className="rounded-full bg-slate-800 px-3 py-1 text-xs text-slate-300">
                        {approval.status}
                      </span>
                    </div>

                    <p className="mb-4 text-slate-400">
                      {approval.user_message || "No message"}
                    </p>

                    <div className="space-y-1 text-sm text-slate-300">
                      <p>
                        <span className="text-slate-500">Agent: </span>
                        {approval.selected_agent || "-"}
                      </p>

                      <p>
                        <span className="text-slate-500">Model: </span>
                        {approval.selected_model || "-"}
                      </p>

                      <p>
                        <span className="text-slate-500">Timestamp: </span>
                        {approval.timestamp
                          ? new Date(approval.timestamp).toLocaleString()
                          : "-"}
                      </p>
                    </div>
                  </div>

                  {approval.status === "pending" && (
                    <div className="flex gap-3">
                      <button
                        onClick={() => updateApproval(approval.id, "approve")}
                        className="rounded-xl bg-emerald-500 px-4 py-2 text-sm font-semibold text-slate-950 transition hover:bg-emerald-400"
                      >
                        Approve
                      </button>

                      <button
                        onClick={() => updateApproval(approval.id, "reject")}
                        className="rounded-xl bg-red-500 px-4 py-2 text-sm font-semibold text-white transition hover:bg-red-400"
                      >
                        Reject
                      </button>
                    </div>
                  )}
                </div>
              </div>
            ))}
          </section>
        )}
      </div>
    </main>
  );
}