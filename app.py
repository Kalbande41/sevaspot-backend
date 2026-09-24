import os
import sys
from flask import Flask, request, jsonify, make_response
from flask_cors import CORS
from supabase import create_client, Client
from datetime import datetime, timedelta

# 🟢 Smart Crop Service (Blueprint)
from smart_crop_service import smart_crop_bp
# 🟢 Voter Crop Service (Blueprint)
from voter_crop_service import voter_crop_bp

app = Flask(__name__)

# 🟢 BULLETPROOF CORS CONFIGURATION
CORS(app, resources={r"/*": {
    "origins": "*",
    "methods": ["GET", "POST", "OPTIONS"],
    "allow_headers": ["Content-Type", "Authorization", "X-Requested-With", "Accept"],
    "expose_headers": ["Content-Disposition"]
}}, supports_credentials=True)

# Pre-flight OPTIONS ग्लोबल हँडलर
@app.before_request
def handle_preflight():
    if request.method == "OPTIONS":
        res = make_response()
        res.headers["Access-Control-Allow-Origin"] = "*"
        res.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        res.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-Requested-With, Accept"
        return res, 200

# After Request द्वारे हेडर गॅरंटी
@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-Requested-With, Accept"
    return response

# Supabase Keys
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY")

supabase: Client = None

if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
    print("⚠️ Warning: SUPABASE_URL or SUPABASE_SERVICE_KEY missing!", file=sys.stderr)
else:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
        print("✅ Supabase Connected Successfully!")
    except Exception as err:
        print(f"❌ Supabase Connection Error: {err}", file=sys.stderr)

# 🟢 Register Blueprints
app.register_blueprint(smart_crop_bp, url_prefix='/api/services')
app.register_blueprint(voter_crop_bp, url_prefix='/api/services')


# ========================================================
# १. Health Check API (Server Ping साठी)
# ========================================================
@app.route('/', methods=['GET'])
@app.route('/health', methods=['GET'])
def home():
    status = "Connected" if supabase is not None else "Missing Configuration"
    return jsonify({
        "status": "online",
        "service": "QuickIDPrint Python Backend",
        "supabase": status,
        "message": "Backend is Running Perfectly!"
    }), 200


# ========================================================
# २. Plan Validity Check API
# ========================================================
@app.route('/check-validity', methods=['POST', 'OPTIONS'])
def check_validity():
    if request.method == 'OPTIONS':
        return jsonify({"status": "ok"}), 200

    if not supabase:
        return jsonify({"error": "Supabase connect nahi."}), 500

    data = request.get_json(silent=True) or {}
    user_id = data.get('userId')
    
    if not user_id:
        return jsonify({"error": "User ID avashyak ahe."}), 400

    try:
        response = supabase.table('user_profiles').select('plan_status, expire_date').eq('id', user_id).execute()
        if not response.data:
            return jsonify({"error": "User chi mahiti milali nahi."}), 404

        user_profile = response.data[0]
        today = datetime.now().date()
        expire_date_str = user_profile.get('expire_date')
        plan_status = user_profile.get('plan_status', '')

        if not expire_date_str:
            return jsonify({"success": False, "error": "Plan chi mudat set keli nahi.", "is_active": False}), 403

        expire_date = datetime.strptime(expire_date_str, '%Y-%m-%d').date()
        is_active_status = plan_status and str(plan_status).strip().lower() == 'active'

        if is_active_status and today <= expire_date:
            return jsonify({
                "success": True, 
                "message": "Plan active ahe.", 
                "is_active": True, 
                "expire_date": expire_date_str
            }), 200
        else:
            if today > expire_date and is_active_status:
                supabase.table('user_profiles').update({'plan_status': 'Expired'}).eq('id', user_id).execute()

            return jsonify({
                "success": False, 
                "error": "Tumcha plan sampla ahe. Krupaya recharge kara.", 
                "is_active": False
            }), 403

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ========================================================
# Run Server
# ========================================================
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
