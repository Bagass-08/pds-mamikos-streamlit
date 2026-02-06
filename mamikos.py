import streamlit as st
import pandas as pd
import time
import random
import folium
from streamlit_folium import st_folium
from collections import Counter
from geopy.geocoders import Nominatim
from geopy.distance import geodesic # Tambahan sisipan untuk fitur hitung jarak
from geopy.extra.rate_limiter import RateLimiter
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from webdriver_manager.core.os_manager import ChromeType
import plotly.express as px

# --- 1. KONFIGURASI HALAMAN ---
st.set_page_config(
    page_title="GIS Indekos & Smart Recommendation",
    page_icon="🏠",
    layout="wide"
)

# --- 2. FUNGSI PEMBERSIH & BANTUAN ---
def clean_lokasi_name(nama_lokasi):
    """Membersihkan nama lokasi: Menghapus kata 'Kecamatan'"""
    if pd.isna(nama_lokasi) or nama_lokasi == "-":
        return "-"
    # Ubah ke Title Case dan hapus kata kunci
    clean = nama_lokasi.replace("Kecamatan ", "").replace("kecamatan ", "").replace("Kelurahan ", "").strip()
    return clean

def extract_tipe_kos_manual(row):
    """[FITUR BARU] Deteksi tipe kos jika upload file CSV lama"""
    teks = (str(row['Nama Kost']) + " " + str(row.get('Link', ''))).lower()
    if 'putri' in teks: return 'Putri'
    elif 'putra' in teks: return 'Putra'
    elif 'pasutri' in teks: return 'Pasutri'
    else: return 'Campur'

#--- 3. FUNGSI GEOCODING (LETAK PETA AKURAT) ---
def add_accurate_coordinates(df, city_context):
    geolocator = Nominatim(user_agent="kos_app_smart_geo_v1")
    
    st.info(f"🗺️ Sedang melakukan Geocoding (Memetakan koordinat kecamatan di {city_context})...")
    progress_bar = st.progress(0)
    
    unique_locs = df['Lokasi Clean'].unique()
    loc_map = {}
    
    for i, loc in enumerate(unique_locs):
        progress_bar.progress(int((i / len(unique_locs)) * 100))
        if loc == "-" or pd.isna(loc):
            loc_map[loc] = None
            continue
        try:
            query = f"{loc}, {city_context}, Indonesia"
            loc_data = geolocator.geocode(query, timeout=10)
            if not loc_data:
                loc_data = geolocator.geocode(f"{loc}, Indonesia", timeout=10)
            
            if loc_data:
                loc_map[loc] = (loc_data.latitude, loc_data.longitude)
            else:
                loc_map[loc] = None
        except:
            loc_map[loc] = None
            
    progress_bar.empty()
    
    latitudes = []
    longitudes = []
    
    try:
        center = geolocator.geocode(f"{city_context}, Indonesia")
        c_lat, c_lon = center.latitude, center.longitude
    except:
        c_lat, c_lon = -6.9175, 107.6191

    for index, row in df.iterrows():
        coords = loc_map.get(row['Lokasi Clean'])
        if coords:
            latitudes.append(coords[0] + random.uniform(-0.002, 0.002))
            longitudes.append(coords[1] + random.uniform(-0.002, 0.002))
        else:
            latitudes.append(c_lat + random.uniform(-0.03, 0.03))
            longitudes.append(c_lon + random.uniform(-0.03, 0.03))
            
    df['lat'] = latitudes
    df['lon'] = longitudes
    return df

# --- 4. FUNGSI SCRAPER (LOGIKA ASLI + FORBIDDEN SKIP + TIPE KOS + DESKRIPSI ASLI) ---
def run_scraper_final_fix(daerah, target_count):
    # Setup Progress di Streamlit
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    # --- SETUP CHROME OPTIONS ---
    # --- SETUP CHROME OPTIONS ---
    options = Options()
    options.page_load_strategy = 'eager'
    prefs = {"profile.managed_default_content_settings.images": 2}
    options.add_experimental_option("prefs", prefs)
    options.add_argument("--disable-blink-features=AutomationControlled") 
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")
    
    driver = None

    # --- LOGIKA HYBRID: COBA LOCAL DULU, KALAU GAGAL PAKAI CLOUD ---
    try:
        # [OPSI 1] MODE LOCAL (Windows/Laptop)
        # Kita coba install driver yang sesuai dengan Chrome di laptop
        service = Service(ChromeDriverManager().install())
        options.add_argument("--start-maximized") # Local bisa pakai layar
        driver = webdriver.Chrome(service=service, options=options)
        print("✅ Menggunakan Driver LOCAL (Google Chrome)")
    
    except Exception as e_local:
        print(f"⚠️ Mode Local Gagal ({e_local}). Beralih ke Mode Cloud...")
        try:
            # [OPSI 2] MODE CLOUD (Streamlit Cloud / Linux)
            # Wajib Headless & Chromium
            options.add_argument("--headless") 
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--disable-gpu")
            
            # Perhatikan baris ini: ChromeType.CHROMIUM
            service = Service(ChromeDriverManager(chrome_type=ChromeType.CHROMIUM).install())
            driver = webdriver.Chrome(service=service, options=options)
            print("✅ Menggunakan Driver CLOUD (Chromium)")
            
        except Exception as e_cloud:
            st.error(f"❌ Gagal Membuka Browser (Local & Cloud Error): {e_cloud}")
            return pd.DataFrame()

    wait = WebDriverWait(driver, 20)
    
    clean_daerah_url = daerah.lower().strip().replace(" ", "-")
    base_url = f"https://mamikos.com/kost/kost-{clean_daerah_url}-murah"
    
    status_text.text(f"🌍 Membuka URL: {base_url}")
    driver.get(base_url)
    main_window = driver.current_window_handle
    
    # --- PENGGANTI INPUT MANUAL ---
    status_text.warning("⚠️ Browser Terbuka! Anda punya 20 detik untuk Login/Captcha manual jika muncul...")
    time.sleep(20) 
    status_text.text("✅ Waktu habis. Mulai scanning otomatis...")
    
    all_data = []
    
    try:
        # Loop sesuai target user
        for i in range(target_count):
            # Update Progress Bar Streamlit
            persen = int((i / target_count) * 100)
            progress_bar.progress(persen)
            status_text.text(f"🔄 [Antrean {i+1}] Memproses...")
            
            try:
                if driver.current_window_handle != main_window:
                    driver.switch_to.window(main_window)

                # ======================================================
                # 1. CARI KARTU & PINDAH HALAMAN
                # ======================================================
                cards = driver.find_elements(By.CSS_SELECTOR, ".kost-rc, [data-testid='roomCard']")
                
                # Pagination Logic
                if i > 0 and i % 20 == 0:
                    status_text.text(f"➡️ Pindah ke Halaman Berikutnya (Data ke-{i+1})...")
                    try:
                        next_button = driver.find_element(By.XPATH, "//ul[contains(@class, 'pagination')]/li[last()]/a")
                        driver.execute_script("arguments[0].click();", next_button)
                        time.sleep(5)
                        cards = driver.find_elements(By.CSS_SELECTOR, ".kost-rc, [data-testid='roomCard']")
                    except Exception as e:
                        print(f"⚠️ Gagal Pindah Halaman: {e}")
            
                # ======================================================
                # 2. PILIH KARTU
                # ======================================================
                local_index = i % 20
                
                if local_index >= len(cards):
                    time.sleep(2)
                    cards = driver.find_elements(By.CSS_SELECTOR, ".kost-rc, [data-testid='roomCard']")
                    if local_index >= len(cards):
                        print("⚠️ Data habis. Skip.")
                        continue

                target_card = cards[local_index]
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", target_card)
                time.sleep(1)

                # KLIK BUKA TAB BARU
                try: clickable = target_card.find_element(By.CLASS_NAME, "rc-info__name")
                except: clickable = target_card.find_element(By.CSS_SELECTOR, ".bg-c-image")

                old_tabs = driver.window_handles
                driver.execute_script("arguments[0].click();", clickable)
                
                try:
                    wait.until(EC.new_window_is_opened(old_tabs))
                    new_tabs = driver.window_handles
                    new_tab = [t for t in new_tabs if t not in old_tabs][0]
                    driver.switch_to.window(new_tab)
                except:
                    print("⚠️ Gagal buka tab. Skip.")
                    continue

                # ======================================================
                # [FITUR BARU] CEK FORBIDDEN (SKIP ERROR)
                # ======================================================
                time.sleep(2)
                if "Forbidden" in driver.title or "403" in driver.title:
                    print("⚠️ Terdeteksi Forbidden/Error. Skip data ini...")
                    driver.close()
                    driver.switch_to.window(main_window)
                    continue 

                # ======================================================
                # 3. SCRAPE DETAIL (LOGIKA LENGKAP)
                # ======================================================
                time.sleep(1) 
                total_height = driver.execute_script("return document.body.scrollHeight")
                for scroll_pos in range(0, total_height, 700):
                    driver.execute_script(f"window.scrollTo(0, {scroll_pos});")
                    time.sleep(0.5)
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(1)

                # AMBIL DATA
                try:
                    # Nama
                    try: nama = driver.find_element(By.CLASS_NAME, "detail-title__room-name").text
                    except: 
                        try: nama = driver.find_element(By.TAG_NAME, "h1").text
                        except: nama = driver.title

                    # Lokasi
                    try:
                        lok_elem = driver.find_element(By.CSS_SELECTOR, ".detail-kost-overview__area-text")
                        lokasi = driver.execute_script("return arguments[0].textContent;", lok_elem).strip()
                    except: lokasi = "-"

                    # --- SISIPAN LOGIKA LANDMARK (TEMPAT TERDEKAT & TRANSPORTASI) ---
                    landmarks_info = []
                    try:
                        landmark_items = driver.find_elements(By.CSS_SELECTOR, "[data-testid='landmark-item']")
                        for item in landmark_items:
                            try:
                                nama_tempat = item.find_element(By.CLASS_NAME, "landmark-item__text-ellipsis").text
                                jarak_tempat = item.find_element(By.CLASS_NAME, "landmark-item__landmark-distance").text
                                landmarks_info.append(f"{nama_tempat} ({jarak_tempat})")
                            except: continue
                    except:
                        landmarks_info = ["Informasi landmark tidak ditemukan"]

                    try:
                        story_raw = driver.find_element(By.ID, "kost-owner-story-content").text
                        akses_teks = "akses yang hanya bisa dilalui oleh motor/sepeda" if "mobil" not in story_raw.lower() else "akses masuk mobil"
                    except:
                        akses_teks = "akses jalan raya"

                    list_landmark_str = ", ".join(landmarks_info)
                    deskripsi_final = f"Kost ini berlokasi dekat dengan jalan raya dengan {akses_teks}, berlokasi dekat dengan {list_landmark_str}."

                    # Harga
                    harga = "0"
                    harga_int = 0
                    try:
                        sidebar_text = driver.find_element(By.CSS_SELECTOR, ".price-card-container, #priceCard").text
                        for line in sidebar_text.split('\n'):
                            if "Rp" in line:
                                harga = line
                                temp = line.replace("Rp", "").replace(".", "").replace(" ", "").split("/")[0]
                                try: harga_int = int(temp)
                                except: pass
                                break
                    except: pass

                    # Fasilitas (DICT LENGKAP)
                    fasilitas_dict = {
                        "Spesifikasi Tipe Kamar": [], "Fasilitas Kamar": [],
                        "Fasilitas Kamar Mandi": [], "Fasilitas Umum": [],
                        "Fasilitas Parkir": [], "Lainnya": []
                    }

                    cats = driver.find_elements(By.CLASS_NAME, "detail-kost-facility-category__title")
                    for cat in cats:
                        judul_cat = cat.text.strip()
                        items_list = []
                        try:
                            parent = cat.find_element(By.XPATH, "./..") 
                            items = parent.find_elements(By.CLASS_NAME, "detail-kost-facility-item__label")
                            for item in items:
                                txt = item.text.strip().replace("·", "")
                                if txt: items_list.append(txt)
                        except: pass

                        items_str = ", ".join(items_list)
                        if "Spesifikasi" in judul_cat: fasilitas_dict["Spesifikasi Tipe Kamar"].append(items_str)
                        elif "mandi" in judul_cat.lower(): fasilitas_dict["Fasilitas Kamar Mandi"].append(items_str)
                        elif "Fasilitas kamar" in judul_cat: fasilitas_dict["Fasilitas Kamar"].append(items_str)
                        elif "umum" in judul_cat.lower(): fasilitas_dict["Fasilitas Umum"].append(items_str)
                        elif "parkir" in judul_cat.lower(): fasilitas_dict["Fasilitas Parkir"].append(items_str)
                        else: fasilitas_dict["Lainnya"].append(f"{judul_cat}: {items_str}")

                    # --- DETEKSI TIPE KOS ---
                    cek_text = (nama + " " + driver.current_url).lower()
                    tipe_kos = "Campur"
                    if "putri" in cek_text: tipe_kos = "Putri"
                    elif "putra" in cek_text: tipe_kos = "Putra"
                    elif "pasutri" in cek_text: tipe_kos = "Pasutri"

                    # --- DATA CLEANING ---
                    lokasi_clean = clean_lokasi_name(lokasi)

                    all_data.append({
                        "Nama Kost": nama,
                        "Tipe": tipe_kos,
                        "Harga": harga.replace("\n", " "),
                        "Harga_Int": harga_int, 
                        "Lokasi": lokasi,       
                        "Lokasi Clean": lokasi_clean,
                        "Deskripsi": deskripsi_final,
                        "Spesifikasi Kamar": ", ".join(fasilitas_dict["Spesifikasi Tipe Kamar"]),
                        "Fasilitas Kamar": ", ".join(fasilitas_dict["Fasilitas Kamar"]),
                        "Fasilitas Kamar Mandi": ", ".join(fasilitas_dict["Fasilitas Kamar Mandi"]),
                        "Fasilitas Umum": ", ".join(fasilitas_dict["Fasilitas Umum"]),
                        "Fasilitas Parkir": ", ".join(fasilitas_dict["Fasilitas Parkir"]),
                        "Fasilitas Lain": ", ".join(fasilitas_dict["Lainnya"]),
                        "Link": driver.current_url
                    })

                except Exception as e:
                    print(f"Error ambil data: {e}")

                driver.close()
                driver.switch_to.window(main_window)
                time.sleep(1)

            except Exception as e:
                if len(driver.window_handles) > 1:
                    driver.close()
                    driver.switch_to.window(main_window)
                continue
    
    except Exception as e:
        st.error(f"Error Utama: {e}")

    driver.quit()
    progress_bar.progress(100)
    status_text.success("✅ Scraping Selesai!")
    
    return pd.DataFrame(all_data)

# --- 5. TAMPILAN WEBSITE (DASHBOARD) ---

st.title("🏆 GIS Indekos & Smart Recommendation")
st.markdown("Aplikasi Tugas Besar: Scraping, Peta Akurat, dan Rekomendasi Cerdas.")

with st.sidebar:
    st.header("⚙️ Kontrol Aplikasi")
    
    # --- [FITUR 1: PILIHAN UPLOAD VS SCRAPING] ---
    pilihan_sumber = st.radio("Pilih Sumber Data:", ["📂 Upload File CSV", "🚀 Live Scraping"])
    st.markdown("---")
    
    df_result = pd.DataFrame() # Wadah data sementara

    # LOGIKA UPLOAD
    if pilihan_sumber == "📂 Upload File CSV":
        st.info("Mode Demo: Gunakan data CSV yang sudah ada.")
        uploaded_file = st.file_uploader("Upload Data CSV", type=['csv'])
        
        if uploaded_file is not None:
            if st.button("Proses Data"):
                try:
                    df_temp = pd.read_csv(uploaded_file)
                    
                    # VALIDASI FORMAT
                    kolom_wajib = ["Nama Kost", "Harga", "Lokasi"]
                    missing = [col for col in kolom_wajib if col not in df_temp.columns]
                    
                    if missing:
                        st.error(f"❌ Format Salah! Kolom hilang: {', '.join(missing)}")
                    else:
                        df_result = df_temp
                        st.success("✅ Format Valid! Memproses...")
                except Exception as e:
                    st.error(f"Gagal membaca file: {e}")

   # --- LOGIKA SCRAPING ---
    else:
        st.warning("Mode Demo: Pengambilan Data Website (Web Scraping).")
        daerah_input = st.text_input("Target Daerah:", "Bandung Kota")
        
        # Ganti slider sebelumnya dengan ini:
        jumlah_data = st.number_input(
            "Jumlah Data yang Ingin Diambil:", 
            min_value=1, 
            max_value=2000, 
            value=5,
            step=1,
            help="Ketik langsung angka (1-2000) atau klik tombol + / -"
        )
        
        if st.button("🚀 Mulai Ambil Data"):
            df_result = run_scraper_final_fix(daerah_input, jumlah_data)

# --- 6. PROSES DATA TERPUSAT ---
if not df_result.empty:
    with st.spinner('Sedang membersihkan dan memetakan data...'):
        df = df_result.copy() # [.copy() Fix Warning]
        
        # 1. Bersihkan Lokasi
        if 'Lokasi Clean' not in df.columns:
            if 'Lokasi' in df.columns:
                df['Lokasi Clean'] = df['Lokasi'].apply(clean_lokasi_name)
            else:
                df['Lokasi Clean'] = "-"
        
        # 2. Bersihkan Harga
        if 'Harga_Int' not in df.columns:
            def clean_price(price_str):
                try:
                    return int(str(price_str).replace("Rp", "").replace(".", "").replace(" ", "").split("/")[0])
                except:
                    return 0
            df['Harga_Int'] = df['Harga'].apply(clean_price)

        # 3. Deteksi Tipe Kos (Untuk file upload lama)
        if 'Tipe' not in df.columns:
            df['Tipe'] = df.apply(extract_tipe_kos_manual, axis=1)

        # 4. Geocoding
        if 'lat' not in df.columns:
            city = daerah_input if 'daerah_input' in locals() else "Bandung"
            df = add_accurate_coordinates(df, city)
            
        st.session_state['data_kos'] = df
        st.success(f"Berhasil memuat {len(df)} data!")

# --- TABS FITUR ---
if 'data_kos' in st.session_state:
    df = st.session_state['data_kos'].copy() # [.copy() Fix Warning]
    
    # --- [FITUR 2: FILTER TIPE KOS] ---
    st.markdown("### 🔍 Filter Dashboard")
    df['Tipe'] = df['Tipe'].fillna('Campur')
    
    pilihan_tipe = st.multiselect(
        "Pilih Tipe Kos:", 
        options=df['Tipe'].unique(),
        default=df['Tipe'].unique()
    )
    
    # Filter Dataframe Utama
    df_view = df[df['Tipe'].isin(pilihan_tipe)].copy() # [.copy() Fix Warning]
    st.markdown(f"**Menampilkan: {len(df_view)} Data**")

    tab1, tab2, tab3, tab4 = st.tabs(["📋 Data Raw vs Clean", "🗺️ Peta GIS Akurat", "📊 Grafik Insight", "🤖 Smart Recommendation & Distance"])
    
    # TAB 1: DATA CLEANING PREVIEW
    with tab1:
        st.header("Perbandingan Data")
        # Menampilkan kolom Tipe juga
        # --- [MULAI SISIPAN] FITUR HAPUS DUPLICATE ---
        col_btn1, col_btn2 = st.columns([1, 2])
        with col_btn1:
            if st.button("🗑️ Hapus Data Duplicate (Nama & Lokasi)"):
                df_lama = st.session_state['data_kos']
                jumlah_awal = len(df_lama)
                
                # Hapus jika Nama Kost DAN Lokasi sama persis
                df_bersih = df_lama.drop_duplicates(subset=['Nama Kost', 'Lokasi'], keep='first')
                
                # Update Session State
                st.session_state['data_kos'] = df_bersih
                
                # Hitung selisih
                jumlah_hapus = jumlah_awal - len(df_bersih)
                
                if jumlah_hapus > 0:
                    st.success(f"✅ Dihapus: {jumlah_hapus} data kembar!")
                    st.rerun() # Wajib Rerun agar tabel terupdate otomatis
                else:
                    st.info("👌 Data sudah bersih.")
        # --- [AKHIR SISIPAN] ---

        st.dataframe(df_view[['Nama Kost', 'Tipe', 'Lokasi', 'Lokasi Clean', 'Harga', 'Deskripsi']])
        
        csv = df_view.to_csv(index=False).encode('utf-8')
        st.download_button("⬇️ Download CSV Lengkap", csv, "DATA_MAMIKOS_FINAL.csv", "text/csv")

    # TAB 2: PETA GIS (COORD AKURAT)
    with tab2:
        df_filtered = df[df['Tipe'].isin(pilihan_tipe)]

        st.header(f"📍 Peta Sebaran Kos ({', '.join(pilihan_tipe) if pilihan_tipe else 'Tidak Ada Tipe Dipilih'})")
        
        if not df_filtered.empty:
            avg_lat = df_filtered['lat'].mean()
            avg_lon = df_filtered['lon'].mean()

            m = folium.Map(location=[avg_lat, avg_lon], zoom_start=13)

            for i, row in df_filtered.iterrows():
                tipe_kos = str(row['Tipe']).lower()
                if 'putra' in tipe_kos:
                    warna_marker = 'blue'
                elif 'putri' in tipe_kos:
                    warna_marker = 'red'
                else:
                    warna_marker = 'purple'

                info_kost = (
                    f"Nama: {row['Nama Kost']}\n"
                    f"Harga: {row['Harga']}\n"
                    f"Tipe: {row['Tipe']}\n"
                    f"Area: {row['Lokasi Clean']}\n"
                )
                folium.Marker(
                    location=[row['lat'], row['lon']],
                    popup=folium.Popup(info_kost, min_width=250, maks_width=300),
                    tooltip=f"{row['Tipe']} - {row['Nama Kost']}",
                    icon=folium.Icon(color=warna_marker, icon="home", prefix="fa")
                ).add_to(m)

            map_key = f"map_{'_'.join(pilihan_tipe)}" if pilihan_tipe else "map_empty"
            st_folium(m, width=1100, height=500, key=map_key)
            
            st.info(f"Menampilkan {len(df_filtered)} lokasi.")

        else:
            st.warning("⚠️ Pilih Tipe Kos pada sidebar/filter untuk menampilkan marker.")
            m_empty = folium.Map(location=[-6.9175, 107.6191], zoom_start=12) # Koordinat default Bandung
            st_folium(m_empty, width=1100, height=500, key="map_none")
        
        
        with st.expander("Lihat Koordinat "):
            st.dataframe(df_view[['Nama Kost', 'Lokasi Clean', 'lat', 'lon']])

    # TAB 3: INSIGHT GRAFIK
    with tab3:
        st.header("📈 Analisis Pasar Kos")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("📊 Komposisi Tipe Kos")
            # Pie Chart Tipe
            fig_pie = px.pie(df_view, names='Tipe', title='Persentase Tipe Kos',
                             color='Tipe', hole=0.4,
                             color_discrete_map={'Putra':'#3498db', 'Putri':'#e91e63', 'Campur':'#9b59b6'})
            st.plotly_chart(fig_pie, use_container_width=True)
            
        with col2:
            st.subheader("💰 Rata-rata Harga Kos Per Tipe")
            avg_price = df_view.groupby('Tipe')['Harga_Int'].mean().reset_index()
            fig_bar = px.bar(avg_price, x='Tipe', y='Harga_Int', color='Tipe')
            fig_bar.update_layout(
                xaxis_title="Tipe",
                yaxis_title="Harga (Rp)",
            )
            st.plotly_chart(fig_bar, use_container_width=True)
            
        col3, col4 = st.columns(2)
        with col3:
            st.subheader("📈 Distribusi Rentang Harga")
            fig_hist = px.histogram(df_view, x="Harga_Int", nbins=5, title="Distribusi Harga")
            fig_hist.update_traces(
                marker_line_color='white', 
                marker_line_width=2 # Garis putih dipertebal biar tegas pemisahnya
            )
            
            fig_hist.update_layout(
                xaxis_title="Harga (Rp)",
                yaxis_title="Jumlah",
            )
            
            st.plotly_chart(fig_hist, use_container_width=True)
            
        with col4:
            st.subheader("🛏️ Top 10 Fasilitas")
            all_fas_text = " ".join(df_view['Fasilitas Kamar'].dropna().astype(str).tolist()) + \
                           " " + " ".join(df_view['Fasilitas Umum'].dropna().astype(str).tolist())
            items = [x.strip() for x in all_fas_text.split(',') if x.strip()]
            
            if items:
                counts = Counter(items).most_common(10)
                df_fas = pd.DataFrame(counts, columns=['Fasilitas', 'Jumlah'])
                fig_bar = px.bar(df_fas, x='Fasilitas', y='Jumlah', title="Top 10 Fasilitas")
                fig_bar.update_traces(textposition='outside')
                fig_bar.update_xaxes(tickangle=-45)
                fig_bar.update_layout(
                    showlegend=False, 
                    coloraxis_showscale=False, 
                )
                st.plotly_chart(fig_bar, use_container_width=True)


    # TAB 4: SMART RECOMMENDATION (FILTER DESKRIPSI & FASILITAS)
    with tab4:
        st.header("🤖 Smart Recommendation")
        st.info("Peringkat dihitung otomatis berdasarkan kelengkapan fasilitas. Gunakan filter untuk mencari kampus/landmark tertentu.")
        
        col_rec1, col_rec2 = st.columns([1, 1])
        with col_rec1:
            budget_user = st.number_input("💰 Budget Maksimal (Rp):", min_value=100000, value=1500000, step=50000)
        with col_rec2:
            # Mengganti alamat GPS menjadi filter kata kunci teks agar lebih akurat
            keyword = st.text_input("🔍 Cari Dekat Kampus/Landmark (Contoh: Widyatama):")
            
        # --- LOGIKA REKOMENDASI TERINTEGRASI ---
        df_rec = df_view[df_view['Harga_Int'] <= budget_user].copy()
        
        # 1. Pastikan kolom Skor_Fasilitas ada (mencegah KeyError)
        if 'Skor_Fasilitas' not in df_rec.columns:
            def hitung_skor_manual(row):
                f_kamar = str(row.get('Fasilitas Kamar', '')) 
                f_umum = str(row.get('Fasilitas Umum', ''))
                # Menghitung jumlah fasilitas berdasarkan tanda koma
                return len([x for x in (f_kamar + "," + f_umum).split(",") if x.strip()])
            df_rec['Skor_Fasilitas'] = df_rec.apply(hitung_skor_manual, axis=1)

        # 2. Filter berdasarkan kata kunci di Deskripsi (Pengganti Jarak GPS)
        if keyword:
            # Mencari teks di kolom Deskripsi yang di-scrape otomatis
            df_rec = df_rec[df_rec['Deskripsi'].str.contains(keyword, case=False, na=False)]
            st.success(f"Ditemukan {len(df_rec)} kos di sekitar '{keyword}'")

        # 3. Sortir: Fasilitas Terlengkap & Harga Termurah
        df_rec = df_rec.sort_values(by=['Skor_Fasilitas', 'Harga_Int'], ascending=[False, True])
        
        st.markdown("---")
        
        if not df_rec.empty:
            st.subheader(f"🏆 Top 3 Rekomendasi Terbaik")
            
            top_3 = df_rec.head(3)
            cols = st.columns(3)
            
            for i, (index, row) in enumerate(top_3.iterrows()):
                with cols[i]:
                    # Container dengan border membuat visual "Card" yang rapi
                    with st.container(border=True):
                        
                        # Subheader untuk teks Peringkat tambahan yang berwarna hijau
                        st.markdown(f"### :green[Peringkat #{i+1}]")
                        
                        # 2. Nama Kost (Judul)
                        # Menggunakan height minimal secara visual lewat markdown
                        st.markdown(f"**{row['Nama Kost']}**")
                        
                        # 3. Info Lokasi & Jarak
                        st.caption(f"📍 {row['Lokasi Clean']}")
                        st.write(f"🏷️ {row['Tipe']}")
                        
                        # 4. Harga (Dibuat Bold & Besar)
                        st.subheader(f"{row['Harga']}")
                        
                        # 5. Skor Fasilitas
                        st.metric("Skor Fasilitas", f"{row['Skor_Fasilitas']} Item")
                        
                        # 6. Tombol Akses
                        st.link_button("👉 Lihat Kos", row['Link'], use_container_width=True)

            st.markdown("#### Daftar Lengkap Hasil Filter")
            # Menampilkan kolom yang relevan saja agar rapi
            st.dataframe(df_rec[['Nama Kost', 'Tipe', 'Harga', 'Skor_Fasilitas', 'Deskripsi']])
        else:
            st.warning("Tidak ada kos yang cocok dengan kriteria budget atau lokasi tersebut.")