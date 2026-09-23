import os
import sys
from flask import Flask, request, jsonify
from flask_cors import CORS
from supabase import create_client, Client
from datetime import datetime, timedelta

# 🟢 डायनॅमिक स्मार्ट क्रॉप सर्व्हिस (Blueprint) इम्पोर्ट करणे
from smart_crop_service import smart_crop_bp

app = Flask(__name__)

# 🟢 CORS ची सर्व बंधने काढून सर्व ब्राऊझर्सना मोकळी परवानगी देणे (याने 'Failed to fetch' मिटेल)
CORS(app, resources={r"/*": {"origins": "*"}}, supports_credentials=True)

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

# 🟢 स्मार्ट क्रॉप सर्व्हिस (युनिव्हर्सल कार्ड क्रॉपिंग) चा सेपरेट कोड इथे लिंक केला आहे
app.register_blueprint(smart_crop_bp, url_prefix='/api/services')


# ========================================================
# १. Health Check API (सर्व्हर चालू आहे का हे तपासण्यासाठी)
# ========================================================
@app.route('/', methods=['GET'])
def home():
    status = "Connected" if supabase is not None else "Missing Configuration"
    return jsonify({
        "status": "online",
        "service": "QuickIDPrint Python Backend",
        "supabase": status,
        "message": "Backend is Running Perfectly on Render!"
    }), 200


# ========================================================
# २. Plan ची Validity Check करण्याची API
# ========================================================
@app.route('/check-validity', methods=['POST', 'OPTIONS'])
def check_validity():
    if request.method == 'OPTIONS':
        return jsonify({"status": "ok"}), 200

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


# ========================================================
# ३. Admin API: Plan recharge approve करणे (जुने दिवस + नवीन दिवस)
# ========================================================
@app.route('/approve-recharge', methods=['POST', 'OPTIONS'])
def approve_recharge():
    if request.method == 'OPTIONS':
        return jsonify({"status": "ok"}), 200

    if not supabase:
        return jsonify({"error": "Supabase कनेक्ट नाही."}), 500

    data = request.get_json(silent=True) or {}
    request_id = data.get('requestId')
    user_id = data.get('userId')
    plan_days = int(data.get('planDays', 30))

    if not request_id or not user_id:
        return jsonify({"error": "requestId आणि userId आवश्यक आहेत."}), 400

    try:
        # १. युजरचा आधीचा डेटा आणि उरलेले दिवस तपासणे
        prof_res = supabase.table('user_profiles').select('expire_date, plan_status, total_renews').eq('id', user_id).execute()
        
        today_date = datetime.now().date()
        start_date = today_date

        if prof_res.data:
            profile = prof_res.data[0]
            current_exp_str = profile.get('expire_date')
            status = profile.get('plan_status')
            
            # जर प्लॅन ॲक्टिव्ह असेल, तर जुन्या शिल्लक दिवसांच्या पुढे नवीन दिवस जोडणे
            if status == 'Active' and current_exp_str:
                current_exp = datetime.strptime(current_exp_str, '%Y-%m-%d').date()
                if current_exp >= today_date:
                    start_date = current_exp  

        new_expiry_date = start_date + timedelta(days=plan_days)
        start_date_str = today_date.strftime('%Y-%m-%d') # प्लॅन आजपासूनच सुरू झालाय असे दाखवण्यासाठी
        expiry_date_str = new_expiry_date.strftime('%Y-%m-%d')

        # २. प्रोफाईल अपडेट करणे
        current_renews = prof_res.data[0].get('total_renews') if prof_res.data and prof_res.data[0].get('total_renews') else 0
        
        supabase.table('user_profiles').update({
            'plan_status': 'Active',
            'start_date': start_date_str,
            'expire_date': expiry_date_str,
            'total_renews': current_renews + 1,
            'last_recharge_date': datetime.now().isoformat()
        }).eq('id', user_id).execute()

        # ३. रिक्वेस्ट 'Approved' करणे
        supabase.table('recharge_requests').update({'status': 'Approved'}).eq('id', request_id).execute()

        # ४. ट्रॅन्झॅक्शन टेबलमध्ये अचूक नोंदी (तारीख आणि एक्सपायरीसह)
        supabase.table('transactions').insert({
            'user_id': user_id,
            'action': 'Plan Renew',
            'remark': f'{plan_days} Days Plan Activated',
            'start_date': start_date_str,
            'expiry_date': expiry_date_str,
            'status': 'Success'
        }).execute()

        return jsonify({"success": True, "message": "Plan यशस्वीरीत्या activate झाला!"}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ========================================================
# ४. थेट पासवर्ड रीसेट API (Mobile + Email)
# ========================================================
@app.route('/reset-password', methods=['POST', 'OPTIONS'])
def reset_password():
    if request.method == 'OPTIONS':
        return jsonify({"status": "ok"}), 200

    if not supabase:
        return jsonify({"status": "error", "message": "Supabase सर्व्हर कनेक्ट नाही."}), 500

    data = request.get_json(silent=True) or request.form or {}
    user_id = data.get('userId')
    email = data.get('email', '').strip().lower()
    mobile = data.get('mobile', '').strip()
    new_password = data.get('newPassword', '').strip()

    if not user_id or not email or not mobile or not new_password:
        return jsonify({
            "status": "error",
            "message": "सर्व माहिती (मोबाईल, ईमेल, नवीन पासवर्ड) आवश्यक आहे."
        }), 400

    if len(new_password) < 6:
        return jsonify({
            "status": "error",
            "message": "पासवर्ड किमान ६ अक्षरांचा असावा."
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
                "message": "सुरक्षा तपासणी अयशस्वी! मोबाईल नंबर व ईमेल जुळत नाहीत."
            }), 403

        supabase.auth.admin.update_user_by_id(
            uid=user_id,
            attributes={"password": new_password}
        )

        return jsonify({
            "status": "success",
            "message": "पासवर्ड यशस्वीरीत्या अपडेट करण्यात आला आहे!"
        }), 200

    except Exception as e:
        print(f"Password Reset Error: {e}", file=sys.stderr)
        return jsonify({
            "status": "error",
            "message": f"सर्व्हर त्रुटी: {str(e)}"
        }), 500


# ========================================================
# ५. Service Log API (प्रिंट हिस्ट्री सेव्ह करण्यासाठी)
# ========================================================
@app.route('/log-service', methods=['POST', 'OPTIONS'])
def log_service():
    if request.method == 'OPTIONS':
        return jsonify({"status": "ok"}), 200

    if not supabase:
        return jsonify({"error": "Supabase कनेक्ट नाही."}), 500

    data = request.get_json(silent=True) or {}
    user_id = data.get('userId')
    category = data.get('serviceCategory') 
    details = data.get('serviceDetails')   

    if not user_id or not category:
        return jsonify({"error": "userId आणि serviceCategory आवश्यक आहेत."}), 400

    try:
        supabase.table('service_logs').insert({
            'user_id': user_id,
            'service_category': category,
            'service_details': details
        }).execute()

        return jsonify({"success": True, "message": "सर्व्हिस लॉग यशस्वीरीत्या सेव्ह झाला!"}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ========================================================
# सर्व्हर सुरू करणे
# ========================================================
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
