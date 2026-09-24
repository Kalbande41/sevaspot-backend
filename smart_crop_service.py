from flask import Blueprint, request, jsonify
import fitz  # PyMuPDF
from PIL import Image, ImageEnhance, ImageDraw
import io
import base64
import os
from supabase import create_client, Client

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY) if SUPABASE_URL else None

smart_crop_bp = Blueprint('smart_crop', __name__)

@smart_crop_bp.route('/process-card', methods=['POST', 'OPTIONS'])
def process_card():
    if request.method == 'OPTIONS':
        return jsonify({"status": "ok"}), 200

    try:
        user_id = request.form.get('userId')
        password = request.form.get('password', '')
        size = request.form.get('size', '4x6')
        
        # 🟢 थेट डाऊनलोडसाठी ऑटो ब्राइटनेस आणि शार्पनेस (११०%)
        brightness = 110 
        sharpness = 1.5 
        
        card_name = request.form.get('cardName', 'Aadhaar') 

        file = request.files.get('pdfFile')
        if not file:
            return jsonify({"error": "PDF फाईल सापडली नाही."}), 400

        if not supabase:
            return jsonify({"error": "डेटाबेस कनेक्शन नाही."}), 500

        template_res = supabase.table('card_templates').select('*').eq('card_name', card_name).execute()
        if not template_res.data:
            return jsonify({"error": f"{card_name} चे टेम्पलेट डेटाबेसमध्ये सापडले नाही!"}), 404
        
        t = template_res.data[0]

        pdf_bytes = file.read()
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        
        if doc.is_encrypted:
            if not doc.authenticate(password):
                return jsonify({"error": f"चुकीचा पासवर्ड! {card_name} चा अचूक पासवर्ड टाका."}), 400

        page = doc[0]
        zoom = 4.0 
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        width, height = img.size

        CARD_ASPECT_RATIO = float(t['aspect_ratio'])
        sw = int(width * float(t['crop_width_pct']))
        sh = int(sw / CARD_ASPECT_RATIO)
        sy = int(height * float(t['crop_y_pct']))
        sLeftX = int(width * float(t['left_x_pct']))
        sRightX = int(width * float(t['right_x_pct']))

        front_img = img.crop((sLeftX, sy, sLeftX + sw, sy + sh))
        back_img = img.crop((sRightX, sy, sRightX + sw, sy + sh))

        # फोटो क्रॉप करून ऑटो क्लिअर करणे
        photo_x = int(sw * float(t['photo_x_pct']))
        photo_y = int(sh * float(t['photo_y_pct']))
        photo_w = int(sw * float(t['photo_w_pct']))
        photo_h = int(sh * float(t['photo_h_pct']))
        
        photo_img = front_img.crop((photo_x, photo_y, photo_x + photo_w, photo_y + photo_h))
        
        # ऑटोमॅटिक ब्राइटनेस आणि शार्पनेस लागू करणे
        photo_img = ImageEnhance.Brightness(photo_img).enhance(brightness / 100.0)
        photo_img = ImageEnhance.Sharpness(photo_img).enhance(sharpness)
            
        front_img.paste(photo_img, (photo_x, photo_y))

        # राऊंडेड कॉर्नर्स आणि कटिंगसाठी काळी बॉर्डर
        def add_rounded_corners_and_border(im, rad):
            im = im.convert("RGBA")
            circle = Image.new('L', (rad * 2, rad * 2), 0)
            draw = ImageDraw.Draw(circle)
            draw.ellipse((0, 0, rad * 2 - 1, rad * 2 - 1), fill=255)
            
            alpha = Image.new('L', im.size, 255)
            w, h = im.size
            alpha.paste(circle.crop((0, 0, rad, rad)), (0, 0))
            alpha.paste(circle.crop((0, rad, rad, rad * 2)), (0, h - rad))
            alpha.paste(circle.crop((rad, 0, rad * 2, rad)), (w - rad, 0))
            alpha.paste(circle.crop((rad, rad, rad * 2, rad * 2)), (w - rad, h - rad))
            im.putalpha(alpha)
            
            bordered = Image.new("RGBA", im.size, (255, 255, 255, 0))
            bordered.paste(im, (0, 0), im)
            
            draw_border = ImageDraw.Draw(bordered)
            draw_border.rounded_rectangle([0, 0, w-1, h-1], radius=rad, outline="black", width=6)
            return bordered.convert("RGB")

        front_img = add_rounded_corners_and_border(front_img, 32)
        back_img = add_rounded_corners_and_border(back_img, 32)

        draw_w = 1040
        draw_h = int(draw_w / CARD_ASPECT_RATIO)
        f_resized = front_img.resize((draw_w, draw_h), Image.Resampling.LANCZOS)
        b_resized = back_img.resize((draw_w, draw_h), Image.Resampling.LANCZOS)

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

        # 🟢 Supabase मध्ये ॲडव्हान्स फॉरमॅटमध्ये लॉग एंट्री सेव्ह करणे
        if supabase and user_id:
            try:
                prof_res = supabase.table('user_profiles').select('full_name, shop_name, mobile_number, address').eq('id', user_id).execute()
                
                shop_str = "No Shop"
                name_str = "Unknown"
                mob_str = "No Mobile"
                addr_str = "No Address"
                
                if prof_res.data:
                    p = prof_res.data[0]
                    shop_str = p.get('shop_name') or "No Shop"
                    name_str = p.get('full_name') or "Unknown"
                    mob_str = p.get('mobile_number') or "No Mobile"
                    addr_str = p.get('address') or "No Address"

                # फॉरमॅट: Shop Name / User-Mobile-Address-Service Details
                final_details = f"{shop_str} / {name_str} - {mob_str} - {addr_str} - {size} Size Auto HD Print"

                supabase.table('service_logs').insert({
                    'user_id': user_id,
                    'service_category': f"{card_name} Print",
                    'service_details': final_details
                }).execute()
            except Exception as log_err:
                print(f"Log Error: {log_err}")

        return jsonify({
            "success": True,
            "pdf_base64": pdf_base64
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500
