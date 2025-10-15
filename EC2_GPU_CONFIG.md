# Configuration EC2 GPU Instance pour Pipeline ML

## 🏗️ Architecture - Deux Instances

### Instance 1️⃣ - Instance PRINCIPALE (Flask/Celery) - Permanente
**Rôle**: Lance et gère les instances GPU
- Tourne en permanence 24/7
- Héberge Flask + Celery + Redis
- **C'EST CETTE INSTANCE QUI A BESOIN DU IAM ROLE** pour lancer l'instance GPU
- Monte l'EFS avec les recordings

**⚠️ INFORMATIONS DE CETTE INSTANCE À COLLECTER (voir section "Informations Manquantes")**

---

### Instance 2️⃣ - Instance GPU - Temporaire (À Lancer Dynamiquement)
**Rôle**: Exécute le pipeline ML avec GPU
- N'existe pas encore
- Sera lancée automatiquement par l'Instance 1 quand une tâche arrive
- Exécute `simulate_pipeline.sh`
- S'éteint automatiquement après exécution
- Monte le même EFS pour accéder aux recordings

**✅ INFORMATIONS COLLECTÉES CI-DESSOUS**

## 📋 Informations Collectées - Instance GPU (Instance 2️⃣)

#### AMI
- **AMI ID**: `ami-0d67eb9a9a933bd88`
- **Nom AMI**: Deep Learning Base OSS Nvidia Driver GPU AMI (Amazon Linux 2023) 20241206
- **Propriétaire**: 222634388391
- **Plateforme**: Linux/UNIX
- **Type de virtualisation**: hvm
- **Mode de démarrage**: uefi-preferred
- **Mode de démarrage actuel**: uefi

#### Configuration Réseau
- **Région AWS**: `us-east-2`
- **Zone de disponibilité**: `us-east-2b`
- **VPC ID**: `vpc-0933dfb2c976a7d1b`
- **Subnet ID**: `subnet-098dc7573fb6bf8bd`
- **Security Groups**:
  - `sg-0906d54ac3d704022` (ec2-rds-1)
  - `sg-0fc71fc185fe9b5e6` (Traffic Sign Inventory)

#### Clés et Sécurité
- **Paire de clés**: `traffic-sign-inventory_keypair`
- **Protection de la résiliation**: Désactivé
- **Protection contre l'arrêt**: Désactivé

#### Monitoring
- **Surveillance CloudWatch**: Désactivé
- **Migration au redémarrage**: Activé (Par défaut)
- **Récupération automatique**: Par défaut

#### Stockage
- **Périphérique racine**: `/dev/xvda`
- **Type de périphérique racine**: EBS
- **Optimisation EBS**: Activé

#### Autre
- **vCPU (donnés)**: 4
- **Autoriser identifications dans métadonnées**: Désactivé
- **Comportement Arrêt - Mise en veille**: Désactivé

---

## ✅ Informations Collectées - Instance PRINCIPALE (Instance 1️⃣)

### Instance Flask/Celery/Redis - Informations Complètes

#### Identification
- **Instance ID**: `i-02c72a6ed2e3c27b8`
- **Type d'instance**: `t3.large` (2 vCPU, 8 GB RAM)
- **État**: En cours d'exécution ✅
- **ARN**: `arn:aws:ec2:us-east-2:222634388391:instance/i-02c72a6ed2e3c27b8`

#### Réseau
- **Région**: `us-east-2`
- **Zone de disponibilité**: `us-east-2b`
- **VPC ID**: `vpc-0933dfb2c976a7d1b`
- **Subnet ID**: `subnet-098dc7573fb6bf8bd`
- **IPv4 publique**: `18.222.211.193`
- **IPv4 privée**: `172.31.30.12`
- **DNS public**: `ec2-18-222-211-193.us-east-2.compute.amazonaws.com`
- **DNS privé**: `ip-172-31-30-12.us-east-2.compute.internal`

#### Sécurité
- **Security Groups**:
  - `sg-0906d54ac3d704022` (ec2-rds-1)
  - `sg-0fc71fc185fe9b5e6` (Traffic Sign Inventory)
- **IAM Role**: ❌ **AUCUN** (à créer - voir section "Configuration IAM" ci-dessous)
- **IMDSv2**: Required

#### Configuration Réseau
✅ **BONNE NOUVELLE**: L'instance principale et l'instance GPU partagent **exactement la même configuration réseau** !
- Même VPC: `vpc-0933dfb2c976a7d1b`
- Même Subnet: `subnet-098dc7573fb6bf8bd`
- Mêmes Security Groups: `sg-0906d54ac3d704022`, `sg-0fc71fc185fe9b5e6`
- Même Zone: `us-east-2b`

**Avantage**: Configuration simplifiée, communication optimale entre les instances

#### Point de Montage EFS
- **Chemin attendu**: `/home/ec2-user/recordings` (d'après le code)
- **À vérifier en SSH**: `df -h /home/ec2-user/recordings`

---

## ❓ Informations Optionnelles - Instance GPU (Instance 2️⃣)

### 1. Type d'Instance GPU (Instance 2️⃣) ✅ SÉLECTIONNÉ
**Question**: Quel type d'instance GPU voulez-vous lancer ?

**Options populaires**:
- `g6e.xlarge` - 4 vCPU, 16 GB RAM, 1x NVIDIA L4 GPU (~$0.70/heure) ⭐ **SÉLECTIONNÉ**
- `g4dn.xlarge` - 4 vCPU, 16 GB RAM, 1x NVIDIA T4 GPU (~$0.526/heure)
- `g4dn.2xlarge` - 8 vCPU, 32 GB RAM, 1x NVIDIA T4 GPU (~$0.752/heure)
- `g5.xlarge` - 4 vCPU, 16 GB RAM, 1x NVIDIA A10G GPU (~$1.006/heure)
- `g5.2xlarge` - 8 vCPU, 32 GB RAM, 1x NVIDIA A10G GPU (~$1.212/heure)
- `p3.2xlarge` - 8 vCPU, 61 GB RAM, 1x NVIDIA V100 GPU (~$3.06/heure)

**Choix configuré dans le code**: `g6e.xlarge` (modifiable dans `gpu_config.py`)

### 2. Dépendances Python sur Instance GPU (Instance 2️⃣) ✅ COMPLÉTÉ
**Question**: Le script `simulate_pipeline.sh` nécessite-t-il des packages Python spécifiques ?

**Réponse**: ❌ **NON** - Le script est un script bash simple qui ne nécessite pas de packages Python spécifiques.

**Vérification**: Le script `simulate_pipeline.sh` utilise uniquement des commandes bash standard (mkdir, echo, sleep) et ne fait pas appel à Python.

**L'AMI Deep Learning inclut déjà**:
- PyTorch, TensorFlow, MXNet
- CUDA, cuDNN
- Jupyter, NumPy, Pandas, OpenCV
- Etc.

**Note**: Si le vrai pipeline ML (non-simulé) nécessite des packages supplémentaires, ils pourront être installés automatiquement au démarrage de l'instance GPU via un fichier `requirements_gpu.txt`.

---

## 📦 Configuration Partagée (Les Deux Instances)

### Filesystem Partagé EFS ✅ COMPLÉTÉ
**Type**: EFS (Elastic File System)

**Détails**:
- **Nom EFS**: `traffic-sign_efs`
- **EFS ID**: `fs-0fdfeb8ca8304e991`
- **Région**: `us-east-2`
- **État**: Disponible
- **Chiffrement**: Activé ✅
- **Taille utilisée**: 47.96 Gio
- **Date de création**: Mon, 09 Dec 2024 20:17:22 GMT
- **DNS Name**: `fs-0fdfeb8ca8304e991.efs.us-east-2.amazonaws.com`

**Montage sur les deux instances**:
- **Instance Principale (Flask)**: `/home/ec2-user/recordings` (à vérifier)
- **Instance GPU**: `/home/ec2-user/recordings` (même point de montage)

**Note**: Les deux instances doivent monter le même EFS pour partager les fichiers

---

## ⚙️ Configuration de l'Instance GPU (Instance 2️⃣)

### Script à Exécuter ✅ COMPLÉTÉ
- **Script**: `simulate_pipeline.sh`
- **Emplacement**: `/home/ec2-user/app/simulate_pipeline.sh` (via EFS)

### Clé SSH ✅ COMPLÉTÉ
- **Paire de clés**: `traffic-sign-inventory_keypair`
- **Chemin de la clé privée**: `/home/ec2-user/traffic-sign-inventory_keypair.pem` (sur Instance Principale)
- **Note**: Nécessaire uniquement pour Option B (connexion SSH)

### Méthode d'Exécution ⭐ RECOMMANDATION
**Question**: Quelle approche préférez-vous ?

**Option A - User Data Script (Recommandé - Plus simple)** ⭐
- ✅ L'instance s'auto-configure au démarrage
- ✅ Monte le filesystem EFS, exécute le pipeline, s'éteint automatiquement
- ✅ Pas besoin de gérer SSH
- ✅ Logs disponibles dans CloudWatch ou fichier sur EFS
- ❌ Moins de visibilité en temps réel (mais peut être contourné)

**Option B - Connexion SSH**
- ✅ Plus de contrôle et visibilité
- ✅ Peut voir les logs en temps réel
- ❌ Plus complexe à implémenter
- ❌ Nécessite gestion des connexions et attente de l'instance ready

**Recommandation**: **Option A** pour la simplicité et fiabilité

**Choix par défaut pour le code**: [x] Option A [ ] Option B (modifiable)

### Budget et Limites ⚙️ PAR DÉFAUT
**Question**: Voulez-vous des limites de sécurité ?

**Timeout maximum pour le pipeline**: `120` minutes (par défaut, modifiable)

**Coût maximum acceptable par exécution**: Non défini (peut être ajouté)

**Estimation de coût** (avec `g6e.xlarge` @ ~$0.70/heure):
- Pipeline de 30 min: ~$0.35 USD
- Pipeline de 60 min: ~$0.70 USD
- Pipeline de 120 min: ~$1.40 USD

---

## � Configuration IAM Requise - ACTION NÉCESSAIRE

### ⚠️ PROBLÈME: Aucun IAM Role attaché à l'instance principale

L'instance `i-02c72a6ed2e3c27b8` (Flask/Celery) n'a **pas de IAM Role**, ce qui l'empêche de lancer des instances EC2 via boto3.

### Solution 1: Créer et Attacher un IAM Role (RECOMMANDÉ) ✅

**Étapes à suivre**:

1. **Créer une IAM Policy** avec ces permissions :
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "ec2:RunInstances",
        "ec2:DescribeInstances",
        "ec2:DescribeInstanceStatus",
        "ec2:TerminateInstances",
        "ec2:CreateTags"
      ],
      "Resource": "*"
    }
  ]
}
```

2. **Créer un IAM Role** :
   - Type: AWS Service → EC2
   - Attacher la policy créée ci-dessus
   - Nom suggéré: `traffic-sign-ec2-manager-role`

3. **Attacher le Role à l'instance** :
   - EC2 Console → Instance `i-02c72a6ed2e3c27b8`
   - Actions → Security → Modify IAM role
   - Sélectionner le role créé

**Note**: Pas besoin de redémarrer l'instance, le role sera actif immédiatement.

### Solution 2: Utiliser AWS Access Keys (Non recommandé) ⚠️

Configurer des Access Keys dans le `.env` (moins sécurisé, à éviter en production).

---

##  Notes Importantes

- Les deux instances doivent avoir accès au même filesystem pour partager les données
- L'instance GPU sera lancée uniquement pendant l'exécution du pipeline
- Type d'instance GPU sélectionné : `g6e.xlarge` (NVIDIA L4)
- Coût estimé par exécution = (Type d'instance $/heure) × (Durée en heures)
- Pour un pipeline de 30 minutes sur `g6e.xlarge`: ~$0.35 USD

