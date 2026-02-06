import pandas as pd

# 1. Membaca file asli
df = pd.read_csv('DATA_MAMIKOS_FINAL (3).csv')

# 2. Menghitung jumlah data sebelum dibersihkan
jumlah_awal = len(df)

# 3. Menghapus duplikat (Berdasarkan Nama dan Link)
# keep='first' artinya menyimpan data pertama yang muncul dan menghapus sisanya
df_clean = df.drop_duplicates(subset=['Nama Kost', 'Link'], keep='first')

# 4. Menghitung hasil pembersihan
jumlah_akhir = len(df_clean)
jumlah_dihapus = jumlah_awal - jumlah_akhir

# 5. Menyimpan ke file baru
df_clean.to_csv('DATA_MAMIKOS_CLEAN.csv', index=False)

print(f"Selesai!")
print(f"Jumlah data awal: {jumlah_awal}")
print(f"Data duplikat dihapus: {jumlah_dihapus}")
print(f"Jumlah data unik sekarang: {jumlah_akhir}")
print(f"File baru disimpan sebagai: DATA_MAMIKOS_CLEAN.csv")