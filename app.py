import os
import sys
from flask import Flask, request, jsonify
from flask_cors import CORS
from supabase import create_client, Client
from datetime import datetime, timedelta

app = Flask(__name__)
CORS(app)

# Render.com च्या Environment Variables मधून keys घेणे
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY")

supabase: Client = None

if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
    print("⚠️ चेतावणी: SUPABASE_URL किंवा SUPABASE_SERVICE_KEY Render वर सापडले नाही!", file=sys.stderr)
else:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
        print("✅ Supabase क्लायंट यशस्वीरीत्या कनेक्ट झाला!")
    except Exception as err:
        print(f"❌ Supabase जोडताना त्रुटी आली: {err}", file=sys.stderr)

# १. Test / Health Check API
@app.route('/', methods=['GET'])
def home():
    status = "Connected" if supabase is not None else "Missing Configuration"
    return jsonify({
        "status": "online",
        "service": "SevaSpot Python Backend",
        "supabase": status,
        "message": "SevaSpot Python Backend is Running Perfectly on Render!"
    }), 200

# २. Plan chi Validity Check karn्याची API
@app.route('/check-validity', methods=['POST'])
def check_validity():
    if not supabase:
        return jsonify({"error": "Supabase कनेक्ट नाही. Environment variables तपासा."}), 500

    data = request.get_json(silent=True) or {}
    user_id = data.get('userId')
    
    if not user_id:
        return jsonify({"error": "User ID आवश्यक आहे."}), 400

    try:
        response = supabase.table('user_profiles').select('plan_status, expire_date').eq('id', user_id).execute()
        
        if not response.data:
            return jsonify({"error": "User ची माहिती मिळाली नाही."}), 404

        user_profile = response.data[0]
        today = datetime.now().date()

        expire_date_str = user_profile.get('expire_date')
        plan_status = user_profile.get('plan_status')

        if not expire_date_str:
            return jsonify({"success": False, "error": "Plan ची मुदत सेट केली नाही.", "is_active": False}), 403

        expire_date = datetime.strptime(expire_date_str, '%Y-%m-%d').date()

        if plan_status != 'Active' or today > expire_date:
            supabase.table('user_profiles').update({'plan_status': 'Expired'}).eq('id', user_id).execute()
            return jsonify({
                "success": False, 
                "error": "तुमचा प्लॅन संपला आहे. कृपया रिचार्ज करा.", 
                "is_active": False
            }), 403

        return jsonify({
            "success": True, 
            "message": "Plan active आहे.", 
            "is_active": True, 
            "expire_date": expire_date_str
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ३. Admin API: Plan recharge approve करणे
@app.route('/approve-recharge', methods=['POST'])
def approve_recharge():
    if not supabase:
        return jsonify({"error": "Supabase कनेक्ट नाही."}), 500

    data = request.get_json(silent=True) or {}
    request_id = data.get('requestId')
    user_id = data.get('userId')
    plan_days = int(data.get('planDays', 30))

    if not request_id or not user_id:
        return jsonify({"error": "requestId आणि userId आवश्यक आहेत."}), 400

    try:
        supabase.table('recharge_requests').update({'status': 'Approved'}).eq('id', request_id).execute()

        new_expiry_date = datetime.now().date() + timedelta(days=plan_days)
        supabase.table('user_profiles').update({
            'plan_status': 'Active',
            'expire_date': new_expiry_date.strftime('%Y-%m-%d')
        }).eq('id', user_id).execute()

        supabase.table('transactions').insert({
            'user_id': user_id,
            'action': 'Recharge Approved',
            'remark': f'{plan_days} Days Plan Activated',
            'status': 'Success'
        }).execute()

        return jsonify({"success": True, "message": "Plan यशस्वीरीत्या activate झाला!"}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
