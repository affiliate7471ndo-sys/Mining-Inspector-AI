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

# --- 3. ENGINE DIAGNOSA MULTI-VISUAL ---
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

        # Prompt disesuaikan untuk membaca BANYAK foto sekaligus
        prompt = f"""Anda adalah Inspektur Alat Berat Senior & Technical Sales AZARINDO. 
        Analisa KUMPULAN FOTO ({len(image_bytes_list)} foto) dari unit {brand} {model_name} (S/N: {serial_number}). Kategori Inspeksi: {category}.
        1. Lakukan inspeksi menyeluruh dari semua foto yang diberikan. Baca panel jika ada, cari kebocoran, retak, atau keausan.
        2. Gabungkan temuan Anda menjadi satu kesimpulan teknis yang komprehensif.
        3. Berikan skor kesehatan keseluruhan (0-100) dan status (Good/Warning/Critical).
        4. Sebutkan daftar suku cadang yang perlu diganti dari SEMUA temuan di foto tersebut.
        
        {katalog_data}
        
        WAJIB cocokkan suku cadang dengan KATALOG di atas.
        Format jawaban WAJIB JSON murni: 
        {{
            "score": angka, 
            "status": "teks", 
            "note": "Kesimpulan panjang dari seluruh foto...", 
            "parts_recommendation": [
                {{"part_name": "Nama Part (Part Number)", "est_price": "Harga Rupiah"}}
            ]
        }}"""

        # Struktur payload dinamis untuk multi-image
        payload = {
            "contents": [{
                "parts": [
                    {"text": prompt}
                ]
            }]
        }
        
        # Menyuntikkan semua foto ke dalam satu paket pengiriman ke Google
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
st.title("🚜 Mining Inspector AI (General Inspection)")
st.subheader("Sistem Analisis Multi-Visual & Database Inspeksi AZARINDO")

if not db_connected:
    st.info("ℹ️ Mode Offline: Database Google Sheets belum terhubung.")

with st.sidebar:
    st.header("📋 Parameter Unit")
    brand = st.text_input("Merek Unit", placeholder="Contoh: Tatsuo, AIMIX...")
    model_name = st.text_input("Tipe/Model", placeholder="Contoh: JP80-9")
    serial_number = st.text_input("Serial Number (S/N)", placeholder="Contoh: 2401X0059")
    # Tambahan opsi General Inspection
    comp = st.selectbox("Kategori Inspeksi", ["General Inspection (Multi-Part)", "Engine Area", "Undercarriage", "Hydraulic System"])
    st.divider()

# PERUBAHAN BESAR: accept_multiple_files = True
uploaded_files = st.file_uploader("Upload Foto Lapangan (Maks 4 Foto untuk hasil optimal)", type=["jpg", "jpeg", "png"], accept_multiple_files=True)

if uploaded_files and brand and serial_number:
    # Membatasi proses maksimal 4 gambar agar tidak terlalu berat
    files_to_process = uploaded_files[:4]
    
    st.write(f"**📸 Konteks Lapangan: {brand.upper()} {model_name.upper()} | S/N: {serial_number.upper()}**")
    
    # Menampilkan grid foto secara dinamis di web
    cols = st.columns(len(files_to_process))
    for idx, f in enumerate(files_to_process):
        cols[idx].image(f, use_container_width=True)

    if 'result' not in st.session_state: st.session_state.result = None
    if 'analyzed' not in st.session_state: st.session_state.analyzed = False

    if st.button("🔍 Jalankan Multi-Analisis AI"):
        with st.status("Memindai seluruh foto & Mencocokkan Katalog...", expanded=True) as status:
            # Mengekstrak bytes dari semua file yang diunggah
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
        
        if st.button("Simpan Data & Cetak Laporan Lengkap"):
            with st.spinner("Menyusun Dokumen PDF Multi-Halaman & Sinkronisasi Database..."):
                doc_id = str(uuid.uuid4()).split('-')[0].upper()
                current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                
                if db_connected:
                    data_to_save = [current_time, f"TA-{doc_id}", brand.upper(), model_name.upper(), serial_number.upper(), comp, f"{res.get('score')}%", status_text, f"{len(files_to_process)} Foto Terlampir"]
                    is_saved = save_to_database(data_to_save)
                    if is_saved:
                        st.success("✅ Log tersimpan di Master Database AZARINDO.")
                
                # --- PDF HALAMAN 1: SUMMARY Laporan ---
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
                
                # --- PDF HALAMAN 2: LAMPIRAN VISUAL (GRID FOTO) ---
                pdf.add_page()
                pdf.set_font("Arial", "B", 14)
                pdf.set_text_color(41, 128, 185)
                pdf.cell(0, 10, txt="LAMPIRAN VISUAL INSPEKSI", ln=True, align="L")
                pdf.set_draw_color(200, 200, 200)
                pdf.line(10, 20, 200, 20)
                pdf.ln(5)

                # Logika cetak foto otomatis ke PDF (2x2 Grid)
                x_pos = 10
                y_pos = pdf.get_y()
                
                for idx, file in enumerate(files_to_process):
                    # Menyimpan gambar sementara untuk dicetak FPDF
                    with tempfile.NamedTemporaryFile(delete=False, suffix='.jpg') as tmp_file:
                        tmp_file.write(file.getvalue())
                        tmp_path = tmp_file.name
                    
                    # Mengatur posisi grid (2 gambar per baris)
                    if idx > 0 and idx % 2 == 0:
                        y_pos += 95 # Turun ke baris baru
                        x_pos = 10
                    
                    try:
                        # Mencetak gambar lebar 90mm
                        pdf.image(tmp_path, x=x_pos, y=y_pos, w=90)
                    except:
                        pass # Abaikan jika gambar rusak
                    
                    # Hapus file sementara
                    os.remove(tmp_path)
                    
                    # Geser X ke kanan untuk gambar sebelah
                    x_pos += 95
                
                # Jeda ke bawah foto terakhir
                pdf.set_y(y_pos + 105)

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
                    label="📥 Download General Inspection Report (PDF)", 
                    data=pdf_bytes, 
                    file_name=f"Inspeksi_{serial_number.upper()}_Multi.pdf",
                    mime="application/pdf"
                )
