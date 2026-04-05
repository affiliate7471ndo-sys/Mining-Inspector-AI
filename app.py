import streamlit as st
import google.generativeai as genai
from PIL import Image
import io
import time
import json

# --- 1. KONFIGURASI API ---
try:
    api_key = st.secrets["GOOGLE_API_KEY"]
    genai.configure(api_key=api_key)
except:
    st.error("⚠️ API Key belum diset di Secrets Streamlit!")

# --- 2. ENGINE DIAGNOSA MURNI (LOGIKA AI) ---
def pure_diagnostic_engine(image_bytes, brand, model_name, category):
    # Inisialisasi Model di dalam fungsi
    try:
        model_ai = genai.GenerativeModel('gemini-1.5-flash')
    except:
        model_ai = genai.GenerativeModel('gemini-pro-vision')

    try:
        prompt = f"""
        Anda adalah Inspektur Alat Berat Senior. Analisa foto komponen {category} 
        pada unit {brand} tipe {model_name} ini. 
        1. Jika ada layar monitor/panel, baca angka RPM, Suhu, Voltase, dan Tekanan.
        2. Jika ada komponen fisik, cari indikasi aus, retak, kebocoran oli, atau kerusakan.
        3. Berikan skor kesehatan (0-100).
        4. Berikan status (Good/Warning/Critical) dan temuan singkat maksimal 2 kalimat.
        Format jawaban WAJIB JSON murni: {{"score": angka, "status": "teks", "note": "teks"}}
        """
        
        img = Image.open(io.BytesIO(image_bytes))
        response = model_ai.generate_content([prompt, img])
        
        # Bersihkan hasil dan muat JSON
        clean_res = response.text.replace('```json', '').replace('```', '').strip()
        return json.loads(clean_res)
    except Exception as e:
        return {"score": 0, "status": "Error", "note": f"AI Error: {str(e)}"}

# --- 3. ANTARMUKA PENGGUNA ---
st.set_page_config(page_title="Mining Inspector AI", layout="wide")
st.title("🚜 Mining Inspector AI")
st.subheader("Sistem Analisis Visual Kerusakan Alat Berat")

# Parameter Input Lapangan
with st.sidebar:
    st.header("📋 Parameter Unit")
    brand = st.text_input("Merek Unit", placeholder="Contoh: Tatsuo, AIMIX, Komatsu...")
    model_name = st.text_input("Tipe/Model", placeholder="Contoh: T-200, PC200...")
    comp = st.selectbox("Komponen Diperiksa", ["Engine Area", "Undercarriage", "Tyre", "Hydraulic"])
    st.divider()
    st.warning("⚠️ Instruksi: Foto komponen dari jarak dekat tanpa menggunakan filter kamera.")

# Area Upload
uploaded_file = st.file_uploader("Upload Foto Aktual Komponen", type=["jpg", "jpeg", "png"])

if uploaded_file and brand:
    # Tampilkan Foto Asli
    img = Image.open(uploaded_file)
    st.image(img, caption=f"Konteks Lapangan: {brand} {model_name}", width=500)

    # State management
    if 'result' not in st.session_state:
        st.session_state.result = None
    if 'analyzed' not in st.session_state:
        st.session_state.analyzed = False

    if st.button("🔍 Jalankan Analisis Visual AI"):
        with st.status("Memindai anomali struktural...", expanded=True) as status:
            # Memanggil fungsi yang sudah didefinisikan di atas
            res = pure_diagnostic_engine(
                uploaded_file.getvalue(), 
                brand, 
                model_name, 
                comp
            )
            st.session_state.result = res
            st.session_state.analyzed = True
            status.update(label="Analisis Selesai", state="complete")

    # Tampilkan Hasil Analisis
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

        # --- LAPORAN ---
        st.divider()
        st.write("### 📄 Unduh Laporan Inspeksi Digital")
        if st.button("Generate Laporan & Rekomendasi Part"):
            st.info("Laporan sedang disiapkan...")
            time.sleep(1)
            st.download_button(
                label="📥 Download Report.pdf", 
                data=f"Report {brand} {model_name} - Status: {status_text}\nNote: {res.get('note')}", 
                file_name=f"Inspeksi_{brand}.pdf"
            )
