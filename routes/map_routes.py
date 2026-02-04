"""Routes for GPS map visualization and traffic signs display.

These routes are accessible to all authenticated users in their organization.
"""

from flask import Blueprint, render_template, request, jsonify
from flask_login import current_user
from decorators.auth_decorators import login_required
from models.organization import Organization
from services.geo_service import GeoService
from services.signs_service import get_signs_geojson, get_filter_options

map_bp = Blueprint('map', __name__, url_prefix='/map')


@map_bp.route('/', methods=['GET'])
@login_required
def routes_map():
    """Display map view of organization's GPS routes and signs."""
    org = Organization.get_by_id(current_user.organization_id)
    return render_template('map/routes_map.html', organization=org)


@map_bp.route('/api/routes', methods=['GET'])
@login_required
def get_routes_geojson():
    """
    API endpoint to get GPS routes as GeoJSON for the organization.

    Query parameters:
        - from: Start date (ISO format YYYY-MM-DD)
        - to: End date (ISO format YYYY-MM-DD)
        - recordings: Comma-separated recording IDs
        - user_id: Filter by specific user ID

    Returns:
        GeoJSON FeatureCollection with GPS traces
    """
    from_date = request.args.get('from')
    to_date = request.args.get('to')
    recordings_param = request.args.get('recordings')
    user_id = request.args.get('user_id')

    recording_ids = None
    if recordings_param:
        recording_ids = [rid.strip() for rid in recordings_param.split(',') if rid.strip()]

    user_ids = [user_id] if user_id else None

    try:
        geojson = GeoService.organization_routes_to_geojson(
            org_id=current_user.organization_id,
            from_date=from_date,
            to_date=to_date,
            recording_ids=recording_ids,
            user_ids=user_ids,
            use_cache=True
        )
        return jsonify(geojson), 200

    except Exception as e:
        print(f"Error in get_routes_geojson: {e}")
        return jsonify({"error": "Failed to generate routes", "message": str(e)}), 500


@map_bp.route('/api/routes/refresh_cache', methods=['POST'])
@login_required
def refresh_routes_cache():
    """
    API endpoint to refresh the GPS routes cache for the organization.

    Query parameters:
        - from: Start date (ISO format YYYY-MM-DD)
        - to: End date (ISO format YYYY-MM-DD)
        - recordings: Comma-separated recording IDs
        - user_id: Filter by specific user ID
    """
    try:
        from_date = request.args.get('from')
        to_date = request.args.get('to')
        recordings_param = request.args.get('recordings')
        user_id = request.args.get('user_id')

        recording_ids = None
        if recordings_param:
            recording_ids = [rid.strip() for rid in recordings_param.split(',') if rid.strip()]

        user_ids = [user_id] if user_id else None

        GeoService.refresh_organization_routes_cache(
            org_id=current_user.organization_id,
            from_date=from_date,
            to_date=to_date,
            recording_ids=recording_ids,
            user_ids=user_ids
        )

        return jsonify({"success": True, "message": "Cache refreshed successfully"}), 200

    except Exception as e:
        print(f"Cache refresh error (proceeding anyway): {e}")
        return jsonify({"success": True, "message": "Cache refresh attempted"}), 200


@map_bp.route('/api/signs', methods=['GET'])
@login_required
def get_signs_geojson_api():
    """
    API endpoint to get traffic signs as GeoJSON for the organization.
    Only returns signs from validated and completed recordings.

    Query parameters:
        - recordings: Comma-separated recording IDs to filter by
        - mutcd_codes: Comma-separated MUTCD codes to filter by

    Returns:
        GeoJSON FeatureCollection with traffic signs
    """
    recordings_param = request.args.get('recordings')
    mutcd_codes_param = request.args.get('mutcd_codes')

    recording_ids = None
    if recordings_param:
        recording_ids = [rid.strip() for rid in recordings_param.split(',') if rid.strip()]

    mutcd_codes = None
    if mutcd_codes_param:
        mutcd_codes = [code.strip() for code in mutcd_codes_param.split(',') if code.strip()]

    try:
        geojson = get_signs_geojson(
            organization_id=current_user.organization_id,
            recording_ids=recording_ids,
            mutcd_codes=mutcd_codes
        )
        return jsonify(geojson), 200

    except Exception as e:
        print(f"Error in get_signs_geojson: {e}")
        return jsonify({"error": "Failed to retrieve signs", "message": str(e)}), 500


@map_bp.route('/api/signs/filters', methods=['GET'])
@login_required
def get_signs_filter_options():
    """
    API endpoint to get available filter options for signs.

    Returns:
        JSON with 'recordings' and 'mutcd_codes' arrays
    """
    try:
        filter_options = get_filter_options(current_user.organization_id)
        return jsonify(filter_options), 200

    except Exception as e:
        print(f"Error in get_signs_filter_options: {e}")
        return jsonify({"error": "Failed to retrieve filter options", "message": str(e)}), 500
