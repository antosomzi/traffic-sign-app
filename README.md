# Application Flask + Celery + Redis - Pipeline ML

Web application for uploading, validating, and asynchronously processing recordings through an ML pipeline.

## 🏗️ Architecture

- **Flask**: Web interface, upload, extraction and validation of ZIP archives
- **Redis**: 
  - Message broker for Celery task queue
  - Shared state storage for extraction progress (across Gunicorn workers)
- **Celery**: Asynchronous worker for ML pipeline processing
- **Gunicorn**: Production WSGI server with 4 worker processes
- **Shared filesystem**: Storage for uploads and results

### Multi-Worker Architecture

The application uses **Gunicorn with 4 workers** for production. Since each worker has its own memory space, Redis is used to share the extraction progress state between workers:

```
Request 1 (Upload) → Worker #1 → Creates extraction progress in Redis
Request 2 (Status) → Worker #3 → Reads extraction progress from Redis ✅
Request 3 (Status) → Worker #2 → Reads extraction progress from Redis ✅
```

Without Redis, each worker would have its own `extraction_progress = {}` dictionary, causing 404 errors when different workers handle the status requests.

## 📁 Project Structure

```
app/
├── app.py                      # Main Flask application
├── celery_app.py               # Celery configuration
├── tasks.py                    # Asynchronous tasks
├── simulate_pipeline.sh        # Pipeline simulation script
├── requirements.txt            # Python dependencies
├── .env                        # Environment variables (not in git)
├── DEPLOYMENT.md               # Deployment guide for EC2
├── templates/
│   ├── upload.html            # Upload interface
│   └── status.html            # Status tracking
└── README.md                  # This file
```

## 🚀 Local Installation

### 1. Clone the repository

```bash
git clone <your-repo-url>
cd app
```

### 2. Create virtual environment

```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 3. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 4. Install and start Redis

**On macOS (with Homebrew):**
```bash
brew install redis
redis-server
```

**On Ubuntu/Debian:**
```bash
sudo apt-get install redis-server
sudo systemctl start redis
```

**On Windows:**
- Download Redis from https://redis.io/download
- Or use WSL2

### 5. Configure environment variables (optional for local dev)

```bash
# Create .env file (already exists with defaults)
cp .env.example .env  # If you want to customize
```

For local development, you can run without password. For production, see `DEPLOYMENT.md`.

### 6. Make the simulation script executable

```bash
chmod +x simulate_pipeline.sh
```

## 🎯 Démarrage

Ouvrez **3 terminaux** et exécutez les commandes suivantes :

### Terminal 1 - Redis
```bash
redis-server
```

### Terminal 2 - Celery Worker
```bash
celery -A tasks worker --loglevel=INFO
```

### Terminal 3 - Flask App
```bash
python app.py
```

L'application sera accessible sur : **http://localhost:5000**

## 📝 Utilisation

### 1. Upload d'un enregistrement

1. Accédez à `http://localhost:5000`
2. Glissez-déposez ou sélectionnez un fichier ZIP
3. Cliquez sur "Télécharger et valider"
4. L'application va :
   - Extraire le ZIP
   - Valider la structure
   - Ajouter une tâche Celery si valide

### 2. Suivi des traitements

- Cliquez sur "Voir les statuts des enregistrements"
- Vous verrez tous les enregistrements avec leur statut
- La page se rafraîchit automatiquement toutes les 10 secondes

### 3. Téléchargement des résultats

- Une fois le traitement terminé, un bouton "Télécharger les résultats" apparaît
- Le téléchargement contient les fichiers `supports.csv` et `signs.csv`

## 🗂️ Structure de données attendue

```
<recording_id>/
└── <device_id>/
    └── <imei_folder>/
        ├── acceleration/
        │   └── <recording_id>_acc.csv
        ├── calibration/
        │   └── *_calibration.csv (au moins 1)
        ├── camera/
        │   ├── <recording_id>_cam_<recording_id>.mp4
        │   └── camera_params.csv
        ├── location/
        │   ├── <recording_id>_loc.csv
        │   └── <recording_id>_loc_cleaned.csv
        └── processed/
            ├── <recording_id>_processed_acc.csv
            └── <recording_id>_processed_loc.csv
```

## 📊 Pipeline de traitement

La pipeline comporte 8 étapes :

1. **s0_detection** - Détection initiale
2. **s1_small_sign_filter** - Filtrage des petits panneaux
3. **s2_tracking** - Suivi des objets
4. **s3_small_track_filter** - Filtrage des petites trajectoires
5. **s4_classification** - Classification des panneaux
6. **s5_frames_gps_coordinates_extraction** - Extraction des coordonnées GPS
7. **s6_localization** - Localisation
8. **s7_export_csv** - Export CSV final

## 🔧 Configuration

### Redis for Extraction Progress

Redis stores extraction progress as JSON strings with the following structure:

**Redis Key Format:**
```
extraction:<job_id>
```

**Value (JSON):**
```json
{
  "status": "running",           // "queued", "running", "done", "error"
  "total_files": 250,             // Total files in ZIP
  "extracted_files": 120,         // Files extracted so far
  "extract_size": 1024000,        // Final size in bytes (null until done)
  "recording_id": "2024_05_...",  // Recording ID (null until done)
  "error_msg": null,              // Error message if status="error"
  "error_details": null           // Detailed error info (dict)
}
```

**TTL (Time To Live):** 1 hour (3600 seconds) - Redis automatically deletes old entries

**Update Frequency:** Progress is updated every 10 files during extraction to optimize performance.

### Helper Functions

```python
# Read from Redis (JSON string → Python dict)
prog = get_extraction_progress(job_id)

# Write to Redis (Python dict → JSON string)
set_extraction_progress(job_id, progress_dict)

# Modify in Python (standard dict operations)
prog["status"] = "running"
prog["extracted_files"] += 1
```

### File Paths

Les chemins par défaut sont configurés pour EC2 dans `/home/ec2-user/`:

- `uploads/` - Fichiers uploadés
- `temp_extracts/` - Extraction temporaire
- `recordings/` - Enregistrements validés

Pour modifier, éditez les constantes dans `app.py` et `tasks.py`.

## 🐛 Dépannage

### Redis ne démarre pas
```bash
# Vérifier si Redis tourne
redis-cli ping
# Devrait retourner "PONG"

# Sur EC2 avec mot de passe
redis6-cli -a Moulines1 ping
```

### Vérifier les données Redis
```bash
# Voir toutes les clés extraction
redis6-cli -a Moulines1 KEYS "extraction:*"

# Voir le contenu d'une clé
redis6-cli -a Moulines1 GET "extraction:abc123..."

# Voir le temps restant avant expiration
redis6-cli -a Moulines1 TTL "extraction:abc123..."

# Supprimer une clé manuellement
redis6-cli -a Moulines1 DEL "extraction:abc123..."

# Vider toute la base Redis (ATTENTION!)
redis6-cli -a Moulines1 FLUSHDB
```

### Problème de barre de progression bloquée

Si la barre de progression reste à 0% puis saute à 100% :
- **Cause**: Le dictionnaire `extraction_progress` n'est pas partagé entre workers Gunicorn
- **Solution**: Redis est maintenant utilisé pour partager l'état entre workers ✅

### Celery ne trouve pas les tâches
```bash
# Vérifier que vous êtes dans le bon répertoire
celery -A celery_app inspect active

# Vérifier que tasks.py est bien importé dans celery_app.py
grep "import tasks" celery_app.py
```

### Erreur "Command 'bash' not found" (Celery)

Si Celery ne trouve pas `bash` lors de l'exécution de `simulate_pipeline.sh` :
- **Cause**: La variable `PATH` n'est pas définie dans le service systemd
- **Solution**: Ajouter `Environment="PATH=/usr/bin:/bin"` dans `/etc/systemd/system/celery-worker.service`

```ini
[Service]
Environment="PATH=/home/ec2-user/app/venv/bin:/usr/local/bin:/usr/bin:/bin"
```

### Problèmes de permissions
```bash
# Donner les permissions au script
chmod +x simulate_pipeline.sh
```

## 📌 Notes importantes

- La simulation de pipeline prend environ **40 secondes** (5 sec par étape)
- Le worker Celery traite les tâches **séquentiellement**
- Les fichiers ZIP sont supprimés après extraction réussie
- En cas d'erreur de validation, tout est nettoyé automatiquement
- **Redis stocke les progrès d'extraction pendant 1 heure** (TTL = 3600s)
- **Gunicorn utilise 4 workers** en production pour gérer les requêtes simultanées
- **La barre de progression se met à jour toutes les 10 fichiers** pour optimiser les performances
- **Le frontend poll le status toutes les 300ms** pour une progression fluide

### Pourquoi Redis pour l'extraction progress ?

Avec Gunicorn (4 workers), chaque worker a sa propre mémoire. Sans Redis :
- Worker #1 extrait le ZIP et stocke `extraction_progress[job_id]` dans **sa mémoire**
- Worker #2 reçoit une requête `/extract_status/<job_id>` mais ne voit **rien** dans sa mémoire → 404 !

Avec Redis :
- Worker #1 écrit dans Redis : `SET extraction:job_id {...}`
- Worker #2, #3, #4 lisent depuis Redis : `GET extraction:job_id` → ✅ Partagé !

## 🔐 Sécurité

- Protection contre les attaques **ZipSlip**
- Validation stricte de la structure des fichiers
- Limite de taille : **8 GB**
- Types de fichiers autorisés : ZIP, TAR, TAR.GZ, TGZ

## 📈 Évolutions possibles

- [ ] Ajouter plusieurs workers Celery pour le parallélisme
- [ ] Implémenter l'authentification utilisateur
- [ ] Ajouter des notifications par email
- [ ] Logger les événements dans une base de données
- [ ] Ajouter un monitoring avec Flower (interface Celery)
