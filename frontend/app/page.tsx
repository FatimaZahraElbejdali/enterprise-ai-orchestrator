import Link from "next/link";

export default function Home() {
  const workflow = [
    "Intent Classification",
    "Agent Routing",
    "Model Selection",
    "Approval Workflow",
    "Audit Logging",
    "Enterprise Systems",
  ];

  const cards = [
    {
      title: "Chat",
      description:
        "Envoyer une demande à l’orchestrateur et visualiser le routage vers les agents.",
      status: "Active",
      href: "/chat",
    },
    {
      title: "Approbations",
      description:
        "Consulter et gérer les demandes nécessitant une validation humaine.",
      status: "Workflow",
      href: "/approvals",
    },
    {
      title: "Journaux d’audit",
      description:
        "Suivre les actions, décisions et réponses générées par le système.",
      status: "Traceability",
      href: "/logs",
    },
    {
      title: "Odoo",
      description:
        "Vérifier l’état de l’intégration ERP et consulter les stocks produits.",
      status: "ERP",
      href: "/odoo",
    },
  ];

  return (
    <main className="min-h-screen bg-gradient-to-br from-slate-950 via-slate-950 to-slate-900 text-white">
      <div className="max-w-7xl mx-auto px-8 py-10">
        <header className="mb-12">
          <p className="text-sm text-cyan-400 font-medium mb-2">
            Enterprise AI Platform
          </p>

          <h1 className="text-5xl font-bold tracking-tight mb-4">
            Enterprise AI Orchestrator
          </h1>

          <p className="text-slate-400 text-lg max-w-3xl mb-8">
            Couche d’IA entre les employés et les systèmes de l’entreprise.
          </p>

          <div className="flex flex-wrap gap-3">
            {workflow.map((item) => (
              <span
                key={item}
                className="rounded-full bg-slate-900/80 px-4 py-2 text-sm text-slate-300 border border-slate-800"
              >
                {item}
              </span>
            ))}
          </div>
        </header>

        <section className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {cards.map((card) => (
            <Link key={card.title} href={card.href}>
              <div className="group rounded-2xl border border-slate-800 bg-slate-900/80 p-6 shadow-lg shadow-black/20 transition hover:-translate-y-1 hover:border-cyan-500/40 cursor-pointer">
                <div className="flex items-start justify-between mb-6">
                  <h2 className="text-2xl font-semibold">{card.title}</h2>

                  <span className="rounded-full bg-slate-800 px-3 py-1 text-xs text-slate-300">
                    {card.status}
                  </span>
                </div>

                <p className="text-slate-400 mb-6">{card.description}</p>

                <span className="text-sm font-medium text-cyan-400 group-hover:text-cyan-300">
                  Ouvrir →
                </span>
              </div>
            </Link>
          ))}
        </section>
      </div>
    </main>
  );
}