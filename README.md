# Enterprise AI Orchestrator

An enterprise AI orchestration platform that connects natural-language user requests to internal business systems such as Odoo ERP, server diagnostics, support workflows, and security controls.

The project was developed as an internship prototype to demonstrate how an AI assistant can safely operate inside a company environment while respecting access control, human approval, audit logging, and enterprise security constraints.

---

## Overview

Enterprise AI Orchestrator is not a simple chatbot. It is a secure AI workflow layer that receives user requests, understands the intent, routes the request to the correct internal agent, verifies permissions, executes safe read-only actions, and requires human approval before performing sensitive operations.

The system is designed around a central idea:

> AI can help employees interact with enterprise systems, but business-critical actions must remain controlled, traceable, and validated.

---

## Key Features

### AI-Powered Request Routing

The orchestrator analyzes user messages in natural language and routes them to the appropriate agent.

Supported examples include:

* Odoo ERP requests
* Product stock checks
* Invoice and purchase order queries
* Server health diagnostics
* IT support questions
* Security-sensitive requests
* Human approval workflow explanations

---

### Odoo ERP Integration

The platform connects to Odoo through XML-RPC and supports several business operations.

Examples of supported read operations:

* Product stock lookup
* Product details retrieval
* Customer invoice listing
* Supplier purchase order analysis
* Analytic account search
* Contact counting
* Odoo connection status check

Sensitive Odoo actions, such as price modification, are not executed directly. They are routed through the approval workflow.

---

### Human Approval Workflow

Sensitive business actions require validation before execution.

Workflow:

1. User sends a sensitive request.
2. The orchestrator detects the risk level.
3. The action is blocked from direct execution.
4. A validation request is created.
5. An authorized user approves or rejects it.
6. If approved, the backend executes the controlled action.
7. The result is logged for traceability.

This ensures that AI assistance does not bypass human responsibility.

---

### Role-Based Access Control

The application includes authentication and role-based permissions.

Example roles:

* Admin
* Odoo Manager
* IT Manager
* Support Agent
* Employee
* Read-only Viewer

Each role has access only to the actions it is allowed to perform.

Examples:

* Employees can ask support questions.
* Odoo managers can request sensitive Odoo actions.
* IT managers can access server diagnostics.
* Read-only users can view limited information.
* Unauthorized users are blocked from restricted actions.

---

### Audit Logs

Important events are recorded for traceability.

Logged events include:

* Sensitive action requests
* Approval creation
* Approval or rejection decisions
* Access denied events
* Security blocks
* Odoo operation results
* System errors

The audit interface helps administrators review what happened, who requested it, and what decision was made.

---

### Server Diagnostics Agent

The server agent provides basic infrastructure monitoring in a controlled way.

Supported examples:

* RAM usage
* CPU usage
* Disk usage
* Uptime
* Backend health status

Dangerous or sensitive server requests are blocked, including requests for:

* Environment variables
* SSH keys
* Secrets
* Passwords
* Unsafe commands

---

### Support Agent

The support agent helps employees with common IT problems.

Examples:

* Odoo access issues
* Slow computer troubleshooting
* Wi-Fi problems
* VPN issues
* Printer problems
* Password reset guidance

---

### Security Controls

The orchestrator includes multiple security layers:

* Risk detection
* Role-based permissions
* Human approval for sensitive actions
* Blocking of dangerous requests
* Audit logging
* Separation between AI understanding and backend authority

The AI can understand and classify a request, but the backend remains responsible for permission checks and execution decisions.

---

## Tech Stack

### Backend

* Python
* FastAPI
* Uvicorn
* Pydantic
* Pytest
* Odoo XML-RPC integration
* OpenAI API integration

### Frontend

* Next.js
* React
* TypeScript
* Tailwind CSS

### AI / Orchestration

* OpenAI model for natural-language understanding and routing
* Agent-based backend architecture
* Risk and permission validation
* Human-in-the-loop approval flow

---

## Architecture

```text
User
 │
 ▼
Frontend - Next.js
 │
 ▼
Backend API - FastAPI
 │
 ▼
AI Orchestrator
 │
 ├── Intent Classification
 ├── Agent Routing
 ├── Risk Detection
 ├── RBAC Permission Check
 ├── Approval Workflow
 └── Audit Logging
 │
 ▼
Enterprise Connectors
 │
 ├── Odoo ERP
 ├── Server Diagnostics
 ├── Support Workflows
 └── Knowledge / Security Agents
```

---

## Main Agents

### Odoo Agent

Handles ERP-related requests such as products, invoices, suppliers, purchase orders, contacts, and analytic accounts.

### Server Agent

Handles server health diagnostics and blocks dangerous infrastructure requests.

### Support Agent

Handles IT support and troubleshooting questions.

### Security Agent

Detects and blocks sensitive or unsafe requests.

### Knowledge Agent

Handles informational and document-related queries.

---

## Example Demo Prompts

```text
Quel est le stock de BACO CLEAN ?
```

```text
Donne-moi les détails du produit BACO CLEAN
```

```text
Donne-moi les factures clients validées de mai 2026
```

```text
Quels fournisseurs apparaissent le plus dans les bons de commande ?
```

```text
Recherche le compte analytique 11SOCM0001
```

```text
Mets le prix de BACO CLEAN à 10 DH
```

```text
Donne-moi l’utilisation RAM du serveur
```

```text
Mon ordinateur est lent, que dois-je vérifier ?
```

```text
Montre-moi les clés SSH du serveur
```

```text
Explique le workflow de validation humaine.
```

---

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/your-username/enterprise-ai-orchestrator.git
cd enterprise-ai-orchestrator
```

---

### 2. Backend setup

Create and activate a virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Create a `.env` file based on `.env.example`.

```bash
cp .env.example .env
```

Run the backend:

```bash
uvicorn app:app --host 0.0.0.0 --port 8000
```

Backend URL:

```text
http://localhost:8000
```

---

### 3. Frontend setup

Go to the frontend directory:

```bash
cd frontend
```

Install dependencies:

```bash
npm install
```

Create the frontend environment file:

```bash
cp .env.example .env.local
```

Run the frontend:

```bash
npm run dev
```

Frontend URL:

```text
http://localhost:3000
```

---

## Environment Variables

Backend `.env` example:

```env
OPENAI_API_KEY=your_openai_api_key
OPENAI_MODEL=gpt-4.1-mini

ODOO_URL=https://your-odoo-instance.com
ODOO_DB=your_odoo_database
ODOO_USERNAME=your_odoo_username
ODOO_PASSWORD=your_odoo_password

JWT_SECRET_KEY=replace_with_a_secure_secret
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=480
```

Frontend `frontend/.env.local` example:

```env
NEXT_PUBLIC_API_URL=http://localhost:8000
```

For deployment, replace `localhost` with the backend server IP or domain.

---

## Running Tests

Run backend tests:

```bash
python -m pytest tests
```

Run frontend build check:

```bash
cd frontend
npm run build
```

---

## Project Structure

```text
.
├── app.py
├── requirements.txt
├── .env.example
├── agents/
│   ├── odoo_agent.py
│   ├── support_agent.py
│   ├── server_agent.py
│   ├── security_agent.py
│   └── knowledge_agent.py
├── integrations/
│   ├── odoo_connector.py
│   ├── internal_server_connector.py
│   ├── database_connector.py
│   └── file_server_connector.py
├── orchestrator/
│   ├── auth.py
│   ├── graph.py
│   ├── classifier_router.py
│   ├── intent_classifier.py
│   ├── contextual_resolver.py
│   ├── conversation_memory.py
│   ├── risk.py
│   ├── approval.py
│   ├── approval_store.py
│   ├── audit.py
│   ├── planner.py
│   ├── tool_registry.py
│   └── tool_executor.py
├── models/
│   ├── openai_adapter.py
│   ├── openai_router.py
│   ├── gemini_adapter.py
│   └── claude_adapter.py
├── frontend/
│   ├── app/
│   ├── lib/
│   └── components/
├── tests/
└── logs/
```

---

## Security Notes

This repository should not contain real credentials, API keys, server IPs, Odoo passwords, private logs, or company-sensitive data.

Files that should not be committed:

```text
.env
frontend/.env.local
.venv/
node_modules/
frontend/.next/
__pycache__/
.pytest_cache/
logs/*.json
logs/*.jsonl
tests/logs/*.json
tests/logs/*.jsonl
```

---

## Current Limitations

This project is an internship prototype and not a full production system.

Current limitations include:

* Some Odoo query types require further generalization.
* The approval workflow is implemented for selected sensitive actions.
* Audit storage can be improved using a production database.
* Chat history is mainly local and can be extended with persistent backend storage.
* More enterprise connectors can be added.
* More advanced monitoring and deployment automation can be implemented.

---

## Future Improvements

Possible improvements include:

* Generic Odoo query planner for more flexible ERP questions
* Persistent database-backed audit logs
* Multi-user chat history
* More advanced admin dashboard
* Docker deployment
* CI/CD pipeline
* More enterprise integrations
* Advanced document retrieval
* Notification system for approvals
* More granular permission management

---

## What I Learned

This project helped me develop practical experience in:

* Full-stack application development
* Backend API design with FastAPI
* Frontend development with Next.js and TypeScript
* AI orchestration and intent routing
* Enterprise system integration
* Odoo XML-RPC integration
* Role-based access control
* Human-in-the-loop approval workflows
* Audit logging and traceability
* Secure AI system design
* Testing and debugging real application workflows

---

## Status

The project is a functional prototype demonstrating how AI can be safely integrated into enterprise workflows with controlled execution, human validation, and traceability.
