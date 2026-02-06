import time
import pandas as pd
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

def scrape_mamikos_final_fix(target_count=1100):
    # --- SETUP ---
    options = Options()
    options.add_argument("--start-maximized")
    options.add_argument("--disable-blink-features=AutomationControlled") 
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")
    
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    wait = WebDriverWait(driver, 20)
    
    base_url = "https://mamikos.com/kost/kost-bandung-kota-murah"
    
    print("\n" + "="*70)
    print("🏠 MAMIKOS SCRAPER - FINAL FIX (NAMA & LOKASI)")
    print("   Target: Memperbaiki Nama (-) dan Lokasi Kosong")
    print("="*70)
    
    all_data = []
    driver.get(base_url)
    main_window = driver.current_window_handle
    
    print("\n⚠️  Browser terbuka.")
    input("✅ Login/Captcha dulu. Tekan ENTER jika daftar kos sudah siap scan...")
    
    for i in range(target_count):
        print(f"\n🔄 [Antrean {i+1}] Memproses...")
        try:
            if driver.current_window_handle != main_window:
                driver.switch_to.window(main_window)

            # ======================================================
            # 1. CARI KARTU & PINDAH HALAMAN (PAGINATION MODE)
            # ======================================================
            
            # Ambil daftar kartu di halaman sekarang
            cards = driver.find_elements(By.CSS_SELECTOR, ".kost-rc, [data-testid='roomCard']")
            
            # LOGIKA PINDAH HALAMAN
            # Jika 'i' > 0 dan habis dibagi 20 (contoh: 20, 40, 60...), waktunya klik Next
            if i > 0 and i % 20 == 0:
                print(f"   ➡️ Pindah ke Halaman Berikutnya (Data ke-{i+1})...")
                try:
                    # CARI TOMBOL NEXT BERDASARKAN GAMBAR HTML ANDA
                    # Strategi: Cari <li> TERAKHIR di dalam <ul class="pagination">
                    # XPath ini artinya: "Cari ul pagination, ambil li terakhir, lalu ambil tag a di dalamnya"
                    next_button = driver.find_element(By.XPATH, "//ul[contains(@class, 'pagination')]/li[last()]/a")
                    
                    # Klik tombol Next
                    driver.execute_script("arguments[0].click();", next_button)
                    
                    # Tunggu Loading Halaman Baru (Wajib agak lama)
                    time.sleep(5)
                    
                    # Refresh daftar kartu setelah halaman berubah
                    cards = driver.find_elements(By.CSS_SELECTOR, ".kost-rc, [data-testid='roomCard']")
                    
                except Exception as e:
                    print(f"   ⚠️ Gagal Pindah Halaman/Mentok: {e}")
            
            # ======================================================
            # PEMILIHAN KARTU (Index Reset)
            # ======================================================
            
            # Karena di halaman 2 urutan kartu kembali ke 0, 1, 2... 
            # Sedangkan loop 'i' terus naik (20, 21, 22...).
            # Kita pakai 'Sisa Bagi' (%) agar i=20 menjadi index=0, i=21 menjadi index=1.
            local_index = i % 20
            
            # Safety Check: Jika halaman belum load sempurna atau data habis
            if local_index >= len(cards):
                # Coba refresh sekali lagi
                time.sleep(2)
                cards = driver.find_elements(By.CSS_SELECTOR, ".kost-rc, [data-testid='roomCard']")
                if local_index >= len(cards):
                    print("   ⚠️ Data di halaman ini habis/error index. Skip.")
                    continue

            target_card = cards[local_index]
            
            # Scroll sedikit ke elemen biar terlihat
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", target_card)
            time.sleep(1)

            # 2. KLIK & BUKA TAB BARU
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
                print("   ⚠️ Gagal buka tab. Skip.")
                continue

            # 3. SCROLL HALAMAN DETAIL SECARA PENUH
            time.sleep(3) 
            total_height = driver.execute_script("return document.body.scrollHeight")
            for scroll_pos in range(0, total_height, 700):
                driver.execute_script(f"window.scrollTo(0, {scroll_pos});")
                time.sleep(0.5)
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(1)

            # 4. SCRAPE DATA (UPDATED SELECTORS)
            try:
                # A. NAMA KOST (PERBAIKAN)
                # Lihat image_b038ec.png -> class="detail-title__room-name"
                try: 
                    nama = driver.find_element(By.CLASS_NAME, "detail-title__room-name").text
                except: 
                    # Backup plan
                    try: nama = driver.find_element(By.TAG_NAME, "h1").text
                    except: nama = driver.title

                
                   # ======================================================
                # B. LOKASI (SUPER FIX - 4 LAPIS BACKUP)
                # ======================================================
                lokasi = "-" # Default value

                try:
                    # CARA 1: Ambil textContent via Javascript (Paling Ampuh untuk teks bandel)
                    # Ini memaksa browser memberikan teks meskipun tersembunyi/loading
                    lokasi_elem = driver.find_element(By.CSS_SELECTOR, ".detail-kost-overview__area-text")
                    lokasi = driver.execute_script("return arguments[0].textContent;", lokasi_elem).strip()
                except:
                    lokasi = "-"

                # Debug Print untuk memastikan script jalan
                print(f"      📍 Lokasi dpt: {lokasi}") 
                # ======================================================

                # C. HARGA
                harga = "0"
                try:
                    sidebar_text = driver.find_element(By.CSS_SELECTOR, ".price-card-container, #priceCard").text
                    for line in sidebar_text.split('\n'):
                        if "Rp" in line and len(line) < 20:
                            harga = line
                            break
                except: pass

                # D. FASILITAS (Sama seperti sebelumnya)
                fasilitas_dict = {
                    "Spesifikasi Tipe Kamar": [], "Fasilitas Kamar": [],
                    "Fasilitas Kamar Mandi": [], "Fasilitas Umum": [],
                    "Fasilitas Parkir": [], "Lainnya": []
                }

                categories = driver.find_elements(By.CLASS_NAME, "detail-kost-facility-category__title")
                for cat in categories:
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
                    elif "Fasilitas kamar mandi" in judul_cat: fasilitas_dict["Fasilitas Kamar Mandi"].append(items_str)
                    elif "Fasilitas kamar" in judul_cat: fasilitas_dict["Fasilitas Kamar"].append(items_str)
                    elif "umum" in judul_cat.lower(): fasilitas_dict["Fasilitas Umum"].append(items_str)
                    elif "parkir" in judul_cat.lower(): fasilitas_dict["Fasilitas Parkir"].append(items_str)
                    else: fasilitas_dict["Lainnya"].append(f"{judul_cat}: {items_str}")

                print(f"   ✅ OK: {nama[:20]}... | {lokasi}")

                data_row = {
                    "Nama Kost": nama,
                    "Harga": harga.replace("\n", " "),
                    "Lokasi": lokasi,
                    "Link": driver.current_url,
                    "Spesifikasi Kamar": ", ".join(fasilitas_dict["Spesifikasi Tipe Kamar"]),
                    "Fasilitas Kamar": ", ".join(fasilitas_dict["Fasilitas Kamar"]),
                    "Fasilitas Kamar Mandi": ", ".join(fasilitas_dict["Fasilitas Kamar Mandi"]),
                    "Fasilitas Umum": ", ".join(fasilitas_dict["Fasilitas Umum"]),
                    "Fasilitas Parkir": ", ".join(fasilitas_dict["Fasilitas Parkir"]),
                    "Fasilitas Lain": ", ".join(fasilitas_dict["Lainnya"])
                }
                all_data.append(data_row)

            except Exception as e:
                print(f"   ⚠️ Error ambil data: {e}")

            driver.close()
            driver.switch_to.window(main_window)
            time.sleep(1)

        except Exception as e:
            print(f"   ❌ Error Fatal: {e}")
            if len(driver.window_handles) > 1:
                driver.close()
                driver.switch_to.window(main_window)
            continue

    driver.quit()
    
    if all_data:
        df = pd.DataFrame(all_data)
        cols = ["Nama Kost", "Harga", "Lokasi", "Spesifikasi Kamar", "Fasilitas Kamar", "Fasilitas Kamar Mandi", "Fasilitas Umum", "Fasilitas Parkir", "Fasilitas Lain", "Link"]
        for c in cols:
            if c not in df.columns: df[c] = "-"
        df = df[cols]
        df.to_csv("DATA_MAMIKOS_COMPLETE_FIX.csv", index=False)
        print("\n✅ DATA TERSIMPAN: DATA_MAMIKOS_COMPLETE_FIX.csv")

if __name__ == "__main__":
    scrape_mamikos_final_fix(target_count=1100)