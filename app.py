import os
import sys
from flask import Flask, request, jsonify, make_response
from flask_cors import CORS
from supabase import create_client, Client
from datetime import datetime, timedelta

# 🟢 Aadhaar & Voter Crop Services (Independent Blueprints)
from smart_crop_service import aadhaar_crop_bp
from voter_crop_service import voter_crop_bp

app = Flask(__name__)

app.config['MAX_CONTENT_LENGTH'] = 32 * 1024 * 1024  # 32 MB Upload Limit

CORS(app, resources={r"/*": {
    "origins": "*",
    "methods": ["GET", "POST", "OPTIONS"],
    "allow_headers": ["Content-Type", "Authorization", "X-Requested-With", "Accept"],
    "expose_headers": ["Content-Disposition"]
}}, supports_credentials=True)

@app.before_request
def handle_preflight():
    if request.method == "OPTIONS":
        res = make_response()
        res.headers["Access-Control-Allow-Origin"] = "*"
        res.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        res.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-Requested-With, Accept"
        return res, 200

@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-Requested-With, Accept"
    return response

@app.errorhandler(413)
def request_entity_too_large(error):
    return jsonify({
        "error": "PDF फाईल खूप मोठी आहे (कमाल मर्यादा 32 MB आहे). कृपया फाईल कॉम्प्रेस करून पुन्हा अपलोड करा."
    }), 413

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

# 🟢 Register Independent Blueprints
app.register_blueprint(aadhaar_crop_bp, url_prefix='/api/services')
app.register_blueprint(voter_crop_bp, url_prefix='/api/services')


@app.route('/', methods=['GET'])
@app.route('/health', methods=['GET'])
def home():
    status = "Connected" if supabase is not None else "Missing Configuration"
    return jsonify({
        "status": "online",
        "service": "QuickIDPrint Python Backend",
        "supabase": status,
        "max_upload_size": "32MB",
        "message": "Backend is Running Perfectly on Render!"
    }), 200

# (इतर सर्व API रूट्स जसेच्या तसे राहतील: check-validity, approve-recharge, reset-password, log-service)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
