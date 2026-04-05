import streamlit as st
from PIL import Image
import time

# --- KONFIGURASI ENGINE ---
st.set_page_config(page_title="Universal Mining AI Diagnostic", layout="wide")

# --- ENGINE DIAGNOSA MURNI (TANPA HAPUS BACKGROUND) ---
import google.generativeai as genai

# Masukkan API Key Anda di sini
genai.configure(api_key="gen-lang-client-0721140806")

def pure_diagnostic_engine(image_bytes, brand, model, category):
    # Konfigurasi Model Vision
    model_ai = genai.GenerativeModel('gemini-1.5-flash')
    
    # Instruksi Spesifik untuk Tambang (Prompt Engineering)
    prompt = f"""
    Anda adalah Inspektur Alat Berat Senior. Analisa foto komponen {category} 
    pada unit {brand} tipe {model} ini. 
    1. Jika ada layar monitor, baca angka/parameter yang muncul (suhu, voltase, tekanan).
    2. Jika ada komponen fisik, cari indikasi aus, retak, atau bocor.
    3. Berikan skor kesehatan (0-100).
    4. Berikan status (Good/Warning/Critical) dan temuan singkat maksimal 2 kalimat.
    Format jawaban harus JSON: {{"score": angka, "status": "teks", "note": "teks"}}
    """
    
    # Kirim ke AI
    img = Image.open(io.BytesIO(image_bytes))
    response = model_ai.generate_content([prompt, img])
    
    # Parsing hasil (Sederhana)
    try:
        # Membersihkan teks agar menjadi JSON murni
        clean_res = response.text.replace('```json', '').replace('```', '').strip()
        import json
        return json.loads(clean_res)
    except:
        return {"score": 0, "status": "Error", "note": "Gagal membaca gambar secara teknis."}

# --- ANTARMUKA PENGGUNA ---
st.title("🚜 Mining Inspector AI")
st.subheader("Sistem Analisis Visual Kerusakan Alat Berat")

# Parameter Input Lapangan
with st.sidebar:
    st.header("📋 Parameter Unit")
    brand = st.text_input("Merek Unit", placeholder="Contoh: Tatsuo, AIMIX, Komatsu...")
    model = st.text_input("Tipe/Model", placeholder="Contoh: T-200, PC200...")
    comp = st.selectbox("Komponen Diperiksa", ["Undercarriage", "Tyre", "Hydraulic", "Engine Area"])
    st.divider()
    st.warning("⚠️ Instruksi: Foto komponen dari jarak dekat tanpa menggunakan filter kamera.")

# Area Upload
uploaded_file = st.file_uploader("Upload Foto Aktual Komponen", type=["jpg", "jpeg", "png"])

if uploaded_file and brand:
    # State management
    if 'analyzed' not in st.session_state:
        st.session_state.analyzed = False

    # Tampilkan Foto Asli (Tanpa dihapus background-nya agar mekanik bisa lihat konteks)
    img = Image.open(uploaded_file)
    st.image(img, caption=f"Konteks Lapangan: {brand} {model}", width=500)

    if st.button("🔍 Jalankan Analisis Visiual AI"):
        with st.status("Memindai anomali struktural...", expanded=True) as status:
            # Pastikan urutan bahannya sesuai dengan definisi fungsi (4 variabel)
st.session_state.result = pure_diagnostic_engine(
    uploaded_file.getvalue(), 
    brand, 
    model, 
    comp
)
            st.session_state.analyzed = True
            status.update(label="Analisis Selesai", state="complete")

    # Hasil Analisis
    if st.session_state.analyzed:
        st.divider()
        res = st.session_state.result
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Skor Integritas (Health)", f"{res['score']}%")
        
        with c2:
            st.subheader("Status Komponen")
            if res['status'] == "Critical": st.error(res['status'])
            elif res['status'] == "Warning": st.warning(res['status'])
            else: st.success(res['status'])
            
        with c3:
            st.subheader("Temuan AI")
            st.write(res['note'])

        # --- KONVERSI & CALL TO ACTION ---
        st.divider()
        st.write("### 📄 Unduh Laporan Inspeksi Digital")
        if st.button("Generate Laporan & Rekomendasi Part (Rp 75.000)"):
            st.info("Sistem mengarahkan ke Gateway Pembayaran...")
            time.sleep(2)
            st.success("Laporan berhasil dibuat. Silakan unduh.")
            st.download_button("📥 Download Report.pdf", data="Data Laporan Tambang", file_name=f"Inspeksi_{brand}.pdf")
