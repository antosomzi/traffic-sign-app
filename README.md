# Application Flask + Celery + Redis - Pipeline ML

Web application for uploading, validating, and asynchronously processing recordings through an ML pipeline.

## 🏗️ Architecture

- **Flask**: Web interface, upload, extraction and validation of ZIP archives
- **Redis**: Message broker for Celery task queue
- **Celery**: Asynchronous worker for ML pipeline processing
- **Shared filesystem**: Storage for uploads and results

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
```

### Celery ne trouve pas les tâches
```bash
# Vérifier que vous êtes dans le bon répertoire
celery -A tasks inspect active
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
