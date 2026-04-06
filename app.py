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
    try:
        sheet_id = st.secrets["GOOGLE_SHEETS_ID"]
        gcp_info = json.loads(st.secrets["GCP_SERVICE_ACCOUNT"])
        scope = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
        creds = Credentials.from_service_account_info(gcp_info, scopes=scope)
        client = gspread.authorize(creds)
        db_connected = True
    except:
        db_connected = False
except:
    api_key = ""
    db_connected = False

# --- 2. ENGINE PEMBACA KATALOG ---
def load_catalog_context():
    try:
        df = pd.read_csv('katalog.csv')
        catalog_text = "REFERENSI KATALOG HARGA AZARINDO:\n"
        catalog_text += df.to_string(index=False)
        return catalog_text
    except:
        return "KATALOG TIDAK DITEMUKAN. Gunakan estimasi wajar."

# --- 3. ENGINE DIAGNOSA MULTI-VISUAL (PENGUATAN JSON PARSING) ---
def pure_diagnostic_engine(image_bytes_list, brand, model_name, serial_number, category):
    if not api_key:
        return {"score": 0, "status": "Error", "note": "API Key tidak ditemukan."}

    try:
        list_url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
        list_res = requests.get(list_url)
        available_models = list_res.json().get('models', [])
        chosen_model = next((m['name'] for m in available_models if 'generateContent' in m.get('supportedGenerationMethods', []) and ('flash' in m['name'] or 'pro' in m['name'])), None)

        katalog_data = load_catalog_context()

        prompt = f"""Anda adalah Inspektur Alat Berat Senior AZARINDO. 
        Analisa {len(image_bytes_list)} foto unit {brand} {model_name} (S/N: {serial_number}). 
        WAJIB Jawab dalam format JSON murni TANPA TEKS LAIN.
        
        {katalog_data}
        
        Format JSON: 
        {{
            "score": angka, 
            "status": "Good/Warning/Critical", 
            "note": "Analisa komprehensif...", 
            "parts_recommendation": [
                {{"part_name": "Nama Part (Part Number)", "est_price": "Harga IDR"}}
            ]
        }}"""

        payload = {"contents": [{"parts": [{"text": prompt}]}]}
        for img_bytes in image_bytes_list:
            payload["contents"][0]["parts"].append({"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(img_bytes).decode('utf-8')}})

        execute_url = f"https://generativelanguage.googleapis.com/v1beta/{chosen_model}:generateContent?key={api_key}"
        response = requests.post(execute_url, headers={"Content-Type": "application/json"}, json=payload)
        
        if response.status_code == 200:
            raw_text = response.json()['candidates'][0]['content']['parts'][0]['text']
            # PENGUATAN: Cari JSON di tengah tumpukan teks menggunakan Regex
            match = re.search(r'\{.*\}', raw_text, re.DOTALL)
            if match:
                return json.loads(match.group())
            else:
                return {"score": 0, "status": "Error", "note": "Format data AI tidak terbaca."}
        else:
            return {"score": 0, "status": "Error", "note": f"Server AI Sibuk: {response.status_code}"}
            
    except Exception as e:
        return {"score": 0, "status": "Error", "note": f"Gagal memproses gambar: {str(e)}"}

# --- 4. UI & LOGIC ---
st.set_page_config(page_title="Mining Inspector AI", layout="wide")
st.title("🚜 Mining Inspector AI (Heavy-Duty)")

with st.sidebar:
    st.header("📋 Parameter Unit")
    brand = st.text_input("Merek")
    model_name = st.text_input("Tipe")
    serial_number = st.text_input("S/N")
    comp = st.selectbox("Inspeksi", ["General Inspection", "Engine Area", "Undercarriage", "Hydraulic"])

uploaded_files = st.file_uploader("Upload Foto (Maks 10)", type=["jpg", "jpeg", "png"], accept_multiple_files=True)

if uploaded_files and brand and serial_number:
    files_to_process = uploaded_files[:10]
    st.write(f"**📸 Unit: {brand.upper()} {model_name.upper()} | S/N: {serial_number.upper()}**")
    
    for i in range(0, len(files_to_process), 5):
        cols = st.columns(5)
        for j, f in enumerate(files_to_process[i:i+5]):
            cols[j].image(f, use_container_width=True)

    if st.button("🔍 Jalankan AI Multi-Scan"):
        with st.status("Menganalisa data visual..."):
            res = pure_diagnostic_engine([f.getvalue() for f in files_to_process], brand, model_name, serial_number, comp)
            st.session_state.result = res
            st.session_state.analyzed = True

    if st.session_state.get('analyzed'):
        res = st.session_state.result
        st.divider()
        c1, c2, c3 = st.columns(3)
        c1.metric("Health Score", f"{res.get('score', 0)}%")
        with c2: 
            st.subheader("Status")
            st.error(res.get('status')) if res.get('status') == "Critical" else st.success(res.get('status'))
        with c3: 
            st.subheader("Kesimpulan")
            st.write(res.get('note'))

        if st.button("Simpan & Cetak Laporan PDF"):
            with st.spinner("Mencetak PDF..."):
                doc_id = str(uuid.uuid4())[:8].upper()
                curr_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                
                # Simpan ke Google Sheets
                if db_connected:
                    save_row = [curr_time, f"TA-{doc_id}", brand.upper(), model_name.upper(), serial_number.upper(), comp, f"{res.get('score')}%", res.get('status'), "Detail di PDF"]
                    try: client.open_by_key(sheet_id).get_worksheet(0).append_row(save_row)
                    except: pass

                # PDF GENERATION (FINAL LAYOUT FIX)
                pdf = FPDF()
                pdf.add_page()
                try: pdf.image('logo.png', 10, 8, 30)
                except: pass
                
                pdf.set_font("Arial", "B", 16)
                pdf.set_text_color(41, 128, 185)
                pdf.cell(0, 10, txt="OFFICIAL INSPECTION REPORT", ln=True, align="R")
                pdf.ln(20)
                
                # Data Table
                pdf.set_fill_color(240, 240, 240)
                pdf.set_font("Arial", "B", 12)
                pdf.set_text_color(0)
                pdf.cell(0, 10, txt="  DATA UNIT", border=1, ln=True, fill=True)
                pdf.set_font("Arial", "", 11)
                pdf.cell(0, 8, txt=f"  Unit: {brand.upper()} {model_name.upper()} | S/N: {serial_number.upper()}", border="LR", ln=True)
                pdf.cell(0, 8, txt=f"  Kategori: {comp} | Skor: {res.get('score')}%", border="LRB", ln=True)
                pdf.ln(5)
                
                # Note
                pdf.set_font("Arial", "B", 11)
                pdf.cell(0, 8, txt="KESIMPULAN TEKNIS:", ln=True)
                pdf.set_font("Arial", "", 10)
                pdf.multi_cell(0, 6, txt=str(res.get('note', '')).encode('latin-1', 'replace').decode('latin-1'))
                pdf.ln(5)

                # Parts
                parts = res.get('parts_recommendation', [])
                if parts:
                    pdf.set_font("Arial", "B", 11)
                    pdf.cell(0, 8, txt="REKOMENDASI SUKU CADANG:", ln=True)
                    pdf.set_font("Arial", "", 9)
                    for p in parts:
                        pdf.cell(0, 6, txt=f"- {p.get('part_name')} ({p.get('est_price')})", ln=True)
                
                # FOTO PAGE
                pdf.add_page()
                pdf.set_font("Arial", "B", 14)
                pdf.cell(0, 10, txt="LAMPIRAN VISUAL", ln=True)
                
                x_start, y_start = 15, 30
                box_w, box_h = 75, 90
                
                for idx, file in enumerate(files_to_process):
                    if idx > 0 and idx % 4 == 0: pdf.add_page(); y_start = 30
                    col, row = idx % 2, (idx % 4) // 2
                    x_box, y_box = x_start + (col * 90), y_start + (row * 100)
                    
                    img_pil = Image.open(io.BytesIO(file.getvalue()))
                    w_img, h_img = img_pil.size
                    ratio = w_img / h_img
                    p_w, p_h = (box_w, box_w/ratio) if ratio > (box_w/box_h) else (box_h*ratio, box_h)
                    
                    with tempfile.NamedTemporaryFile(delete=False, suffix='.jpg') as tmp:
                        tmp.write(file.getvalue()); tmp_path = tmp.name
                    pdf.image(tmp_path, x=x_box + (box_w-p_w)/2, y=y_box + (box_h-p_h)/2, w=p_w, h=p_h)
                    os.remove(tmp_path)

                # STAMP (FORCE POSITION)
                pdf.set_auto_page_break(auto=False)
                pdf.set_y(-30)
                pdf.set_font("Arial", "B", 7)
                pdf.set_text_color(150)
                pdf.line(10, pdf.get_y(), 200, pdf.get_y())
                pdf.cell(0, 4, txt=f"DOC ID: TA-{doc_id} | VERIFIED BY VORTEX ENGINE | {curr_time}", ln=True)

                st.download_button("📥 Download PDF Final", data=pdf.output(dest='S').encode('latin-1'), file_name=f"Report_{serial_number}.pdf")
