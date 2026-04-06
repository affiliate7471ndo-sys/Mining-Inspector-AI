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

# --- 3. ENGINE DIAGNOSA (REINFORCED JSON PARSER) ---
def pure_diagnostic_engine(image_bytes_list, brand, model_name, serial_number, category):
    if not api_key: return {"score": 0, "status": "Error", "note": "API Key Hilang"}
    
    try:
        # Gunakan model Pro jika tersedia untuk stabilitas multi-image
        model_name_ai = "gemini-1.5-flash" 
        
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
        for img in image_bytes_list:
            payload["contents"][0]["parts"].append({"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(img).decode('utf-8')}})

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name_ai}:generateContent?key={api_key}"
        res = requests.post(url, json=payload, headers={"Content-Type": "application/json"})
        
        if res.status_code == 200:
            text_out = res.json()['candidates'][0]['content']['parts'][0]['text']
            # MENGAMBIL JSON SAJA (Mencegah Error Expecting Value)
            json_match = re.search(r'\{.*\}', text_out, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
        return {"score": 0, "status": "Error", "note": "AI gagal merespon dengan benar."}
    except Exception as e:
        return {"score": 0, "status": "Error", "note": f"Koneksi terputus: {str(e)}"}

# --- 4. UI STREAMLIT ---
st.set_page_config(page_title="Mining Inspector AI", layout="wide")
st.title("🚜 Mining Inspector AI (Heavy Duty)")

if 'result' not in st.session_state: st.session_state.result = None

with st.sidebar:
    st.header("📋 Parameter")
    brand = st.text_input("Merek", "TATSUO")
    model = st.text_input("Tipe", "JP80-9")
    sn = st.text_input("S/N")
    cat = st.selectbox("Kategori", ["General Inspection", "Engine Area", "Undercarriage"])

files = st.file_uploader("Upload Foto (Max 10)", accept_multiple_files=True)

if files and sn:
    # Preview Grid
    cols = st.columns(5)
    for i, f in enumerate(files[:10]):
        cols[i % 5].image(f, use_container_width=True)

    if st.button("🔍 JALANKAN ANALISIS MENYELURUH"):
        with st.status("Menghitung data visual..."):
            st.session_state.result = pure_diagnostic_engine([f.getvalue() for f in files], brand, model, sn, cat)

    if st.session_state.result:
        res = st.session_state.result
        st.divider()
        c1, c2, c3 = st.columns(3)
        c1.metric("Integritas Unit", f"{res.get('score', 0)}%")
        c2.subheader(f"Status: {res.get('status')}")
        c3.subheader("Temuan Teknis")
        st.write(res.get('note'))

        if st.button("📄 CETAK PDF & SIMPAN DATABASE"):
            with st.spinner("Menyusun Laporan..."):
                doc_id = str(uuid.uuid4())[:8].upper()
                # Simpan ke Sheets
                if db_connected:
                    try:
                        sheet = client.open_by_key(sheet_id).get_worksheet(0)
                        sheet.append_row([datetime.now().strftime("%Y-%m-%d %H:%M"), f"TA-{doc_id}", brand, model, sn, cat, res.get('score'), res.get('status')])
                        st.success("✅ Terdaftar di Database")
                    except: st.warning("⚠️ Gagal ke Database")

                # PDF Logic (Final Proportional Fix)
                pdf = FPDF()
                pdf.add_page()
                try: pdf.image('logo.png', 10, 8, 30)
                except: pass
                
                pdf.set_font("Arial", "B", 16)
                pdf.cell(0, 10, "INSPECTION REPORT", ln=True, align="R")
                pdf.ln(20)
                pdf.set_font("Arial", "", 11)
                pdf.cell(0, 8, f"Unit: {brand} {model} | S/N: {sn}", ln=True)
                pdf.multi_cell(0, 7, f"Catatan: {res.get('note')}")
                
                # Halaman Foto
                pdf.add_page()
                x, y = 15, 30
                for idx, f in enumerate(files[:10]):
                    if idx > 0 and idx % 4 == 0: pdf.add_page(); y = 30
                    img = Image.open(io.BytesIO(f.getvalue()))
                    w, h = img.size
                    # Pengecilan otomatis (Smart Scale)
                    ratio = w/h
                    pw, ph = (70, 70/ratio) if ratio > 0.7 else (60*ratio, 80)
                    
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp:
                        tmp.write(f.getvalue()); tpath = tmp.name
                    pdf.image(tpath, x=x + (idx%2)*90, y=y + ((idx%4)//2)*100, w=pw, h=ph)
                    os.remove(tpath)
                
                # Footer Stamp (Lock at Bottom)
                pdf.set_auto_page_break(False)
                pdf.set_y(-25)
                pdf.set_font("Arial", "I", 7)
                pdf.cell(0, 5, f"Verified by AZARINDO AI - DOC ID: {doc_id}", align="C")
                
                st.download_button("📥 DOWNLOAD PDF", pdf.output(dest='S').encode('latin-1'), f"Report_{sn}.pdf")
