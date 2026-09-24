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

# 🟢 1. फाईल साईझ मर्यादा वाढवली (32 MB पर्यंतच्या सर्व मोठ्या PDF ना पूर्ण परवानगी)
app.config['MAX_CONTENT_LENGTH'] = 32 * 1024 * 1024  # 32 MB Upload Limit

# 🟢 2. BULLETPROOF CORS CONFIGURATION
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

# मोठ्या फाईलसाठी स्वच्छ एरर हँडलर
@app.errorhandler(413)
def request_entity_too_large(error):
    return jsonify({
        "error": "PDF फाईल खूप मोठी आहे (कमाल मर्यादा 32 MB आहे). कृपया फाईल कॉम्प्रेस करून पुन्हा अपलोड करा."
    }), 413

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
        "max_upload_size": "32MB",
        "message": "Backend is Running Perfectly on Render!"
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
# ३. Admin API: Plan recharge approve (From & To Date)
# ========================================================
@app.route('/approve-recharge', methods=['POST', 'OPTIONS'])
def approve_recharge():
    if request.method == 'OPTIONS':
        return jsonify({"status": "ok"}), 200

    if not supabase:
        return jsonify({"error": "Supabase connect nahi."}), 500

    data = request.get_json(silent=True) or {}
    request_id = data.get('requestId')
    user_id = data.get('userId')
    plan_days = int(data.get('planDays', 30))

    if not request_id or not user_id:
        return jsonify({"error": "requestId ani userId avashyak ahet."}), 400

    try:
        prof_res = supabase.table('user_profiles').select('expire_date, plan_status, total_renews').eq('id', user_id).execute()
        
        today_date = datetime.now().date()
        start_date = today_date

        if prof_res.data:
            profile = prof_res.data[0]
            current_exp_str = profile.get('expire_date')
            status = profile.get('plan_status', '')
            
            if status and str(status).strip().lower() == 'active' and current_exp_str:
                current_exp = datetime.strptime(current_exp_str, '%Y-%m-%d').date()
                if current_exp >= today_date:
                    start_date = current_exp  

        new_expiry_date = start_date + timedelta(days=plan_days)
        start_date_str = today_date.strftime('%Y-%m-%d')
        expiry_date_str = new_expiry_date.strftime('%Y-%m-%d')

        current_renews = prof_res.data[0].get('total_renews') if prof_res.data and prof_res.data[0].get('total_renews') else 0
        
        supabase.table('user_profiles').update({
            'plan_status': 'Active',
            'start_date': start_date_str,
            'expire_date': expiry_date_str,
            'total_renews': current_renews + 1,
            'last_recharge_date': datetime.now().isoformat()
        }).eq('id', user_id).execute()

        supabase.table('recharge_requests').update({'status': 'Approved'}).eq('id', request_id).execute()

        supabase.table('transactions').insert({
            'user_id': user_id,
            'action': 'Plan Renew',
            'remark': f'{plan_days} Days Plan Activated',
            'start_date': start_date_str,
            'expiry_date': expiry_date_str,
            'status': 'Success'
        }).execute()

        return jsonify({"success": True, "message": "Plan yashasviritya activate jhala!"}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ========================================================
# ४. Direct Password Reset API
# ========================================================
@app.route('/reset-password', methods=['POST', 'OPTIONS'])
def reset_password():
    if request.method == 'OPTIONS':
        return jsonify({"status": "ok"}), 200

    if not supabase:
        return jsonify({"status": "error", "message": "Supabase server connect nahi."}), 500

    data = request.get_json(silent=True) or request.form or {}
    user_id = data.get('userId')
    email = data.get('email', '').strip().lower()
    mobile = data.get('mobile', '').strip()
    new_password = data.get('newPassword', '').strip()

    if not user_id or not email or not mobile or not new_password:
        return jsonify({
            "status": "error",
            "message": "Sarva mahiti (mobile, email, navin password) avashyak ahe."
        }), 400

    if len(new_password) < 6:
        return jsonify({
            "status": "error",
            "message": "Password kiman 6 aksharancha asava."
        }), 400

    try:
        profile_res = supabase.table('user_profiles')\
            .select('id, email, mobile_number')\
            .eq('id', user_id)\
            .eq('mobile_number', mobile)\
            .eq('email', email)\
            .execute()

        if not profile_res.data or len(profile_res.data) == 0:
            return jsonify({
                "status": "error",
                "message": "Suraksha tapasani ayashasvi! Mobile number va email julat nahit."
            }), 403

        supabase.auth.admin.update_user_by_id(
            uid=user_id,
            attributes={"password": new_password}
        )

        return jsonify({
            "status": "success",
            "message": "Password yashasviritya update karnyat ala ahe!"
        }), 200

    except Exception as e:
        print(f"Password Reset Error: {e}", file=sys.stderr)
        return jsonify({
            "status": "error",
            "message": f"Server truti: {str(e)}"
        }), 500


# ========================================================
# ५. Service Log API
# ========================================================
@app.route('/log-service', methods=['POST', 'OPTIONS'])
def log_service():
    if request.method == 'OPTIONS':
        return jsonify({"status": "ok"}), 200

    if not supabase:
        return jsonify({"error": "Supabase connect nahi."}), 500

    data = request.get_json(silent=True) or {}
    user_id = data.get('userId')
    category = data.get('serviceCategory') 
    details = data.get('serviceDetails')   

    if not user_id or not category:
        return jsonify({"error": "userId ani serviceCategory avashyak ahet."}), 400

    try:
        now = datetime.now()
        date_str = now.strftime("%d/%m/%Y")
        
        supabase.table('service_logs').insert({
            'user_id': user_id,
            'log_date': date_str,
            'service_category': category,
            'service_details': details,
            'created_at': now.isoformat()
        }).execute()

        return jsonify({"success": True, "message": "Service log yashasviritya save jhala!"}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ========================================================
# Run Server
# ========================================================
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
