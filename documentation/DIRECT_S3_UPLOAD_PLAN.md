# Plan d'Implémentation : Upload 100% S3 (Vidéo et GPS via Pre-signed URLs)

Ce document détaille l'architecture où **l'intégralité** des fichiers d'un enregistrement (Vidéo et données GPS) est envoyée directement sur Amazon S3 par le client mobile, sans passer par le serveur.

## 1. Nouvelle Architecture et Flux de Données

1. **Initialisation (Client -> Serveur)** : `POST /upload/init`
   - Le mobile envoie le `recording_id` et la liste des fichiers prévus (ex: `video.mp4`, `gps_data.json`).
   - Le serveur génère **une Pre-signed URL par fichier** et les retourne au client.
2. **Upload Direct (Client -> S3)** :
   - Le mobile upload les fichiers directement sur AWS via les URLs fournies (peut être fait en parallèle).
3. **Confirmation (Client -> Serveur)** : `POST /upload/complete`
   - Le mobile confirme que tous les uploads S3 sont terminés.
   - Le serveur crée l'entrée en base de données (si ce n'est pas déjà fait) et ajoute une tâche Celery.
4. **Traitement (Celery Worker)** :
   - Le worker télécharge le GPS et la Vidéo depuis S3 vers le stockage local (EFS).
   - Il reconstitue l'arborescence requise : `recordings/<recording_id>/camera/video.mp4` et `recordings/<recording_id>/gps/gps_data.json`.
   - Il lance le pipeline d'intelligence artificielle habituel.

---

## 2. Modifications Backend (API & Services)

### A. S3 Service (`services/sign_app/s3_service.py`)
- Ajouter la méthode `generate_presigned_post(s3_key)` pour générer les URLs temporaires (avec une limite de taille appropriée, ex: 5GB pour la vidéo, 50MB pour le GPS).
- Mettre à jour les méthodes de téléchargement pour gérer n'importe quel fichier lié à un enregistrement.

### B. Routes (`routes/sign_app/upload_routes.py`)
- **Créer `POST /upload/init`** :
  - Reçoit : `{"recording_id": "2024_06_15_...", "files": ["video.mp4", "gps.json"]}`.
  - Vérifie les droits et l'existence du `recording_id`.
  - Retourne les Pre-signed URLs générées via S3.
- **Créer/Modifier `POST /upload/complete`** :
  - Reçoit la confirmation.
  - Enregistre le statut "En attente de traitement" et lance la tâche Celery.
- **Supprimer (à terme) l'ancienne route ZIP** (`POST /upload`).

---

## 3. Modifications Backend (Celery & Pipeline)

### `pipeline/celery_tasks.py`
- Modifier la logique de préparation : avant de lancer `simulate_pipeline.sh`, le worker **doit** s'assurer que tous les fichiers nécessaires sont téléchargés depuis S3.
- Créer une fonction `prepare_local_environment_from_s3(recording_id)` qui :
  1. Crée le dossier `recordings/<recording_id>`.
  2. Télécharge S3:`<prefix>/<recording_id>/video.mp4` vers `.../camera/video.mp4`.
  3. Télécharge S3:`<prefix>/<recording_id>/gps.json` vers `.../gps/gps.json`.

---

## 4. Script de Migration (Données Existantes)

Puisque S3 devient la source de vérité pour tous les fichiers (plus seulement la vidéo), il faut migrer les fichiers GPS actuellement stockés localement sur l'EFS vers S3.

**Nouveau script : `migrations/sign_app/migrate_gps_to_s3.py`**
- **Logique** :
  1. Parcourir le dossier local `recordings/`.
  2. Pour chaque dossier (qui correspond au `recording_id`) :
     - Vérifier que le préfixe (dossier S3) existe déjà dans S3.
     - Chercher le dossier `gps/` et les fichiers qu'il contient (ex: `data.json`, `gps.csv`).
     - Uploader ces fichiers vers S3 sous le préfixe `<prefix>/<recording_id>/<nom_du_fichier>`.
- *Note : L'architecture S3 reflètera l'ID d'enregistrement, rendant la correspondance directe avec l'ancien système local parfaite.*

### Exécution en Production

Afin d'éviter de modifier le code de manière permanente (et faciliter une éventuelle resynchronisation future), le script est programmé pour tourner en **dry run par défaut**. 

**1. Tester la migration (Dry Run) :**
```bash
source venv/bin/activate
python migrations/sign_app/migrate_gps_to_s3.py
```

**2. Exécuter la migration réelle (SANS modifier le fichier) :**
Pour effectuer la migration pour de vrai (`dry_run=False`), exécutez la commande en ligne suivante :
```bash
source venv/bin/activate
python -c "from migrations.sign_app.migrate_gps_to_s3 import migrate_gps_files; migrate_gps_files(dry_run=False)"
```
Cela permet d'appliquer les changements sans altérer le comportement par défaut de sécurité du script.

---

## 5. Modifications Mobile (Client)

- Remplacer la logique de compression ZIP par une logique d'upload multi-fichiers.
- Implémenter le chaînage d'appels API :
  1. `Init` -> Récupération des URLs.
  2. Upload S3 natif (avec gestion de la progression).
  3. `Complete`.

---

## 6. Avantages et Robustesse
- **S3 comme Backup Absolu** : Même si le serveur EFS crash, aucune donnée utilisateur n'est perdue.
- **Serveur Flask Soulagé à 100%** : Flask ne gère plus que du JSON très léger. Finis les problèmes de timeout ou de RAM saturée.
- **Parité Client/Serveur** : Code asynchrone beaucoup plus propre sur mobile (pas d'opération lourde de compression).
- **Reprise sur erreur (Retry)** : Si un pipeline plante côté serveur, le serveur a toujours les fichiers sources intacts sur S3 pour retenter.
