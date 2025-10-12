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
        # Dernière étape: créer les CSV finaux
        echo "frame_id,sign_type,confidence,x,y,width,height" > "$STEP_PATH/supports.csv"
        echo "1,STOP,0.95,100,200,50,50" >> "$STEP_PATH/supports.csv"
        echo "2,YIELD,0.92,150,250,45,45" >> "$STEP_PATH/supports.csv"
        
        echo "sign_id,class,latitude,longitude" > "$STEP_PATH/signs.csv"
        echo "1,STOP,48.8566,2.3522" >> "$STEP_PATH/signs.csv"
        echo "2,YIELD,48.8567,2.3523" >> "$STEP_PATH/signs.csv"
        
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
