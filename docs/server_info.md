# Informations serveur — Démo Enterprise AI Orchestrator

## Objectif

Le serveur interne est utilisé pour héberger et tester l’Enterprise AI Orchestrator.  
Il permet d’exécuter le backend FastAPI, le frontend Next.js et les connecteurs vers les systèmes internes comme Odoo.

## Services principaux

### Backend API

- Technologie : FastAPI / Python
- Port local : 8000
- Rôle : recevoir les requêtes du chat, router vers les agents, appliquer les règles de sécurité, gérer les validations et communiquer avec Odoo.
- Documentation API : /docs

### Frontend

- Technologie : Next.js / React
- Port local : 3000
- Rôle : interface utilisateur pour le chat, Odoo, les validations et les logs.

### Stockage interne

- Dossier contrôlé : ./storage
- Rôle : stocker des fichiers texte de démonstration accessibles par l’agent serveur.
- Restrictions : l’agent ne peut pas lire .env, les chemins absolus ou les chemins contenant ..

### Logs

- Dossier : ./logs
- Rôle : stocker les journaux d’audit et les demandes de validation.
- Les fichiers générés ne doivent pas être versionnés sur GitHub.

## Agents disponibles

### Odoo Agent

Gère les demandes liées à Odoo :
- consultation de stock
- résumé inventaire
- recherche produit
- recherche document
- modification de prix avec validation humaine
- blocage des demandes ambiguës

### Support Agent

Gère les questions IT :
- problème d’accès Odoo
- Wi-Fi
- ordinateur lent
- VPN
- diagnostic utilisateur

### Server Agent

Gère les demandes liées au serveur interne :
- lister les fichiers autorisés
- créer un fichier texte dans le stockage interne
- lire un fichier autorisé
- bloquer les chemins sensibles

## Règles de sécurité

- Ne jamais exposer les clés API.
- Ne jamais lire ou afficher le fichier .env.
- Ne jamais afficher les mots de passe.
- Les actions sensibles dans Odoo nécessitent une validation humaine.
- Les chemins comme ../.env sont bloqués.
- Les logs servent à assurer la traçabilité.

## Exemples de questions serveur

- Liste les fichiers du serveur interne
- Lis le fichier serveur server_info.md
- Quel est le rôle du backend ?
- Quels services composent l’application ?
- Où sont stockés les logs ?
- Pourquoi l’accès à .env est-il bloqué ?

