# Limitations

This project is designed as a production-oriented enterprise AI orchestration platform, developed during an internship and structured around real enterprise requirements such as authentication, role-based access control, human approval, audit logging, Odoo integration, and secure execution boundaries.

## Current limitations

- Some Odoo queries are supported only for selected models.
- The approval workflow currently covers selected sensitive actions.
- Audit logs can be improved with persistent database storage.
- Chat history can be improved with backend persistence.
- Deployment can be improved with Docker and CI/CD.
- More enterprise systems can be connected in the future.

## Future work

- Generic Odoo query planner
- More advanced RBAC
- Persistent audit database
- Notification system for approvals
- Docker deployment
- CI/CD pipeline
- More robust monitoring
