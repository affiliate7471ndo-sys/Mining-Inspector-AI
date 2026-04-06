import streamlit as st
import requests
import base64
import json
import time
import uuid
import gspread
import pandas as pd
import tempfile
import os
import io
import re
from datetime import datetime
from fpdf import FPDF
from google.oauth2.service_account import Credentials
from PIL import Image

# --- 1. KONFIGURASI API & DATABASE ---
try:
    api_key = st.secrets["GOOGLE_API_KEY"]
    sheet_id = st.secrets["GOOGLE_SHEETS_ID"]
    gcp_info = json.loads(st.secrets["GCP_SERVICE_ACCOUNT"])
    scope = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    creds = Credentials.from_service_account_info(gcp_info, scopes=scope)
    client = gspread.authorize(creds)
    db_connected = True
except:
    db_connected = False

# --- 2. ENGINE PEMBACA KATALOG ---
def load_catalog_context():
    try:
        df = pd.read_csv('katalog.csv')
        return "KATALOG HARGA AZARINDO:\n" + df.to_string(index=False)
    except:
        return "Gunakan estimasi harga pasar alat berat yang wajar."

# --- 3. AUTO-COMPRESSOR ---
def compress_image(img_bytes, max_size=800):
    img = Image.open(io.BytesIO(img_bytes))
    if img.mode != 'RGB':
        img = img.convert('RGB')
    img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=85) 
    return out.getvalue()

# --- 4. ENGINE DIAGNOSA ---
def pure_diagnostic_engine(image_bytes_list, brand, model_name, serial_number, category):
    if not api_key: return {"score": 0, "status": "Error", "note": "API Key Hilang"}
    
    try:
        list_url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
        list_res = requests.get(list_url)
        available_models = list_res.json().get('models', [])
        chosen_model = next((m['name'] for m in available_models if 'generateContent' in m.get('supportedGenerationMethods', []) and ('flash' in m['name'] or 'pro' in m['name'] or 'vision' in m['name'])), None)

        if not chosen_model:
            return {"score": 0, "status": "Error", "note": "API Key Anda tidak memiliki akses model Vision."}
        
        prompt = f"""Anda adalah Inspektur Senior AZARINDO. Analisa {len(image_bytes_list)} foto unit {brand} {model_name} (S/N: {serial_number}). 
        WAJIB berikan hasil dalam format JSON murni:
        {{
            "score": angka_kesehatan_0_sampai_100,
            "status": "Good/Warning/Critical",
            "note": "Analisa mendalam semua foto",
            "parts_recommendation": [{{"part_name": "Nama Part", "est_price": "Harga"}}]
        }}
        {load_catalog_context()}"""

        payload = {"contents": [{"parts": [{"text": prompt}]}]}
        
        for img_raw in image_bytes_list:
            img_compressed = compress_image(img_raw)
            payload["contents"][0]["parts"].append({
                "inline_data": {
                    "mime_type": "image/jpeg", 
                    "data": base64.b64encode(img_compressed).decode('utf-8')
                }
            })

        url = f"https://generativelanguage.googleapis.com/v1beta/{chosen_model}:generateContent?key={api_key}"
        res = requests.post(url, json=payload, headers={"Content-Type": "application/json"})
        
        if res.status_code == 200:
            text_out = res.json()['candidates'][0]['content']['parts'][0]['text']
            json_match = re.search(r'\{.*\}', text_out.strip().replace('\n', ''), re.DOTALL)
            try:
                if json_match:
                    return json.loads(json_match.group())
                else:
                    clean_text = text_out.replace('```json', '').replace('```', '').strip()
                    return json.loads(clean_text)
            except Exception as e:
                 return {"score": 0, "status": "Error", "note": f"Format JSON rusak: {str(e)}"}
        else:
            return {"score": 0, "status": "Error", "note": f"Server Error {res.status_code}: {res.text[:100]}..."}
            
    except Exception as e:
        return {"score": 0, "status": "Error", "note": f"Koneksi terputus: {str(e)}"}

# --- 5. UI STREAMLIT ---
st.set_page_config(page_title="Mining Inspector AI", layout="wide")
st.title("🚜 Mining Inspector AI (Heavy Duty)")

if 'result' not in st.session_state: st.session_state.result = None

with st.sidebar:
    st.header("📋 Parameter")
    brand = st.text_input("Merek", "TATSUO")
    model = st.text_input("Tipe", "JP80-9")
    sn = st.text_input("S/N")
    cat = st.selectbox("Kategori", ["General Inspection", "Engine Area", "Undercarriage", "Hydraulic"])

files = st.file_uploader("Upload Foto (Max 10)", accept_multiple_files=True)

if files and sn:
    cols = st.columns(5)
    for i, f in enumerate(files[:10]):
        cols[i % 5].image(f, use_container_width=True)

    if st.button("🔍 JALANKAN ANALISIS MENYELURUH"):
        with st.status("Mengompres & Menganalisa data visual..."):
            st.session_state.result = pure_diagnostic_engine([f.getvalue() for f in files[:10]], brand, model, sn, cat)

    if st.session_state.result:
        res = st.session_state.result
        st.divider()
        c1, c2, c3 = st.columns(3)
        c1.metric("Integritas Unit", f"{res.get('score', 0)}%")
        
        with c2: 
            st.subheader("Status")
            status_txt = res.get('status', 'Error')
            if status_txt in ["Critical", "Error"]:
                st.error(status_txt)
            elif status_txt == "Warning":
                st.warning(status_txt)
            else:
                st.success(status_txt)
                
        with c3: 
            st.subheader("Kesimpulan Teknis")
            st.write(res.get('note'))

        if res.get('status') != "Error":
            if st.button("📄 CETAK PDF & SIMPAN DATABASE"):
                with st.spinner("Menyusun Laporan..."):
                    doc_id = str(uuid.uuid4())[:8].upper()
                    curr_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    
                    if db_connected:
                        try:
                            sheet = client.open_by_key(sheet_id).get_worksheet(0)
                            sheet.append_row([datetime.now().strftime("%Y-%m-%d %H:%M"), f"TA-{doc_id}", brand, model, sn, cat, res.get('score'), res.get('status')])
                            st.success("✅ Terdaftar di Database")
                        except: st.warning("⚠️ Gagal ke Database")

                    # --- PEMBUATAN PDF (MENGEMBALIKAN DESAIN ENTERPRISE) ---
                    pdf = FPDF()
                    pdf.add_page()
                    try: pdf.image('logo.png', 10, 8, 30)
                    except: pass
                    
                    # Header
                    pdf.set_font("Arial", "B", 18)
                    pdf.set_text_color(41, 128, 185) 
                    pdf.cell(0, 10, txt="GENERAL INSPECTION REPORT", ln=True, align="R")
                    
                    pdf.set_font("Arial", "I", 10)
                    pdf.set_text_color(128, 128, 128) 
                    pdf.cell(0, 5, txt="AZARINDO Heavy Equipment Ecosystem", ln=True, align="R")
                    pdf.cell(0, 5, txt=f"Generated: {curr_time}", ln=True, align="R")
                    
                    pdf.set_draw_color(41, 128, 185)
                    pdf.set_line_width(0.5)
                    pdf.line(10, 35, 200, 35)
                    pdf.ln(15)
                    
                    # Kotak Data Unit
                    pdf.set_text_color(0, 0, 0)
                    pdf.set_fill_color(240, 240, 240) 
                    pdf.set_font("Arial", "B", 12)
                    pdf.cell(0, 10, txt="  DATA UNIT LOKASI", border=1, ln=True, fill=True)
                    
                    pdf.set_font("Arial", "", 11)
                    pdf.cell(0, 8, txt=f"  Merek/Model  : {brand.upper()} {model.upper()}", border="LR", ln=True)
                    pdf.cell(0, 8, txt=f"  Serial Number: {sn.upper()}", border="LR", ln=True)
                    pdf.cell(0, 8, txt=f"  Kategori     : {cat}", border="LR", ln=True)
                    pdf.cell(0, 8, txt=f"  Health Score : {res.get('score')}%  |  Status: {res.get('status')}", border="LRB", ln=True)
                    pdf.ln(8)
                    
                    # Temuan Teknis
                    pdf.set_font("Arial", "B", 12)
                    pdf.cell(0, 10, txt="  KESIMPULAN INSPEKSI MENYELURUH", ln=True)
                    pdf.set_font("Arial", "", 11)
                    safe_note = str(res.get('note', '')).encode('latin-1', 'replace').decode('latin-1')
                    pdf.multi_cell(0, 7, txt=safe_note)
                    pdf.ln(8)
                    
                    # TABEL BIRU SUKU CADANG (Dikembalikan)
                    parts = res.get('parts_recommendation', [])
                    if parts:
                        pdf.set_font("Arial", "B", 12)
                        pdf.cell(0, 10, txt="  REKOMENDASI SUKU CADANG (MASTER KATALOG)", ln=True)
                        
                        pdf.set_font("Arial", "B", 10)
                        pdf.set_fill_color(41, 128, 185)
                        pdf.set_text_color(255, 255, 255)
                        pdf.cell(130, 10, "Deskripsi Part & Part Number", border=1, fill=True)
                        pdf.cell(60, 10, "Estimasi Harga (IDR)", border=1, ln=True, fill=True)
                        
                        pdf.set_font("Arial", "", 10)
                        pdf.set_text_color(0, 0, 0)
                        for p in parts:
                            part_name = str(p.get('part_name', 'Unknown')).encode('latin-1', 'replace').decode('latin-1')
                            est_price = str(p.get('est_price', 'N/A')).encode('latin-1', 'replace').decode('latin-1')
                            pdf.cell(130, 10, part_name, border=1)
                            pdf.cell(60, 10, est_price, border=1, ln=True)
                    
                    # --- HALAMAN LAMPIRAN FOTO ---
                    pdf.add_page()
                    pdf.set_font("Arial", "B", 14)
                    pdf.set_text_color(41, 128, 185)
                    pdf.cell(0, 10, txt="LAMPIRAN VISUAL INSPEKSI", ln=True, align="L")
                    pdf.set_draw_color(200, 200, 200)
                    pdf.line(10, 20, 200, 20)
                    pdf.ln(5)
                    
                    x_start, y_start = 15, 30
                    box_w, box_h = 75, 90
                    
                    for idx, f in enumerate(files[:10]):
                        if idx > 0 and idx % 4 == 0: 
                            pdf.add_page()
                            pdf.set_font("Arial", "B", 14)
                            pdf.set_text_color(41, 128, 185)
                            pdf.cell(0, 10, txt="LAMPIRAN VISUAL INSPEKSI (Lanjutan)", ln=True, align="L")
                            pdf.set_draw_color(200, 200, 200)
                            pdf.line(10, 20, 200, 20)
                            y_start = 30
                            
                        col, row = idx % 2, (idx % 4) // 2
                        x_box, y_box = x_start + (col * 90), y_start + (row * 100)
                        
                        img_pil = Image.open(io.BytesIO(f.getvalue()))
                        w_img, h_img = img_pil.size
                        ratio = w_img / h_img
                        p_w, p_h = (box_w, box_w/ratio) if ratio > (box_w/box_h) else (box_h*ratio, box_h)
                        
                        with tempfile.NamedTemporaryFile(delete=False, suffix='.jpg') as tmp:
                            tmp.write(f.getvalue()); tmp_path = tmp.name
                        try:
                            pdf.image(tmp_path, x=x_box + (box_w-p_w)/2, y=y_box + (box_h-p_h)/2, w=p_w, h=p_h)
                        except: pass
                        os.remove(tmp_path)

                    # DIGITAL STAMP (Dikembalikan ke format rapi 3 Baris di Pojok Kiri Bawah)
                    pdf.set_auto_page_break(False)
                    pdf.set_y(-30)
                    pdf.set_draw_color(200, 200, 200)
                    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
                    pdf.ln(3)
                    
                    pdf.set_font("Arial", "B", 8)
                    pdf.set_text_color(0, 0, 0)
                    pdf.cell(0, 4, txt="DIGITAL AUTHORIZATION STAMP", ln=True)
                    pdf.set_font("Arial", "", 8)
                    pdf.cell(0, 4, txt=f"Document ID : TA-{doc_id}-{int(time.time())}", ln=True)
                    pdf.cell(0, 4, txt="Verified By : System VORTEX / Mining Inspector Engine", ln=True)
                    pdf.cell(0, 4, txt="Status      : SYSTEM GENERATED - NO SIGNATURE REQUIRED", ln=True)
                    
                    st.download_button("📥 DOWNLOAD PDF FINAL", pdf.output(dest='S').encode('latin-1'), f"Report_{sn}.pdf")
