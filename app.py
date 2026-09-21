import os
from flask import Flask, request, jsonify
from flask_cors import CORS
from supabase import create_client, Client
from datetime import datetime, timedelta

app = Flask(__name__)
# CORS मुळे तुमच्या फ्रंटएंडला या बॅकएंडशी बोलण्याची परवानगी मिळते
CORS(app)

# Render.com च्या सेटिंग्समधून Supabase च्या Keys सुरक्षितपणे घेणे
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY")

# Supabase शी कनेक्शन
if SUPABASE_URL and SUPABASE_SERVICE_KEY:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

# १. सर्व्हर चालू आहे की नाही हे तपासण्यासाठी (Test API)
@app.route('/', methods=['GET'])
def home():
    return "SevaSpot Python Backend is Running Perfectly (Validity Based System)!"

# २. प्लॅनची व्हॅलिडिटी चेक करण्याची API
@app.route('/check-validity', methods=['POST'])
def check_validity():
    data = request.json
    user_id = data.get('userId')
    
    if not user_id:
        return jsonify({"error": "User ID आवश्यक आहे."}), 400

    try:
        # डेटाबेसमधून युजरचा प्लॅन आणि संपण्याची तारीख काढणे
        response = supabase.table('user_profiles').select('plan_status, expire_date').eq('id', user_id).execute()
        
        if not response.data:
            return jsonify({"error": "युजरची माहिती मिळाली नाही."}), 400

        user_profile = response.data[0]
        today = datetime.now().date()

        expire_date_str = user_profile.get('expire_date')
        plan_status = user_profile.get('plan_status')

        if not expire_date_str:
            return jsonify({"success": False, "error": "प्लॅनची मुदत सेट केलेली नाही.", "is_active": False}), 403

        expire_date = datetime.strptime(expire_date_str, '%Y-%m-%d').date()

        # जर प्लॅनची मुदत संपली असेल
        if plan_status != 'Active' or today > expire_date:
            # डेटाबेसमध्ये स्टेटस 'Expired' करा
            supabase.table('user_profiles').update({'plan_status': 'Expired'}).eq('id', user_id).execute()
            return jsonify({
                "success": False, 
                "error": "तुमचा प्लॅन संपला आहे. कृपया रिचार्ज करा.", 
                "is_active": False
            }), 403

        # प्लॅन चालू असल्यास
        return jsonify({
            "success": True, 
            "message": "प्लॅन ॲक्टिव्ह आहे.", 
            "is_active": True, 
            "expire_date": expire_date_str
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ३. ॲडमिनसाठी API: प्लॅन रिचार्ज मंजूर (Approve) करणे
@app.route('/approve-recharge', methods=['POST'])
def approve_recharge():
    data = request.json
    request_id = data.get('requestId')
    user_id = data.get('userId')
    plan_days = int(data.get('planDays', 30)) # उदा. ३० दिवसांचा प्लॅन

    try:
        # १. रिक्वेस्टचे स्टेटस 'Approved' करा
        supabase.table('recharge_requests').update({'status': 'Approved'}).eq('id', request_id).execute()

        # २. युजरचे प्रोफाईल अपडेट करा (Validity वाढवा)
        new_expiry_date = datetime.now().date() + timedelta(days=plan_days)
        supabase.table('user_profiles').update({
            'plan_status': 'Active',
            'expire_date': new_expiry_date.strftime('%Y-%m-%d')
        }).eq('id', user_id).execute()

        # ३. ट्रान्झॅक्शनची नोंद ठेवा
        supabase.table('transactions').insert({
            'user_id': user_id,
            'action': 'Recharge Approved',
            'remark': f'{plan_days} Days Plan Activated',
            'status': 'Success'
        }).execute()

        return jsonify({"success": True, "message": "प्लॅन यशस्वीरीत्या ॲक्टिव्हेट झाला!"})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
