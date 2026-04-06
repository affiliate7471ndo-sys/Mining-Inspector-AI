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
from datetime import datetime
from fpdf import FPDF
from google.oauth2.service_account import Credentials

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

# --- 2. ENGINE PEMBACA KATALOG (RAG SYSTEM) ---
def load_catalog_context():
    try:
        df = pd.read_csv('katalog.csv')
        catalog_text = "REFERENSI KATALOG HARGA AZARINDO:\n"
        catalog_text += df.to_string(index=False)
        return catalog_text
    except Exception as e:
        return "KATALOG TIDAK DITEMUKAN. Gunakan estimasi wajar."

# --- 3. ENGINE DIAGNOSA MULTI-VISUAL (UP TO 10 IMAGES) ---
def pure_diagnostic_engine(image_bytes_list, brand, model_name, serial_number, category):
    if not api_key:
        return {"score": 0, "status": "Error", "note": "API Key kosong."}

    try:
        list_url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
        list_res = requests.get(list_url)
        available_models = list_res.json().get('models', [])
        chosen_model = next((m['name'] for m in available_models if 'generateContent' in m.get('supportedGenerationMethods', []) and ('flash' in m['name'] or 'pro' in m['name'] or 'vision' in m['name'])), None)

        if not chosen_model:
            return {"score": 0, "status": "Error", "note": "Akses model Vision ditolak."}

        katalog_data = load_catalog_context()

        prompt = f"""Anda adalah Inspektur Alat Berat Senior AZARINDO. 
        Analisa KUMPULAN FOTO (Total: {len(image_bytes_list)} foto) dari unit {brand} {model_name} (S/N: {serial_number}). 
        Kategori Inspeksi: {category}.
        1. Lakukan inspeksi menyeluruh dari SEMUA foto. Hubungkan temuan dari foto satu dengan foto lainnya.
        2. Gabungkan temuan menjadi satu kesimpulan teknis yang solid.
        3. Berikan skor kesehatan keseluruhan (0-100) dan status (Good/Warning/Critical).
        4. Sebutkan daftar suku cadang yang perlu diganti dari SELURUH anomali di foto tersebut.
        
        {katalog_data}
        
        WAJIB cocokkan suku cadang dengan KATALOG di atas jika tersedia.
        Format jawaban WAJIB JSON murni: 
        {{
            "score": angka, 
            "status": "teks", 
            "note": "Kesimpulan komprehensif...", 
            "parts_recommendation": [
                {{"part_name": "Nama Part (Part Number)", "est_price": "Harga Rupiah"}}
            ]
        }}"""

        payload = {
            "contents": [{
                "parts": [
                    {"text": prompt}
                ]
            }]
        }
        
        for img_bytes in image_bytes_list:
            base64_img = base64.b64encode(img_bytes).decode('utf-8')
            payload["contents"][0]["parts"].append({
                "inline_data": {
                    "mime_type": "image/jpeg",
                    "data": base64_img
                }
            })

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

# --- 4. FUNGSI DATABASE ---
def save_to_database(data_row):
    if not db_connected: return False
    try:
        sheet = client.open_by_key(sheet_id).get_worksheet(0)
        sheet.append_row(data_row)
        return True
    except:
        return False

# --- 5. ANTARMUKA PENGGUNA (UI) ---
st.set_page_config(page_title="Mining Inspector AI", layout="wide")
st.title("🚜 Mining Inspector AI (Heavy-Duty Inspection)")
st.subheader("Sistem Analisis Multi-Visual (Maks 10 Foto) & Database AZARINDO")

if not db_connected:
    st.info("ℹ️ Mode Offline: Database Google Sheets belum terhubung.")

with st.sidebar:
    st.header("📋 Parameter Unit")
    brand = st.text_input("Merek Unit", placeholder="Contoh: Tatsuo, AIMIX...")
    model_name = st.text_input("Tipe/Model", placeholder="Contoh: JP80-9")
    serial_number = st.text_input("Serial Number (S/N)", placeholder="Contoh: 2401X0059")
    comp = st.selectbox("Kategori Inspeksi", ["General Inspection (Multi-Part)", "Engine Area", "Undercarriage", "Hydraulic System"])
    st.divider()

uploaded_files = st.file_uploader("Upload Foto Lapangan (Maks 10 Foto)", type=["jpg", "jpeg", "png"], accept_multiple_files=True)

if uploaded_files and brand and serial_number:
    files_to_process = uploaded_files[:10] 
    
    st.write(f"**📸 Konteks Lapangan: {brand.upper()} {model_name.upper()} | S/N: {serial_number.upper()} ({len(files_to_process)} Titik Inspeksi)**")
    
    for i in range(0, len(files_to_process), 5):
        cols = st.columns(5)
        for j, f in enumerate(files_to_process[i:i+5]):
            cols[j].image(f, use_container_width=True)

    if 'result' not in st.session_state: st.session_state.result = None
    if 'analyzed' not in st.session_state: st.session_state.analyzed = False

    if st.button("🔍 Jalankan AI Heavy-Duty Scan"):
        with st.status(f"Menganalisa {len(files_to_process)} foto secara paralel...", expanded=True) as status:
            image_bytes_list = [f.getvalue() for f in files_to_process]
            res = pure_diagnostic_engine(image_bytes_list, brand, model_name, serial_number, comp)
            
            st.session_state.result = res
            st.session_state.analyzed = True
            status.update(label="Analisis Selesai", state="complete")

    if st.session_state.analyzed and st.session_state.result:
        st.divider()
        res = st.session_state.result
        
        col1, col2, col3 = st.columns(3)
        col1.metric("Skor Integritas (Health)", f"{res.get('score', 0)}%")
        
        with col2:
            st.subheader("Status Unit")
            status_text = res.get('status', 'Unknown')
            if status_text == "Critical": st.error(status_text)
            elif status_text == "Warning": st.warning(status_text)
            else: st.success(status_text)
            
        with col3:
            st.subheader("Kesimpulan Inspeksi Menyeluruh")
            st.write(res.get('note', 'Tidak ada catatan.'))

        parts = res.get('parts_recommendation', [])
        
        st.divider()
        st.write("### 📄 Eksekusi Laporan General Inspection & Database")
        
        if st.button("Simpan Data & Cetak Laporan Lengkap (PDF)"):
            with st.spinner("Menyusun Dokumen PDF Multi-Halaman..."):
                doc_id = str(uuid.uuid4()).split('-')[0].upper()
                current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                
                if db_connected:
                    data_to_save = [current_time, f"TA-{doc_id}", brand.upper(), model_name.upper(), serial_number.upper(), comp, f"{res.get('score')}%", status_text, f"{len(files_to_process)} Foto Terlampir"]
                    save_to_database(data_to_save)
                
                pdf = FPDF()
                pdf.add_page()
                try: pdf.image('logo.png', 10, 8, 30) 
                except: pass 
                
                pdf.set_font("Arial", "B", 18)
                pdf.set_text_color(41, 128, 185) 
                pdf.cell(0, 10, txt="GENERAL INSPECTION REPORT", ln=True, align="R")
                
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
                pdf.cell(0, 8, txt=f"  Kategori     : {comp} ({len(files_to_process)} Titik Inspeksi)", border="LR", ln=True)
                pdf.cell(0, 8, txt=f"  Health Score : {res.get('score', 0)}%  |  Status: {status_text}", border="LRB", ln=True)
                pdf.ln(8)
                
                pdf.set_font("Arial", "B", 12)
                pdf.cell(0, 10, txt="  KESIMPULAN INSPEKSI MENYELURUH", ln=True)
                pdf.set_font("Arial", "", 11)
                safe_note = str(res.get('note', 'Tidak ada catatan.')).encode('latin-1', 'replace').decode('latin-1')
                pdf.multi_cell(0, 7, txt=safe_note)
                pdf.ln(8)
                
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
                
                # --- PDF HALAMAN LANJUTAN: AUTO-PAGINATION FOTO ---
                pdf.add_page()
                pdf.set_font("Arial", "B", 14)
                pdf.set_text_color(41, 128, 185)
                pdf.cell(0, 10, txt="LAMPIRAN VISUAL INSPEKSI", ln=True, align="L")
                pdf.set_draw_color(200, 200, 200)
                pdf.line(10, 20, 200, 20)
                pdf.ln(5)

                x_start = 10
                y_start = 30
                x_offset = 95
                y_offset = 110 # Jarak antar baris foto dilebarkan
                
                for idx, file in enumerate(files_to_process):
                    if idx > 0 and idx % 4 == 0:
                        pdf.add_page()
                        pdf.set_font("Arial", "B", 14)
                        pdf.set_text_color(41, 128, 185)
                        pdf.cell(0, 10, txt="LAMPIRAN VISUAL INSPEKSI (Lanjutan)", ln=True, align="L")
                        pdf.set_draw_color(200, 200, 200)
                        pdf.line(10, 20, 200, 20)

                    col = idx % 2
                    row = (idx % 4) // 2
                    
                    x_pos = x_start + (col * x_offset)
                    y_pos = y_start + (row * y_offset)
                    
                    with tempfile.NamedTemporaryFile(delete=False, suffix='.jpg') as tmp_file:
                        tmp_file.write(file.getvalue())
                        tmp_path = tmp_file.name
                    
                    try:
                        pdf.image(tmp_path, x=x_pos, y=y_pos, w=85) # Lebar 85 agar muat aman di kertas
                    except:
                        pass 
                    
                    os.remove(tmp_path)
                
                # --- FIX DIGITAL STAMP OVERLAP ---
                final_row = ((len(files_to_process) - 1) % 4) // 2
                
                # Jika foto terakhir jatuh pada baris bawah (row == 1), 
                # FPDF akan memecah halaman khusus untuk stamp agar tidak tertimpa foto portrait panjang.
                if final_row == 1:
                    pdf.add_page()
                
                # Kunci posisi di dasar halaman (absolute y-axis dari bawah)
                pdf.set_y(-35) 
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
                    label="📥 Download Heavy-Duty Report (PDF)", 
                    data=pdf_bytes, 
                    file_name=f"Inspeksi_{serial_number.upper()}_Multi.pdf",
                    mime="application/pdf"
                )
