from flask import Blueprint, request, jsonify
import pymupdf as fitz  # 🟢 Modern PyMuPDF Import (No Deprecation Warning)
from PIL import Image, ImageEnhance, ImageDraw
import io
import base64
import os
import gc
from datetime import datetime
from supabase import create_client, Client

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY) if SUPABASE_URL else None

smart_crop_bp = Blueprint('smart_crop', __name__)

@smart_crop_bp.route('/process-card', methods=['POST', 'OPTIONS'])
def process_card():
    if request.method == 'OPTIONS':
        return jsonify({"status": "ok"}), 200

    doc = None
    try:
        user_id = request.form.get('userId')
        if not user_id or str(user_id).strip() in ['null', 'undefined', '']:
            user_id = None

        password = request.form.get('password', '')
        size = request.form.get('size', '4x6')
        
        brightness = 110 
        sharpness = 1.5 
        card_name = request.form.get('cardName', 'Aadhaar') 

        file = request.files.get('pdfFile')
        if not file:
            return jsonify({"error": "PDF file sapadli nahi."}), 400

        if not supabase:
            return jsonify({"error": "Database connection nahi."}), 500

        template_res = supabase.table('card_templates').select('*').eq('card_name', card_name).execute()
        if not template_res.data:
            return jsonify({"error": f"{card_name} che template database madhe sapadle nahi!"}), 404
        
        t = template_res.data[0]

        pdf_bytes = file.read()
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        
        if doc.is_encrypted:
            if not doc.authenticate(password):
                return jsonify({"error": f"Chukicha password! {card_name} cha achuk password taka."}), 400

        page = doc[0]

        # 🟢 zoom = 2.5: 300 DPI एचडी प्रिंटसाठी अत्यंत हलके (Zero Crash on Large PDF)
        zoom = 2.5
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        width, height = img.size

        # Free pixmap
        pix = None

        CARD_ASPECT_RATIO = float(t['aspect_ratio'])
        sw = int(width * float(t['crop_width_pct']))
        sh = int(sw / CARD_ASPECT_RATIO)
        sy = int(height * float(t['crop_y_pct']))
        sLeftX = int(width * float(t['left_x_pct']))
        sRightX = int(width * float(t['right_x_pct']))

        front_img = img.crop((sLeftX, sy, sLeftX + sw, sy + sh))
        back_img = img.crop((sRightX, sy, sRightX + sw, sy + sh))

        img = None

        photo_x = int(sw * float(t['photo_x_pct']))
        photo_y = int(sh * float(t['photo_y_pct']))
        photo_w = int(sw * float(t['photo_w_pct']))
        photo_h = int(sh * float(t['photo_h_pct']))
        
        photo_img = front_img.crop((photo_x, photo_y, photo_x + photo_w, photo_y + photo_h))
        photo_img = ImageEnhance.Brightness(photo_img).enhance(brightness / 100.0)
        photo_img = ImageEnhance.Sharpness(photo_img).enhance(sharpness)
            
        front_img.paste(photo_img, (photo_x, photo_y))

        # 🟢 नॅचरल राऊंडेड कॉर्नर्स आणि अचूक बॉर्डर
        def add_rounded_corners_and_border(im, rad):
            w, h = im.size
            im = im.convert("RGBA")
            
            mask = Image.new('L', (w, h), 0)
            draw_mask = ImageDraw.Draw(mask)
            draw_mask.rounded_rectangle([0, 0, w-1, h-1], radius=rad, fill=255)
            im.putalpha(mask)
            
            bg = Image.new("RGB", (w, h), (255, 255, 255))
            bg.paste(im, (0, 0), im)
            
            draw_border = ImageDraw.Draw(bg)
            draw_border.rounded_rectangle([1, 1, w-2, h-2], radius=rad, outline="black", width=3)
            return bg

        front_img = add_rounded_corners_and_border(front_img, 28)
        back_img = add_rounded_corners_and_border(back_img, 28)

        draw_w = 940
        draw_h = int(draw_w / CARD_ASPECT_RATIO) 
        
        f_resized = front_img.resize((draw_w, draw_h), Image.Resampling.LANCZOS)
        b_resized = back_img.resize((draw_w, draw_h), Image.Resampling.LANCZOS)

        front_img = None
        back_img = None

        if size == '4x6':
            canvas = Image.new('RGB', (1200, 1800), (255, 255, 255))
            margin_x = (1200 - draw_w) // 2
            margin_y = (1800 - (draw_h * 2) - 130) // 2
            canvas.paste(f_resized, (margin_x, margin_y))
            canvas.paste(b_resized, (margin_x, margin_y + draw_h + 130))
        else:
            canvas = Image.new('RGB', (2480, 3508), (255, 255, 255))
            gap = 140
            margin_x = (2480 - (draw_w * 2 + gap)) // 2
            margin_y = 100
            canvas.paste(f_resized, (margin_x, margin_y))
            canvas.paste(b_resized, (margin_x + draw_w + gap, margin_y))

        pdf_out = io.BytesIO()
        canvas.save(pdf_out, format='PDF', resolution=300.0)
        pdf_base64 = base64.b64encode(pdf_out.getvalue()).decode('utf-8')

        canvas = None
        f_resized = None
        b_resized = None
        gc.collect()

        # 🟢 Service Log
        if supabase and user_id:
            try:
                prof_res = supabase.table('user_profiles').select('full_name, shop_name, mobile_number, address').eq('id', user_id).execute()
                
                shop_val = ""
                user_val = ""
                mob_val = ""
                addr_val = ""
                
                if prof_res.data and len(prof_res.data) > 0:
                    p = prof_res.data[0]
                    shop_val = p.get('shop_name') or ""
                    user_val = p.get('full_name') or ""
                    mob_val = p.get('mobile_number') or ""
                    addr_val = p.get('address') or ""
                
                if card_name == "Aadhaar":
                    category_name = "आधार कार्ड प्रिंट"
                elif card_name == "Voter":
                    category_name = "मतदान कार्ड प्रिंट"
                else:
                    category_name = f"{card_name} कार्ड प्रिंट"
                
                now = datetime.now()
                date_str = now.strftime("%d/%m/%Y")
                current_time = now.isoformat()

                supabase.table('service_logs').insert({
                    'user_id': user_id,
                    'log_date': date_str,
                    'shop_name': shop_val,
                    'user_name': user_val,
                    'mobile': mob_val,
                    'address': addr_val,
                    'service_category': category_name,
                    'service_details': f"{size} Size + Smart HD Photo Edit",
                    'created_at': current_time
                }).execute()
            except Exception as log_err:
                print(f"Service Log Error: {log_err}")

        return jsonify({
            "success": True,
            "pdf_base64": pdf_base64
        })

    except Exception as e:
        print(f"Server Error: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        if doc:
            doc.close()
        gc.collect()
