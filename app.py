import streamlit as st
import requests
import base64
import json
import time
from fpdf import FPDF

# --- 1. KONFIGURASI API ---
try:
    api_key = st.secrets["GOOGLE_API_KEY"]
except:
    api_key = ""

# --- 2. ENGINE DIAGNOSA MURNI (AUTO-DISCOVERY REST API & AUTO-QUOTATION) ---
def pure_diagnostic_engine(image_bytes, brand, model_name, category):
    if not api_key:
        return {"score": 0, "status": "Error", "note": "API Key kosong. Silakan isi di Secrets Streamlit."}

    try:
        # TAHAP 1: AUTO-DISCOVERY MODEL
        list_url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
        list_res = requests.get(list_url)
        
        if list_res.status_code != 200:
            return {"score": 0, "status": "Error", "note": "Gagal melakukan handshake dengan server Google."}
            
        available_models = list_res.json().get('models', [])
        chosen_model = None
        
        for m in available_models:
            methods = m.get('supportedGenerationMethods', [])
            name = m.get('name', '') 
            
            if 'generateContent' in methods:
                if 'flash' in name or 'pro' in name or 'vision' in name:
                    chosen_model = name
                    break
        
        if not chosen_model:
            return {"score": 0, "status": "Error", "note": "API Key Anda tidak memiliki akses ke model Vision/AI apapun."}

        # TAHAP 2: EKSEKUSI DIAGNOSA (DENGAN PROMPT ESTIMASI HARGA)
        prompt = f"""Anda adalah Inspektur Alat Berat Senior sekaligus Technical Sales Advisor. 
        Analisa foto {category} unit {brand} {model_name}. 
        1. Baca indikator panel monitor jika ada (RPM, Temp, Voltase).
        2. Cari anomali fisik (aus, retak, bocor).
        3. Berikan skor 0-100, status (Good/Warning/Critical), dan temuan teknis singkat.
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
        payload = {
            "contents": [{
                "parts": [
                    {"text": prompt},
                    {
                        "inline_data": {
                            "mime_type": "image/jpeg",
                            "data": base64_img
                        }
                    }
                ]
            }]
        }
        headers = {"Content-Type": "application/json"}
        
        execute_url = f"https://generativelanguage.googleapis.com/v1beta/{chosen_model}:generateContent?key={api_key}"
        response = requests.post(execute_url, headers=headers, json=payload)
        
        if response.status_code == 200:
            data = response.json()
            raw_text = data['candidates'][0]['content']['parts'][0]['text']
            clean_res = raw_text.replace('```json', '').replace('```', '').strip()
            return json.loads(clean_res)
        else:
            return {"score": 0, "status": "Error", "note": f"Eksekusi API gagal: {response.text}"}
            
    except Exception as e:
        return {"score": 0, "status": "Error", "note": f"System Error: {str(e)}"}

# --- 3. ANTARMUKA PENGGUNA (UI) ---
st.set_page_config(page_title="Mining Inspector AI", layout="wide")
st.title("🚜 Mining Inspector AI")
st.subheader("Sistem Analisis Visual Kerusakan Alat Berat")

with st.sidebar:
    st.header("📋 Parameter Unit")
    brand = st.text_input("Merek Unit", placeholder="Contoh: Tatsuo, AIMIX, Komatsu...")
    model_name = st.text_input("Tipe/Model", placeholder="Contoh: T-200, PC200...")
    comp = st.selectbox("Komponen Diperiksa", ["Engine Area", "Undercarriage", "Tyre", "Hydraulic"])
    st.divider()
    st.warning("⚠️ Instruksi: Foto komponen dari jarak dekat tanpa filter.")

uploaded_file = st.file_uploader("Upload Foto Aktual Komponen", type=["jpg", "jpeg", "png"])

if uploaded_file and brand:
    st.image(uploaded_file, caption=f"Konteks Lapangan: {brand.upper()} {model_name.upper()}", width=500)

    if 'result' not in st.session_state:
        st.session_state.result = None
    if 'analyzed' not in st.session_state:
        st.session_state.analyzed = False

    if st.button("🔍 Jalankan Analisis Visual AI"):
        with st.status("Menghubungkan ke Server Pusat & Memindai Anomali...", expanded=True) as status:
            res = pure_diagnostic_engine(
                uploaded_file.getvalue(), 
                brand, 
                model_name, 
                comp
            )
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
            elif status_text == "Error": st.error(status_text)
            else: st.success(status_text)
            
        with col3:
            st.subheader("Temuan Teknis AI")
            st.write(res.get('note', 'Tidak ada catatan anomali.'))

        # Menampilkan UI Rekomendasi Part
        st.subheader("🛠️ Rekomendasi Suku Cadang")
        parts = res.get('parts_recommendation', [])
        if parts:
            for p in parts:
                st.info(f"**{p.get('part_name', 'Part Unknown')}** — Estimasi: {p.get('est_price', 'N/A')}")
        else:
            st.write("Tidak ada penggantian part mendesak berdasarkan temuan visual saat ini.")

        # --- 4. GENERATOR LAPORAN PDF (FPDF) ---
        st.divider()
        st.write("### 📄 Unduh Laporan Inspeksi Digital")
        
        if st.button("Generate Laporan & Penawaran Part"):
            with st.spinner("Menyusun dokumen penawaran resmi..."):
                pdf = FPDF()
                pdf.add_page()
                
                pdf.set_font("Arial", "B", 16)
                pdf.cell(200, 10, txt="LAPORAN INSPEKSI & PENAWARAN SUKU CADANG", ln=True, align="C")
                pdf.set_font("Arial", "I", 10)
                pdf.cell(200, 10, txt=f"Official Report for {brand.upper()} Ecosystem", ln=True, align="C")
                pdf.ln(10)
                
                pdf.set_font("Arial", "B", 12)
                pdf.cell(0, 10, txt="DETAIL UNIT:", ln=True)
                pdf.set_font("Arial", "", 12)
                pdf.cell(0, 8, txt=f"Unit      : {brand.upper()} {model_name.upper()}", ln=True)
                pdf.cell(0, 8, txt=f"Kategori  : {comp}", ln=True)
                pdf.ln(5)
                
                pdf.set_font("Arial", "B", 12)
                pdf.cell(0, 10, txt="ANALISIS TEKNIS:", ln=True)
                pdf.set_font("Arial", "", 11)
                
                # Membersihkan teks untuk FPDF agar tidak error membaca karakter aneh
                safe_note = str(res.get('note', 'Tidak ada catatan khusus.')).encode('latin-1', 'replace').decode('latin-1')
                pdf.multi_cell(0, 7, txt=safe_note)
                pdf.ln(5)
                
                # Cek jika ada rekomendasi part untuk dimasukkan ke tabel
                if parts:
                    pdf.set_font("Arial", "B", 12)
                    pdf.cell(0, 10, txt="REKOMENDASI SUKU CADANG & ESTIMASI BIAYA:", ln=True)
                    
                    # Header Tabel
                    pdf.set_font("Arial", "B", 10)
                    pdf.cell(130, 10, "Deskripsi Part", 1)
                    pdf.cell(60, 10, "Estimasi Harga (IDR)", 1, ln=True)
                    
                    # Isi Tabel
                    pdf.set_font("Arial", "", 10)
                    for p in parts:
                        part_name = str(p.get('part_name', 'Unknown')).encode('latin-1', 'replace').decode('latin-1')
                        est_price = str(p.get('est_price', 'N/A')).encode('latin-1', 'replace').decode('latin-1')
                        
                        pdf.cell(130, 10, part_name, 1)
                        pdf.cell(60, 10, est_price, 1, ln=True)
                    
                    pdf.ln(10)
                    pdf.set_font("Arial", "I", 9)
                    pdf.multi_cell(0, 5, txt="*Harga di atas adalah estimasi sistem AI. Silakan hubungi dealer resmi untuk penawaran final.")
                
                pdf_bytes = pdf.output(dest='S').encode('latin-1')
                
                st.success("Laporan Penawaran berhasil dibuat!")
                st.download_button(
                    label="📥 Download Penawaran Suku Cadang (PDF)", 
                    data=pdf_bytes, 
                    file_name=f"Penawaran_{brand}_{model_name}.pdf",
                    mime="application/pdf"
                )
