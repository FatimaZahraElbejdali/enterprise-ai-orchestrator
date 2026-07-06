"use client";

import { FormEvent, useState } from "react";
import Image from "next/image";
import { API_BASE_URL, BACKEND_UNREACHABLE_MESSAGE, storeAuth } from "@/lib/api";

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(() => {
    if (typeof window === "undefined") return "";

    const authError = window.localStorage.getItem("auth_error") || "";
    window.localStorage.removeItem("auth_error");
    return authError;
  });

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setLoading(true);
    setError("");

    try {
      const response = await fetch(`${API_BASE_URL}/auth/login`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          email,
          password,
        }),
      });

      if (!response.ok) {
        setError("Identifiants incorrects.");
        return;
      }

      const data = await response.json();
      storeAuth(data.access_token, data.user);
      window.location.href = "/chat";
    } catch {
      setError(BACKEND_UNREACHABLE_MESSAGE);
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="loginShell">
      <section className="loginPanel">
        <div className="brand">
          <div className="brandMark">
            <Image
              className="brandLogo"
              src="/jamain-baco-logo.png"
              alt="Jamain Baco"
              width={44}
              height={44}
            />
          </div>
          <div>
            <p>Jamain Baco</p>
            <h1>Connexion</h1>
          </div>
        </div>

        <form onSubmit={handleSubmit}>
          <label htmlFor="email">Adresse e-mail</label>
          <input
            id="email"
            type="email"
            placeholder="Entrez votre adresse e-mail"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            autoComplete="email"
          />

          <label htmlFor="password">Mot de passe</label>
          <input
            id="password"
            type="password"
            placeholder="Entrez votre mot de passe"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            autoComplete="current-password"
          />

          {error && <p className="errorText">{error}</p>}

          <button type="submit" disabled={loading}>
            {loading ? "Connexion..." : "Se connecter"}
          </button>
        </form>
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

        .loginShell {
          min-height: 100vh;
          display: grid;
          place-items: center;
          padding: 24px;
          background: #f4f6f8;
        }

        .loginPanel {
          width: min(420px, 100%);
          background: #ffffff;
          border: 1px solid #d9dee7;
          padding: 28px;
        }

        .brand {
          display: flex;
          align-items: center;
          gap: 14px;
          margin-bottom: 28px;
        }

        .brandMark {
          width: 52px;
          height: 52px;
          background: #ffffff;
          display: grid;
          place-items: center;
          flex: 0 0 52px;
        }

        .brandLogo {
          width: 44px;
          height: 44px;
          object-fit: contain;
          display: block;
        }

        .brand p {
          margin: 0 0 4px;
          color: #647084;
          font-size: 12px;
          text-transform: uppercase;
          letter-spacing: 0.09em;
          font-weight: 800;
        }

        .brand h1 {
          margin: 0;
          font-size: 24px;
        }

        form {
          display: grid;
          gap: 12px;
        }

        label {
          font-size: 13px;
          font-weight: 800;
          color: #334155;
        }

        input {
          min-height: 44px;
          border: 1px solid #cbd5e1;
          padding: 0 12px;
          font-size: 15px;
        }

        button {
          min-height: 44px;
          border: 0;
          background: #101827;
          color: #ffffff;
          font-weight: 800;
          cursor: pointer;
        }

        button:disabled {
          opacity: 0.65;
          cursor: not-allowed;
        }

        .errorText {
          margin: 0;
          color: #b42318;
          font-weight: 800;
          font-size: 13px;
        }
      `}</style>
    </main>
  );
}
