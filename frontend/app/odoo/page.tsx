"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

type OdooStatus = {
  connected?: boolean;
  mode?: string;
  url?: string;
  database?: string;
  database_configured?: boolean;
  username?: string;
  username_configured?: boolean;
  password_or_api_key_configured?: boolean;
  message?: string;
  [key: string]: unknown;
};

type StockResult = {
  source?: string;
  mode?: string;
  product?: string;
  product_name?: string;
  stock_quantity?: number;
  stock?: number;
  quantity?: number;
  available_qty?: number;
  unit?: string;
  warehouse?: string;
  status?: string;
  message?: string;
  [key: string]: unknown;
};

export default function OdooPage() {
  const [status, setStatus] = useState<OdooStatus | null>(null);
  const [productName, setProductName] = useState("");
  const [stockResult, setStockResult] = useState<StockResult | null>(null);
  const [loadingStatus, setLoadingStatus] = useState(true);
  const [loadingStock, setLoadingStock] = useState(false);
  const [error, setError] = useState("");

  async function checkStock() {
    if (!productName.trim()) return;

    setLoadingStock(true);
    setError("");
    setStockResult(null);

    try {
      const response = await fetch(
        `http://localhost:8000/odoo/stock/${encodeURIComponent(productName)}`
      );

      if (!response.ok) {
        throw new Error("Stock request failed");
      }

      const data = await response.json();
      setStockResult(data);
    } catch {
      setError("Impossible de consulter le stock.");
    } finally {
      setLoadingStock(false);
    }
  }

  useEffect(() => {
    let cancelled = false;

    fetch("http://localhost:8000/odoo/status")
      .then((response) => response.json())
      .then((data) => {
        if (!cancelled) {
          setStatus(data);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setError("Impossible de contacter le connecteur Odoo.");
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoadingStatus(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, []);

  const displayedStock =
    stockResult?.stock_quantity ??
    stockResult?.stock ??
    stockResult?.quantity ??
    stockResult?.available_qty ??
    "-";

  return (
    <main className="min-h-screen bg-gradient-to-br from-slate-950 via-slate-950 to-slate-900 text-white">
      <div className="max-w-6xl mx-auto px-8 py-10">
        <Link href="/" className="text-sm text-cyan-400 hover:text-cyan-300">
          ← Retour au tableau de bord
        </Link>

        <header className="mt-8 mb-8">
          <p className="text-sm text-cyan-400 font-medium mb-2">
            ERP Integration
          </p>

          <h1 className="text-4xl font-bold tracking-tight mb-3">Odoo</h1>

          <p className="text-slate-400 text-lg">
            Vérifier l’état de l’intégration ERP et consulter les stocks produits.
          </p>
        </header>

        <section className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div className="rounded-2xl border border-slate-800 bg-slate-900/80 p-6 shadow-lg shadow-black/20">
            <div className="mb-5 flex items-center justify-between">
              <h2 className="text-2xl font-semibold">État de connexion</h2>

              <span className="rounded-full bg-slate-800 px-3 py-1 text-xs text-slate-300">
                {status?.mode || "loading"}
              </span>
            </div>

            {loadingStatus ? (
              <p className="text-slate-400">Chargement...</p>
            ) : (
              <div className="space-y-4 text-slate-300">
                <StatusRow
                  label="Connected"
                  value={status?.connected ? "Yes" : "No"}
                />

                <StatusRow label="Mode" value={status?.mode || "-"} />

                <StatusRow label="URL" value={String(status?.url || "-")} />

                <StatusRow
                  label="Database configured"
                  value={status?.database_configured ? "Yes" : "No"}
                />

                <StatusRow
                  label="Username configured"
                  value={status?.username_configured ? "Yes" : "No"}
                />

                <StatusRow
                  label="Credentials configured"
                  value={
                    status?.password_or_api_key_configured ? "Yes" : "No"
                  }
                />

                <div className="rounded-xl bg-slate-950/70 p-4">
                  <p className="mb-1 text-sm text-slate-500">Message</p>
                  <p className="text-sm text-slate-300">
                    {status?.message || "-"}
                  </p>
                </div>
              </div>
            )}
          </div>

          <div className="rounded-2xl border border-slate-800 bg-slate-900/80 p-6 shadow-lg shadow-black/20">
            <h2 className="text-2xl font-semibold mb-4">
              Consultation du stock
            </h2>

            <div className="flex flex-col gap-3 md:flex-row">
              <input
                className="flex-1 rounded-xl border border-slate-800 bg-slate-950 p-4 text-white placeholder:text-slate-500 outline-none transition focus:border-cyan-500"
                placeholder="Nom du produit..."
                value={productName}
                onChange={(event) => setProductName(event.target.value)}
              />

              <button
                onClick={checkStock}
                disabled={loadingStock || !productName.trim()}
                className="rounded-xl bg-cyan-500 px-6 py-3 text-sm font-semibold text-slate-950 transition hover:bg-cyan-400 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {loadingStock ? "Recherche..." : "Vérifier"}
              </button>
            </div>

            {stockResult && (
              <div className="mt-6 rounded-xl border border-slate-800 bg-slate-950/70 p-5">
                <div className="mb-4 flex items-center justify-between">
                  <p className="text-sm text-slate-500">Résultat</p>

                  <span className="rounded-full bg-slate-800 px-3 py-1 text-xs text-slate-300">
                    {stockResult.mode || stockResult.source || "result"}
                  </span>
                </div>

                <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                  <div>
                    <p className="text-sm text-slate-500">Produit</p>
                    <p className="text-xl font-semibold">
                      {stockResult.product ||
                        stockResult.product_name ||
                        productName}
                    </p>
                  </div>

                  <div>
                    <p className="text-sm text-slate-500">Stock disponible</p>
                    <p className="text-xl font-semibold">{displayedStock}</p>
                  </div>

                  <div>
                    <p className="text-sm text-slate-500">Unité</p>
                    <p className="text-xl font-semibold">
                      {stockResult.unit || "-"}
                    </p>
                  </div>

                  <div>
                    <p className="text-sm text-slate-500">Entrepôt</p>
                    <p className="text-xl font-semibold">
                      {stockResult.warehouse || "-"}
                    </p>
                  </div>
                </div>

                {stockResult.message && (
                  <p className="mt-4 text-sm text-slate-400">
                    {stockResult.message}
                  </p>
                )}

                {stockResult.source === "mock_odoo" && (
                  <p className="mt-4 text-xs text-amber-300">
                    Données mockées en attendant les identifiants Odoo réels.
                  </p>
                )}
              </div>
            )}
          </div>
        </section>

        {error && <p className="mt-6 text-sm text-red-400">{error}</p>}
      </div>
    </main>
  );
}

function StatusRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between border-b border-slate-800 pb-3">
      <span className="text-sm text-slate-500">{label}</span>
      <span className="text-sm font-medium text-slate-300">{value}</span>
    </div>
  );
}