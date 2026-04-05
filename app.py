import streamlit as st
import google.generativeai as genai
from PIL import Image
import io
import time
import json

# --- 1. KONFIGURASI API (Hanya satu kali) ---
try:
    # Mengambil kunci dari Secrets Streamlit secara aman
    api_key = st.secrets["GOOGLE_API_KEY"]
    genai.configure(api_key=api_key)
except:
    st.error("API Key belum diset di Secrets Streamlit!")

# --- 2. ENGINE DIAGNOSA MURNI ---
# LOGIKA BARU YANG LEBIH TAHAN ERROR:
def pure_diagnostic_engine(image_bytes, brand, model_name, category):
try:
    # Model terbaru dan tercepat
    model_ai = genai.GenerativeModel('gemini-1.5-flash-latest')
except:
    try:
        # Nama model alternatif untuk beberapa region API
        model_ai = genai.GenerativeModel('gemini-1.5-flash')
    except:
        # Cadangan terakhir jika model Flash belum tersedia
        model_ai = genai.GenerativeModel('gemini-pro-vision')

# --- 3. ANTARMUKA PENGGUNA ---
st.set_page_config(page_title="Mining Inspector AI", layout="wide")
st.title("🚜 Mining Inspector AI")
st.subheader("Sistem Analisis Visual Kerusakan Alat Berat")

# Parameter Input Lapangan
with st.sidebar:
    st.header("📋 Parameter Unit")
    brand = st.text_input("Merek Unit", placeholder="Contoh: Tatsuo, AIMIX, Komatsu...")
    model = st.text_input("Tipe/Model", placeholder="Contoh: T-200, PC200...")
    comp = st.selectbox("Komponen Diperiksa", ["Engine Area", "Undercarriage", "Tyre", "Hydraulic"])
    st.divider()
    st.warning("⚠️ Instruksi: Foto komponen dari jarak dekat tanpa menggunakan filter kamera.")

# Area Upload
uploaded_file = st.file_uploader("Upload Foto Aktual Komponen", type=["jpg", "jpeg", "png"])

if uploaded_file and brand:
    # Tampilkan Foto Asli
    img = Image.open(uploaded_file)
    st.image(img, caption=f"Konteks Lapangan: {brand} {model}", width=500)

    # State management untuk hasil analisis
    if 'result' not in st.session_state:
        st.session_state.result = None
    if 'analyzed' not in st.session_state:
        st.session_state.analyzed = False

    if st.button("🔍 Jalankan Analisis Visual AI"):
        with st.status("Memindai anomali struktural...", expanded=True) as status:
            # PEMPERBAIKAN INDENTASI DI SINI
            res = pure_diagnostic_engine(
                uploaded_file.getvalue(), 
                brand, 
                model, 
                comp
            )
            st.session_state.result = res
            st.session_state.analyzed = True
            status.update(label="Analisis Selesai", state="complete")

    # Tampilkan Hasil Analisis jika sudah ada
    if st.session_state.analyzed and st.session_state.result:
        st.divider()
        res = st.session_state.result
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Skor Integritas (Health)", f"{res.get('score', 0)}%")
        
        with c2:
            st.subheader("Status Komponen")
            status_text = res.get('status', 'Unknown')
            if status_text == "Critical": st.error(status_text)
            elif status_text == "Warning": st.warning(status_text)
            else: st.success(status_text)
            
        with c3:
            st.subheader("Temuan AI")
            st.write(res.get('note', 'Tidak ada catatan.'))

        # --- KONVERSI & PDF (Sederhana untuk tes) ---
        st.divider()
        st.write("### 📄 Unduh Laporan Inspeksi Digital")
        if st.button("Generate Laporan & Rekomendasi Part"):
            st.info("Laporan sedang disiapkan...")
            time.sleep(1)
            st.download_button(
                label="📥 Download Report.pdf", 
                data=f"Report {brand} {model} - Status: {status_text}", 
                file_name=f"Inspeksi_{brand}.pdf"
            )
