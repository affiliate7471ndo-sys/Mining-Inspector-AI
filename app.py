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
    
    # Kredensial Google Sheets (Opsional: Tetap jalan walau Sheets belum disetup)
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

# --- 2. ENGINE DIAGNOSA MURNI (REST API) ---
def pure_diagnostic_engine(image_bytes, brand, model_name, serial_number, category):
    if not api_key:
        return {"score": 0, "status": "Error", "note": "API Key kosong."}

    try:
        list_url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
        list_res = requests.get(list_url)
        available_models = list_res.json().get('models', [])
        chosen_model = next((m['name'] for m in available_models if 'generateContent' in m.get('supportedGenerationMethods', []) and ('flash' in m['name'] or 'pro' in m['name'] or 'vision' in m['name'])), None)

        if not chosen_model:
            return {"score": 0, "status": "Error", "note": "Akses model Vision ditolak."}

        # Prompt AI sekarang mengunci Serial Number
        prompt = f"""Anda adalah Inspektur Alat Berat Senior. Analisa foto {category} unit {brand} {model_name} dengan Serial Number: {serial_number}. 
        1. Baca indikator panel monitor jika ada.
        2. Cari anomali fisik.
        3. Berikan skor 0-100, status (Good/Warning/Critical), dan temuan teknis.
        4. WAJIB: Sebutkan daftar suku cadang yang perlu diganti dan estimasi harga dalam Rupiah (IDR).
        Format jawaban WAJIB JSON murni: 
        {{
            "score": angka, 
            "status": "teks", 
            "note": "teks", 
            "parts_recommendation": [
                {{"part_name": "Nama Suku Cadang", "est_price": "Harga Rupiah"}}
            ]
        }}"""

        base64_img = base64.b64encode(image_bytes).decode('utf-8')
        payload = {"contents": [{"parts": [{"text": prompt}, {"inline_data": {"mime_type": "image/jpeg", "data": base64_img}}]}]}
        headers = {"Content-Type": "application/json"}
        
        execute_url = f"https://generativelanguage.googleapis.com/v1beta/{chosen_model}:generateContent?key={api_key}"
        response = requests.post(execute_url, headers=headers, json=payload)
        
        if response.status_code == 200:
            raw_text = response.json()['candidates'][0]['content']['parts'][0]['text']
            clean_res = raw_text.replace('```json', '').replace('```', '').strip()
            return json.loads(clean_res)
        else:
            return {"score": 0, "status": "Error", "note": f"API gagal: {response.text}"}
            
    except Exception as e:
        return {"score": 0, "status": "Error", "note": f"System Error: {str(e)}"}

# --- 3. FUNGSI DATABASE ---
def save_to_database(data_row):
    if not db_connected: return False
    try:
        sheet = client.open_by_key(sheet_id).get_worksheet(0)
        sheet.append_row(data_row)
        return True
    except:
        return False

# --- 4. ANTARMUKA PENGGUNA (UI) ---
st.set_page_config(page_title="Mining Inspector AI", layout="wide")
st.title("🚜 Mining Inspector AI")
st.subheader("Sistem Analisis Visual & Database Inspeksi")

if not db_connected:
    st.info("ℹ️ Mode Offline: Database Google Sheets belum terhubung. PDF tetap bisa dicetak.")

with st.sidebar:
    st.header("📋 Parameter Unit")
    brand = st.text_input("Merek Unit", placeholder="Contoh: Tatsuo, AIMIX...")
    model_name = st.text_input("Tipe/Model", placeholder="Contoh: JP80-9")
    serial_number = st.text_input("Serial Number (S/N)", placeholder="Contoh: TS-809-991204")
    comp = st.selectbox("Komponen Diperiksa", ["Engine Area", "Undercarriage", "Tyre", "Hydraulic"])
    st.divider()

uploaded_file = st.file_uploader("Upload Foto Aktual Komponen", type=["jpg", "jpeg", "png"])

# Syarat tombol jalan: Brand, Model, dan S/N harus diisi
if uploaded_file and brand and serial_number:
    st.image(uploaded_file, caption=f"Konteks Lapangan: {brand.upper()} {model_name.upper()} | S/N: {serial_number.upper()}", width=500)

    if 'result' not in st.session_state: st.session_state.result = None
    if 'analyzed' not in st.session_state: st.session_state.analyzed = False

    if st.button("🔍 Jalankan Analisis Visual AI"):
        with st.status("Menghubungkan ke Server Pusat & Memindai...", expanded=True) as status:
            res = pure_diagnostic_engine(uploaded_file.getvalue(), brand, model_name, serial_number, comp)
            st.session_state.result = res
            st.session_state.analyzed = True
            status.update(label="Analisis Selesai", state="complete")

    if st.session_state.analyzed and st.session_state.result:
        st.divider()
        res = st.session_state.result
        
        col1, col2, col3 = st.columns(3)
        col1.metric("Skor Integritas (Health)", f"{res.get('score', 0)}%")
        
        with col2:
            st.subheader("Status Komponen")
            status_text = res.get('status', 'Unknown')
            if status_text == "Critical": st.error(status_text)
            elif status_text == "Warning": st.warning(status_text)
            else: st.success(status_text)
            
        with col3:
            st.subheader("Temuan Teknis AI")
            st.write(res.get('note', 'Tidak ada catatan.'))

        parts = res.get('parts_recommendation', [])
        
        # --- 5. GENERATOR PDF & TRIGGER DATABASE ---
        st.divider()
        st.write("### 📄 Eksekusi Laporan & Database")
        
        if st.button("Simpan Data & Cetak Dokumen Resmi"):
            with st.spinner("Memproses Dokumen & Sinkronisasi Database..."):
                doc_id = str(uuid.uuid4()).split('-')[0].upper()
                current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                
                # Eksekusi Database
                if db_connected:
                    # Susunan kolom disesuaikan dengan header Excel
                    data_to_save = [
                        current_time, 
                        f"TA-{doc_id}", 
                        brand.upper(), 
                        model_name.upper(), 
                        serial_number.upper(), 
                        comp, 
                        f"{res.get('score')}%", 
                        status_text, 
                        "Cek PDF untuk Detail Harga"
                    ]
                    is_saved = save_to_database(data_to_save)
                    if is_saved:
                        st.success("✅ Log tersimpan di Master Database AZARINDO.")
                    else:
                        st.warning("⚠️ Gagal menyimpan ke Database, tapi PDF tetap dibuat.")

                # Eksekusi PDF (Desain Mewah)
                pdf = FPDF()
                pdf.add_page()
                
                try: pdf.image('logo.png', 10, 8, 30) 
                except: pass 
                
                pdf.set_font("Arial", "B", 18)
                pdf.set_text_color(41, 128, 185) 
                pdf.cell(0, 10, txt="OFFICIAL INSPECTION REPORT", ln=True, align="R")
                
                pdf.set_font("Arial", "I", 10)
                pdf.set_text_color(128, 128, 128) 
                pdf.cell(0, 5, txt="AZARINDO Heavy Equipment Ecosystem", ln=True, align="R")
                pdf.cell(0, 5, txt=f"Generated: {current_time}", ln=True, align="R")
                
                pdf.set_draw_color(41, 128, 185)
                pdf.set_line_width(0.5)
                pdf.line(10, 35, 200, 35)
                pdf.ln(15)
                
                pdf.set_text_color(0, 0, 0)
                pdf.set_fill_color(240, 240, 240) 
                pdf.set_font("Arial", "B", 12)
                pdf.cell(0, 10, txt="  DATA UNIT LOKASI", border=1, ln=True, fill=True)
                
                pdf.set_font("Arial", "", 11)
                pdf.cell(0, 8, txt=f"  Merek/Model  : {brand.upper()} {model_name.upper()}", border="LR", ln=True)
                pdf.cell(0, 8, txt=f"  Serial Number: {serial_number.upper()}", border="LR", ln=True)
                pdf.cell(0, 8, txt=f"  Komponen     : {comp}", border="LR", ln=True)
                pdf.cell(0, 8, txt=f"  Health Score : {res.get('score', 0)}%  |  Status: {status_text}", border="LRB", ln=True)
                pdf.ln(8)
                
                pdf.set_font("Arial", "B", 12)
                pdf.cell(0, 10, txt="  TEMUAN TEKNIS LAPANGAN", ln=True)
                pdf.set_font("Arial", "", 11)
                safe_note = str(res.get('note', 'Tidak ada catatan.')).encode('latin-1', 'replace').decode('latin-1')
                pdf.multi_cell(0, 7, txt=safe_note)
                pdf.ln(8)
                
                if parts:
                    pdf.set_font("Arial", "B", 12)
                    pdf.cell(0, 10, txt="  REKOMENDASI SUKU CADANG & ESTIMASI BIAYA", ln=True)
                    
                    pdf.set_font("Arial", "B", 10)
                    pdf.set_fill_color(41, 128, 185)
                    pdf.set_text_color(255, 255, 255)
                    pdf.cell(130, 10, "Deskripsi Part", border=1, fill=True)
                    pdf.cell(60, 10, "Estimasi Harga (IDR)", border=1, ln=True, fill=True)
                    
                    pdf.set_font("Arial", "", 10)
                    pdf.set_text_color(0, 0, 0)
                    for p in parts:
                        part_name = str(p.get('part_name', 'Unknown')).encode('latin-1', 'replace').decode('latin-1')
                        est_price = str(p.get('est_price', 'N/A')).encode('latin-1', 'replace').decode('latin-1')
                        pdf.cell(130, 10, part_name, border=1)
                        pdf.cell(60, 10, est_price, border=1, ln=True)
                    
                    pdf.ln(5)
                    pdf.set_font("Arial", "I", 9)
                    pdf.set_text_color(128, 128, 128)
                    pdf.multi_cell(0, 5, txt="*Harga adalah estimasi sistem AI. Hubungi dealer untuk penawaran final.")
                
                pdf.ln(15)
                pdf.set_draw_color(200, 200, 200)
                pdf.line(10, pdf.get_y(), 200, pdf.get_y())
                pdf.ln(5)
                
                pdf.set_font("Arial", "B", 8)
                pdf.set_text_color(0, 0, 0)
                pdf.cell(0, 5, txt="DIGITAL AUTHORIZATION STAMP", ln=True)
                pdf.set_font("Arial", "", 8)
                pdf.cell(0, 5, txt=f"Document ID : TA-{doc_id}-{int(time.time())}", ln=True)
                pdf.cell(0, 5, txt="Verified By : System VORTEX / Mining Inspector Engine", ln=True)
                pdf.cell(0, 5, txt="Status      : SYSTEM GENERATED - NO SIGNATURE REQUIRED", ln=True)
                
                pdf_bytes = pdf.output(dest='S').encode('latin-1')
                
                st.download_button(
                    label="📥 Download Official Report (PDF)", 
                    data=pdf_bytes, 
                    file_name=f"Inspeksi_{serial_number.upper()}_{doc_id}.pdf",
                    mime="application/pdf"
                )
