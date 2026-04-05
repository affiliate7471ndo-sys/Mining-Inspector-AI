import streamlit as st
from PIL import Image
import time

# --- KONFIGURASI ENGINE ---
st.set_page_config(page_title="Universal Mining AI Diagnostic", layout="wide")

# --- ENGINE DIAGNOSA MURNI (TANPA HAPUS BACKGROUND) ---
def pure_diagnostic_engine(image_bytes, category):
    # Simulasi AI Computer Vision menganalisis piksel asli (termasuk debu, oli, dan tanah)
    time.sleep(2) 
    
    # Database Logika Standar Global
    db_logic = {
        "Undercarriage": {"score": 55, "status": "Warning", "note": "Keausan pada sproket dan track link. Terlihat tumpukan lumpur keras yang mengganggu pergerakan."},
        "Tyre": {"score": 30, "status": "Critical", "note": "Sayatan dalam pada dinding ban (Sidewall cut) sepanjang 15cm. Risiko pecah tinggi."},
        "Hydraulic": {"score": 85, "status": "Good", "note": "Silinder hidrolik kering. Tidak ada indikasi rembesan oli pada area sekitar."},
        "Engine Area": {"score": 70, "status": "Check", "note": "Warna blok mesin mengindikasikan *overheating* ringan. Cek sistem pendingin."}
    }
    return db_logic.get(category, {"score": 95, "status": "Normal", "note": "Komponen dalam batas toleransi aman."})

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
            st.session_state.result = pure_diagnostic_engine(uploaded_file.getvalue(), comp)
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