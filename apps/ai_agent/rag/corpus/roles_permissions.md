# Rôles et permissions du système

## Hiérarchie des rôles

Le système FSB définit cinq rôles avec des permissions croissantes. Le rôle scolarité gère les inscriptions, les dossiers étudiants et la saisie des notes. Le rôle admin ajoute la gestion des enseignants, la planification des examens et la validation des stages. Le rôle chef de département supervise les filières et les résultats de son département uniquement. Le rôle doyen dispose d'un accès en lecture à l'ensemble des données et valide les décisions disciplinaires. Le rôle super admin administre les comptes utilisateurs et la configuration du système.

## Permissions de l'agent IA

L'agent conversationnel applique les mêmes règles de permission que l'interface classique. La recherche d'étudiants et les statistiques sont accessibles aux rôles scolarité, admin, chef de département et doyen. La création d'étudiants est réservée aux rôles scolarité, admin et super admin. La planification d'examens via l'agent est réservée aux rôles admin et super admin. Toute action refusée pour permission insuffisante est journalisée.

## Protection des données personnelles

Les données sensibles des étudiants (CIN, adresse, téléphone) ne sont affichées qu'aux agents habilités et jamais transmises à l'agent IA dans le contexte de conversation. Les numéros étudiants et noms peuvent être cités dans les réponses de l'agent. Toute extraction massive de données nécessite l'autorisation du responsable de traitement.

## Journalisation et audit

Chaque action de création, modification ou suppression est enregistrée dans le journal d'audit avec l'identité de l'auteur, l'horodatage et l'objet concerné. Les métriques de l'agent IA (temps de réponse, outils appelés, taux de succès) sont consultables par les administrateurs sur le tableau de bord dédié.
