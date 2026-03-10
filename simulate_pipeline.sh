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
        # Dernière étape: créer les CSV finaux (format réaliste identique à la vraie pipeline)
        # supports.csv – one row per physical support pole
        echo "ID,Mounting Height,Longitude,Latitude" > "$STEP_PATH/supports.csv"
        echo "0,84.0,-110.84433348073429,32.30694008810992" >> "$STEP_PATH/supports.csv"
        echo "1,96.0,-110.84460729972315,32.307264014526766" >> "$STEP_PATH/supports.csv"
        echo "2,72.0,-110.84512003451280,32.307842095123445" >> "$STEP_PATH/supports.csv"
        
        # signs.csv – one row per sign; Foreign Key → support ID
        echo "ID,Foreign Key,MUTCD Code,Position on the Support,Height (in),Width (in)" > "$STEP_PATH/signs.csv"
        echo "0,0,R1-1,1,30,30" >> "$STEP_PATH/signs.csv"
        echo "1,1,R2-1,1,36,36" >> "$STEP_PATH/signs.csv"
        echo "2,1,W3-1,2,30,30" >> "$STEP_PATH/signs.csv"
        echo "3,2,R1-2,1,24,24" >> "$STEP_PATH/signs.csv"
        
        echo "✓ Fichiers CSV créés"
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
