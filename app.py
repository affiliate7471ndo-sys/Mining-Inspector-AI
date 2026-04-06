import streamlit as st
import requests
import base64
import json
import time
import uuid
import gspread
from datetime import datetime
from fpdf import FPDF
from google.oauth2.service_account import Credentials

# --- 1. KONFIGURASI API & DATABASE ---
try:
    api_key = st.secrets["GOOGLE_API_KEY"]
    sheet_id = st.secrets["GOOGLE_SHEETS_ID"]
    # Memuat kredensial Google Sheets
    gcp_info = json.loads(st.secrets["GCP_SERVICE_ACCOUNT"])
    scope = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    creds = Credentials.from_service_account_info(gcp_info, scopes=scope)
    client = gspread.authorize(creds)
except Exception as e:
    st.error(f"⚠️ Masalah Konfigurasi: {str(e)}")

# --- 2. ENGINE DIAGNOSA MURNI (REST API AUTO-SNIPER) ---
def pure_diagnostic_engine(image_bytes, brand, model_name, category):
    try:
        list_url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
        list_res = requests.get(list_url)
        available_models = list_res.json().get('models', [])
        chosen_model = next((m['name'] for m in available_models if 'generateContent' in m.get('supportedGenerationMethods', []) and ('flash' in m['name'] or 'pro' in m['name'] or 'vision' in m['name'])), None)

        prompt = f"""Anda adalah Inspektur Alat Berat Senior Tatsuo-AIMIX. 
        Analisa foto {category} unit {brand} {model_name}. Berikan skor 0-100, status, temuan teknis, 
        dan daftar suku cadang + estimasi harga IDR.
        Format JSON: {{"score": angka, "status": "teks", "note": "teks", "parts_recommendation": [{{"part_name": "teks", "est_price": "teks"}}]}}"""

        base64_img = base64.b64encode(image_bytes).decode('utf-8')
        payload = {"contents": [{"parts": [{"text": prompt}, {"inline_data": {"mime_type": "image/jpeg", "data": base64_img}}]}]}
        
        execute_url = f"https://generativelanguage.googleapis.com/v1beta/{chosen_model}:generateContent?key={api_key}"
        response = requests.post(execute_url, headers={"Content-Type": "application/json"}, json=payload)
        
        clean_res = response.json()['candidates'][0]['content']['parts'][0]['text'].replace('```json', '').replace('```', '').strip()
        return json.loads(clean_res)
    except Exception as e:
        return {"score": 0, "status": "Error", "note": f"System Error: {str(e)}"}

# --- 3. FUNGSI SIMPAN KE DATABASE (GOOGLE SHEETS) ---
def save_to_database(data_row):
    try:
        sheet = client.open_by_key(sheet_id).get_worksheet(0)
        sheet.append_row(data_row)
        return True
    except:
        return False

# --- 4. ANTARMUKA PENGGUNA (UI) ---
st.set_page_config(page_title="VORTEX: Mining Inspector AI", layout="wide")
st.title("🚜 Mining Inspector AI")
st.subheader("Sistem Analisis Visual & Database Inspeksi Tatsuo/AIMIX")

with st.sidebar:
    st.header("📋 Parameter Unit")
    brand = st.text_input("Merek Unit", placeholder="Tatsuo / AIMIX")
    model_name = st.text_input("Tipe/Model", placeholder="Contoh: JP80-9")
    comp = st.selectbox("Komponen", ["Engine Area", "Undercarriage", "Tyre", "Hydraulic"])

uploaded_file = st.file_uploader("Upload Foto Aktual", type=["jpg", "jpeg", "png"])

if uploaded_file and brand:
    st.image(uploaded_file, caption=f"Unit: {brand.upper()} {model_name.upper()}", width=400)

    if 'result' not in st.session_state: st.session_state.result = None
    if 'analyzed' not in st.session_state: st.session_state.analyzed = False

    if st.button("🔍 Jalankan Analisis Visual AI"):
        with st.status("Memproses Analisis & Sinkronisasi Database...", expanded=True):
            res = pure_diagnostic_engine(uploaded_file.getvalue(), brand, model_name, comp)
            st.session_state.result = res
            st.session_state.analyzed = True

    if st.session_state.analyzed and st.session_state.result:
        res = st.session_state.result
        st.divider()
        c1, c2, c3 = st.columns(3)
        c1.metric("Health Score", f"{res.get('score', 0)}%")
        c2.subheader("Status")
        status_txt = res.get('status', 'Unknown')
        if status_txt == "Critical": st.error(status_txt)
        else: st.success(status_txt)
        c3.subheader("Temuan AI")
        st.write(res.get('note'))

        # Tampilan Part
        st.subheader("🛠️ Estimasi Suku Cadang")
        parts = res.get('parts_recommendation', [])
        total_est = 0
        for p in parts:
            st.info(f"**{p.get('part_name')}** — {p.get('est_price')}")
        
        # --- PDF & DATABASE TRIGGER ---
        st.divider()
        if st.button("Cetak Laporan & Simpan ke Database"):
            doc_id = f"TA-{str(uuid.uuid4())[:8].upper()}"
            curr_date = datetime.now().strftime('%Y-%m-%d %H:%M')
            
            # Simpan ke Google Sheets
            data_to_save = [curr_date, doc_id, brand.upper(), model_name.upper(), comp, f"{res.get('score')}%", status_txt, "Terlampir di PDF"]
            db_status = save_to_database(data_to_save)
            
            # Buat PDF
            pdf = FPDF()
            pdf.add_page()
            try: pdf.image('logo.png', 10, 8, 30)
            except: pass
            pdf.set_font("Arial", "B", 16)
            pdf.cell(0, 10, txt="OFFICIAL INSPECTION & DATABASE RECORD", ln=True, align="R")
            pdf.ln(20)
            pdf.set_font("Arial", "B", 12)
            pdf.cell(0, 10, txt=f"DOCUMENT ID: {doc_id}", ln=True)
            pdf.set_font("Arial", "", 11)
            pdf.cell(0, 8, txt=f"Unit: {brand} {model_name} | Date: {curr_date}", ln=True)
            pdf.multi_cell(0, 8, txt=f"Analisis: {res.get('note')}")
            
            pdf_bytes = pdf.output(dest='S').encode('latin-1')
            st.success("✅ Data berhasil masuk ke Database Utama AZARINDO!") if db_status else st.warning("⚠️ PDF Siap, tapi koneksi Database gagal.")
            st.download_button("📥 Unduh Laporan (PDF)", data=pdf_bytes, file_name=f"Report_{doc_id}.pdf")
