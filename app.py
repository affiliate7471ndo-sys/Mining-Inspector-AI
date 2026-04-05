import streamlit as st
import requests
import base64
import json
import time

# --- 1. KONFIGURASI API ---
try:
    api_key = st.secrets["GOOGLE_API_KEY"]
except:
    api_key = ""
    st.error("⚠️ API Key belum diset di Secrets Streamlit!")

# --- 2. ENGINE DIAGNOSA MURNI (REST API AUTO-SNIPER) ---
def pure_diagnostic_engine(image_bytes, brand, model_name, category):
    if not api_key:
        return {"score": 0, "status": "Error", "note": "API Key kosong. Silakan isi di Secrets."}

    try:
        prompt = f"""Anda adalah Inspektur Alat Berat Senior. Analisa foto {category} unit {brand} {model_name}. 
        1. Baca indikator panel monitor jika ada (RPM, Temp, Voltase).
        2. Cari anomali fisik (aus, retak, bocor).
        3. Berikan skor 0-100, status (Good/Warning/Critical), dan temuan teknis singkat.
        Format jawaban WAJIB JSON murni: {{"score": angka, "status": "teks", "note": "teks"}}"""

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
        
        # --- LOGIKA PELURU GANDA (AUTO-FALLBACK) ---
        # Daftar pintu server dari yang paling baru sampai yang paling lama
        endpoints = [
            "gemini-1.5-flash-latest",
            "gemini-pro-vision", 
            "gemini-1.5-pro-latest"
        ]
        
        last_error = ""
        
        for model in endpoints:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
            response = requests.post(url, headers=headers, json=payload)
            
            if response.status_code == 200:
                # Berhasil tembus!
                data = response.json()
                raw_text = data['candidates'][0]['content']['parts'][0]['text']
                clean_res = raw_text.replace('```json', '').replace('```', '').strip()
                return json.loads(clean_res)
            else:
                # Simpan error terakhir dan coba pintu berikutnya
                last_error = response.text
                continue
                
        # Jika semua pintu ditutup oleh Google
        return {"score": 0, "status": "Error", "note": f"Semua jalur ditolak. Error terakhir: {last_error}"}
            
    except Exception as e:
        return {"score": 0, "status": "Error", "note": f"System Error: {str(e)}"}

# --- 3. ANTARMUKA PENGGUNA ---
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
    st.image(uploaded_file, caption=f"Konteks Lapangan: {brand} {model_name}", width=500)

    if 'result' not in st.session_state:
        st.session_state.result = None
    if 'analyzed' not in st.session_state:
        st.session_state.analyzed = False

    if st.button("🔍 Jalankan Analisis Visual AI"):
        with st.status("Memindai anomali via Direct API...", expanded=True) as status:
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
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Skor Integritas (Health)", f"{res.get('score', 0)}%")
        
        with c2:
            st.subheader("Status Komponen")
            status_text = res.get('status', 'Unknown')
            if status_text == "Critical": st.error(status_text)
            elif status_text == "Warning": st.warning(status_text)
            elif status_text == "Error": st.error(status_text)
            else: st.success(status_text)
            
        with c3:
            st.subheader("Temuan AI")
            st.write(res.get('note', 'Tidak ada catatan.'))

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
