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

# --- 2. ENGINE DIAGNOSA MURNI (AUTO-DISCOVERY REST API) ---
def pure_diagnostic_engine(image_bytes, brand, model_name, category):
    if not api_key:
        return {"score": 0, "status": "Error", "note": "API Key kosong. Silakan isi di Secrets."}

    try:
        # TAHAP 1: AUTO-DISCOVERY (Membaca "Menu" dari Google)
        list_url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
        list_res = requests.get(list_url)
        
        if list_res.status_code != 200:
            return {"score": 0, "status": "Error", "note": "Gagal membaca daftar model dari server Google."}
            
        available_models = list_res.json().get('models', [])
        chosen_model = None
        
        # Mencari model yang mendukung 'generateContent' dan cocok untuk gambar
        for m in available_models:
            methods = m.get('supportedGenerationMethods', [])
            name = m.get('name', '') # Outputnya otomatis berbentuk 'models/nama-model'
            
            if 'generateContent' in methods:
                # Prioritaskan model Flash atau Pro yang memiliki kemampuan Vision
                if 'flash' in name or 'pro' in name or 'vision' in name:
                    chosen_model = name
                    break
        
        if not chosen_model:
            return {"score": 0, "status": "Error", "note": "API Key Anda tidak memiliki akses ke model Vision/AI apapun."}

        # TAHAP 2: EKSEKUSI DIAGNOSA
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
        
        # Menembak tepat ke model yang sudah dikonfirmasi aktif oleh Google
        execute_url = f"https://generativelanguage.googleapis.com/v1beta/{chosen_model}:generateContent?key={api_key}"
        response = requests.post(execute_url, headers=headers, json=payload)
        
        if response.status_code == 200:
            data = response.json()
            raw_text = data['candidates'][0]['content']['parts'][0]['text']
            clean_res = raw_text.replace('```json', '').replace('```', '').strip()
            return json.loads(clean_res)
        else:
            return {"score": 0, "status": "Error", "note": f"Eksekusi gagal pada {chosen_model}: {response.text}"}
            
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
        with st.status("Melakukan Handshake dengan Server Google...", expanded=True) as status:
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
