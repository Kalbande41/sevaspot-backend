import os
from flask import Flask, request, jsonify
from flask_cors import CORS
from supabase import create_client, Client
from datetime import datetime, timedelta

app = Flask(__name__)
# CORS mule tumchya frontend la yashasviritya connection milte
CORS(app)

# Render.com chya Environment Variables madhun keys ghene
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY")

# Supabase Client setup
if SUPABASE_URL and SUPABASE_SERVICE_KEY:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

# ১. Test API (Server chaloo ahe ka te tapanysathi)
@app.route('/', methods=['GET'])
def home():
    return "SevaSpot Python Backend is Running Perfectly (Validity Based System)!"

# ২. Plan chi Validity Check karn्याची API
@app.route('/check-validity', methods=['POST'])
def check_validity():
    data = request.json
    user_id = data.get('userId')
    
    if not user_id:
        return jsonify({"error": "User ID avashyak ahe."}), 400

    try:
        # Database madhun user cha plan status ani expiry date kadhne
        response = supabase.table('user_profiles').select('plan_status, expire_date').eq('id', user_id).execute()
        
        if not response.data:
            return jsonify({"error": "User chi mahiti milali nahi."}), 400

        user_profile = response.data[0]
        today = datetime.now().date()

        expire_date_str = user_profile.get('expire_date')
        plan_status = user_profile.get('plan_status')

        if not expire_date_str:
            return jsonify({"success": False, "error": "Plan chi mudat set keli nahi.", "is_active": False}), 403

        expire_date = datetime.strptime(expire_date_str, '%Y-%m-%d').date()

        # Jar plan chi mudat sampali asel
        if plan_status != 'Active' or today > expire_date:
            supabase.table('user_profiles').update({'plan_status': 'Expired'}).eq('id', user_id).execute()
            return jsonify({
                "success": False, 
                "error": "Tumcha plan sampala ahe. Krupaya recharge kara.", 
                "is_active": False
            }), 403

        # Plan chaloo aslyas
        return jsonify({
            "success": True, 
            "message": "Plan active ahe.", 
            "is_active": True, 
            "expire_date": expire_date_str
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ৩. Admin sathi API: Plan recharge approve karne
@app.route('/approve-recharge', methods=['POST'])
def approve_recharge():
    data = request.json
    request_id = data.get('requestId')
    user_id = data.get('userId')
    plan_days = int(data.get('planDays', 30))

    try:
        # ১. Request status 'Approved' karne
        supabase.table('recharge_requests').update({'status': 'Approved'}).eq('id', request_id).execute()

        # ২. User profile update karne (Validity vadhavne)
        new_expiry_date = datetime.now().date() + timedelta(days=plan_days)
        supabase.table('user_profiles').update({
            'plan_status': 'Active',
            'expire_date': new_expiry_date.strftime('%Y-%m-%d')
        }).eq('id', user_id).execute()

        # ৩. Transaction chi nond thevne
        supabase.table('transactions').insert({
            'user_id': user_id,
            'action': 'Recharge Approved',
            'remark': f'{plan_days} Days Plan Activated',
            'status': 'Success'
        }).execute()

        return jsonify({"success": True, "message": "Plan yashasviritya activate zala!"})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
