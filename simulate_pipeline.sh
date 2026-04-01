#!/bin/bash

# Script de simulation de la pipeline ML
# Simule un traitement qui prend du temps et crée les fichiers de sortie attendus

RECORDING_PATH=$1

if [ -z "$RECORDING_PATH" ]; then
    echo "Usage: $0 <recording_path>"
    exit 1
fi

echo "=========================================="
echo "Simulation Pipeline ML"
echo "Recording: $RECORDING_PATH"
echo "=========================================="

# Créer la structure de résultats
RESULT_PATH="$RECORDING_PATH/result_pipeline_stable"
mkdir -p "$RESULT_PATH"

# Liste des étapes de la pipeline
STEPS=(
    "s0_detection"
    "s1_small_sign_filter"
    "s2_tracking"
    "s3_small_track_filter"
    "s4_classification"
    "s5_frames_gps_coordinates_extraction"
    "s6_localization"
    "s7_export_csv"
)

# Simuler chaque étape avec un délai
for STEP in "${STEPS[@]}"; do
    echo "Étape: $STEP"
    STEP_PATH="$RESULT_PATH/$STEP"
    mkdir -p "$STEP_PATH"
    
    # Simuler un temps de traitement (5 secondes par étape)
    sleep 5
    
    # Créer le fichier de sortie approprié
    if [ "$STEP" == "s7_export_csv" ]; then
        
        # 1. supports.csv – one row per physical support pole
        cat << 'EOF' > "$STEP_PATH/supports.csv"
ID,Mounting Height,Longitude,Latitude
0,84.0,-110.992750,32.322050
1,96.0,-110.691850,32.069250
2,72.0,-111.025000,32.323200
3,84.0,-110.990818,32.323981
4,96.0,-110.685000,32.075000
5,72.0,-111.020000,32.328000
6,84.0,-110.746500,32.287500
7,96.0,-110.742800,32.287450
8,72.0,-110.740000,32.295000
9,84.0,-110.750000,32.280000
10,80.0,-111.016310,32.3065715
11,80.0,-111.016430,32.3063075
EOF

        # 2. signs.csv – one row per sign; Foreign Key → support ID
        cat << 'EOF' > "$STEP_PATH/signs.csv"
ID,Foreign Key,MUTCD Code,Position on the Support,Height (in),Width (in)
0,0,R1-1,1,30,30
1,1,R1-2,1,24,24
2,2,W3-1,1,36,36
3,3,R2-1,1,24,30
4,4,W1-1,1,30,30
5,5,M1-1,1,24,24
6,6,R1-1,1,30,30
7,7,R2-1,1,24,30
8,8,W3-1,1,36,36
9,9,W1-1,1,30,30
10,10,D9-18,1,17.04,23.29
11,11,D9-18,1,17.17,25.09
EOF
        
        echo "✓ Fichiers supports.csv, signs.csv et signs_merged.csv créés"
    else
        # Autres étapes: créer output.json
        echo '{"status": "completed", "items_processed": 100}' > "$STEP_PATH/output.json"
        echo "✓ output.json créé"
    fi
done

echo "=========================================="
echo "Pipeline terminée avec succès!"
echo "=========================================="

exit 0