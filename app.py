import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime
import os
import hashlib
from fpdf import FPDF
import base64

# --- KONFIGURASI & DATABASE ---
DB_FILE = 'keuangan_rt.db'
BUKTI_DIR = 'bukti_transaksi'

if not os.path.exists(BUKTI_DIR):
    os.makedirs(BUKTI_DIR)

def init_db():
    """Inisialisasi Database dan Tabel"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    # 1. Tabel User
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (username TEXT PRIMARY KEY, password TEXT, role TEXT, nama_lengkap TEXT)''')
    
    # 2. Tabel Kategori
    c.execute('''CREATE TABLE IF NOT EXISTS kategori
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  nama TEXT,
                  jenis TEXT)''') 
    
    # 3. Tabel Transaksi
    c.execute('''CREATE TABLE IF NOT EXISTS transaksi
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  tanggal DATE,
                  tipe TEXT,
                  kategori TEXT,
                  nominal REAL,
                  keterangan TEXT,
                  user_input TEXT,
                  file_bukti TEXT)''')
    
    # Seed Data Admin Awal
    c.execute("SELECT * FROM users WHERE username = 'admin'")
    if not c.fetchone():
        pass_admin = hashlib.sha256('admin123'.encode()).hexdigest()
        c.execute("INSERT INTO users VALUES (?, ?, ?, ?)", ('admin', pass_admin, 'admin', 'Bendahara RT'))
        
    # Seed Kategori Default
    c.execute("SELECT count(*) FROM kategori")
    if c.fetchone()[0] == 0:
        defaults = [
            ('Iuran Warga', 'Pemasukan'), ('Donasi', 'Pemasukan'), 
            ('Kebersihan', 'Pengeluaran'), ('Perbaikan', 'Pengeluaran')
        ]
        c.executemany("INSERT INTO kategori (nama, jenis) VALUES (?, ?)", defaults)
    
    conn.commit()
    conn.close()

def run_query(query, params=(), return_data=False):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    try:
        c.execute(query, params)
        if return_data:
            data = c.fetchall()
            conn.close()
            return data
        conn.commit()
    except Exception as e:
        st.error(f"Database Error: {e}")
    finally:
        conn.close()

def hash_pass(password):
    return hashlib.sha256(password.encode()).hexdigest()

# --- FUNGSI GENERATE PDF ---
class PDF(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 16)
        self.cell(0, 10, 'Laporan Keuangan RT', 0, 1, 'C')
        self.set_font('Arial', 'I', 10)
        self.cell(0, 10, f'Dicetak pada: {datetime.now().strftime("%d-%m-%Y %H:%M")}', 0, 1, 'C')
        self.ln(5)

    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.cell(0, 10, f'Halaman {self.page_no()}', 0, 0, 'C')

def create_pdf(dataframe):
    pdf = PDF()
    pdf.add_page()
    pdf.set_font("Arial", size=10)
    
    # Header Tabel
    pdf.set_fill_color(200, 220, 255)
    pdf.cell(30, 10, 'Tanggal', 1, 0, 'C', 1)
    pdf.cell(25, 10, 'Tipe', 1, 0, 'C', 1)
    pdf.cell(40, 10, 'Kategori', 1, 0, 'C', 1)
    pdf.cell(35, 10, 'Nominal', 1, 0, 'C', 1)
    pdf.cell(60, 10, 'Keterangan', 1, 1, 'C', 1)
    
    # Isi Tabel
    pdf.set_font("Arial", size=9)
    total_masuk = 0
    total_keluar = 0
    
    for index, row in dataframe.iterrows():
        tgl = row['tanggal'].strftime('%d-%m-%Y')
        nominal_fmt = f"{row['nominal']:,.0f}"
        
        pdf.cell(30, 8, tgl, 1)
        pdf.cell(25, 8, row['tipe'], 1)
        pdf.cell(40, 8, row['kategori'], 1)
        pdf.cell(35, 8, nominal_fmt, 1, 0, 'R')
        pdf.cell(60, 8, str(row['keterangan'])[:30], 1, 1) # Potong teks jika kepanjangan
        
        if row['tipe'] == 'Pemasukan':
            total_masuk += row['nominal']
        else:
            total_keluar += row['nominal']
            
    pdf.ln(5)
    pdf.set_font("Arial", 'B', 10)
    pdf.cell(0, 8, f"Total Pemasukan: Rp {total_masuk:,.0f}", 0, 1)
    pdf.cell(0, 8, f"Total Pengeluaran: Rp {total_keluar:,.0f}", 0, 1)
    pdf.cell(0, 8, f"Saldo Akhir: Rp {total_masuk - total_keluar:,.0f}", 0, 1)
    
    return pdf.output(dest='S').encode('latin-1')

# --- FITUR LOGIN ---
def login():
    st.title("🔐 Login SI-Keuangan RT")
    username = st.text_input("Username")
    password = st.text_input("Password", type='password')
    if st.button("Masuk"):
        hashed_pw = hash_pass(password)
        user = run_query("SELECT username, role, nama_lengkap FROM users WHERE username=? AND password=?", 
                         (username, hashed_pw), return_data=True)
        if user:
            st.session_state['logged_in'] = True
            st.session_state['username'] = user[0][0]
            st.session_state['role'] = user[0][1]
            st.session_state['nama'] = user[0][2]
            st.rerun()
        else:
            st.error("Username atau Password salah!")

def logout():
    st.session_state.clear()
    st.rerun()

# --- HALAMAN UTAMA ---
def main():
    st.set_page_config(page_title="Keuangan RT", layout="wide")
    init_db()
    
    if 'logged_in' not in st.session_state or not st.session_state['logged_in']:
        login()
        return

    # --- SIDEBAR NAVIGASI ---
    st.sidebar.title(f"Halo, {st.session_state['nama']}")
    st.sidebar.caption(f"Role: {st.session_state['role'].upper()}")
    
    if st.session_state['role'] == 'admin':
        menu_options = ["Dashboard", "Input Transaksi", "Kelola Kategori", "Kelola Pengguna", "Riwayat Transaksi", "Laporan"]
    else:
        menu_options = ["Dashboard", "Riwayat Transaksi", "Laporan"]
        
    choice = st.sidebar.radio("Menu", menu_options)
    
    if st.sidebar.button("Logout"):
        logout()

    # --- 1. DASHBOARD ---
    if choice == "Dashboard":
        st.header("📊 Dashboard Real-time")
        df = get_data("transaksi")
        
        if not df.empty:
            # Pastikan format data benar
            df['tanggal'] = pd.to_datetime(df['tanggal'])
            # Paksa nominal jadi angka (kadang dari GSheets terbaca string)
            df['nominal'] = pd.to_numeric(df['nominal'], errors='coerce').fillna(0)
            
            # Hitung Saldo
            masuk = df[df['tipe'] == 'Pemasukan']['nominal'].sum()
            keluar = df[df['tipe'] == 'Pengeluaran']['nominal'].sum()
            
            c1, c2, c3 = st.columns(3)
            c1.metric("Saldo", f"Rp {masuk-keluar:,.0f}")
            c2.metric("Pemasukan", f"Rp {masuk:,.0f}")
            c3.metric("Pengeluaran", f"Rp {keluar:,.0f}")
            
            st.subheader("Grafik Tahunan")
            df['bulan'] = df['tanggal'].dt.strftime('%Y-%m')
            
            # Grouping data
            chart = df.groupby(['bulan', 'tipe'])['nominal'].sum().unstack().fillna(0)
            
            # --- PERBAIKAN ERROR DI SINI ---
            # Kita pastikan kolom 'Pemasukan' dan 'Pengeluaran' selalu ada
            # agar warnanya tidak error
            cols_expected = ['Pemasukan', 'Pengeluaran']
            for col in cols_expected:
                if col not in chart.columns:
                    chart[col] = 0
            
            # Urutkan kolom agar Pemasukan selalu kiri (Hijau), Pengeluaran kanan (Merah)
            chart = chart[['Pemasukan', 'Pengeluaran']]
            
            # Tampilkan dengan warna manual: Hijau (#4CAF50) & Merah (#FF4B4B)
            st.bar_chart(chart, color=["#4CAF50", "#FF4B4B"])
            
        else:
            st.info("Belum ada data transaksi.")

    # --- 2. INPUT TRANSAKSI (Admin) ---
    elif choice == "Input Transaksi":
        st.header("📝 Input Data Keuangan")
        jenis = st.radio("Jenis", ["Pemasukan", "Pengeluaran"], horizontal=True)
        
        raw_kat = run_query("SELECT nama FROM kategori WHERE jenis = ?", (jenis,), return_data=True)
        list_kat = [r[0] for r in raw_kat] if raw_kat else ["Lainnya"]

        with st.form("input_trx", clear_on_submit=True):
            c1, c2 = st.columns(2)
            tgl = c1.date_input("Tanggal", datetime.now())
            nom = c2.number_input("Nominal (Rp)", min_value=0, step=1000)
            kat = st.selectbox("Kategori", list_kat)
            ket = st.text_area("Keterangan")
            file = st.file_uploader("Upload Bukti", type=['jpg','png','pdf'])
            
            if st.form_submit_button("Simpan"):
                path = ""
                if file:
                    path = os.path.join(BUKTI_DIR, file.name)
                    with open(path, "wb") as f: f.write(file.getbuffer())
                
                run_query("INSERT INTO transaksi (tanggal, tipe, kategori, nominal, keterangan, user_input, file_bukti) VALUES (?,?,?,?,?,?,?)",
                          (tgl, jenis, kat, nom, ket, st.session_state['username'], path))
                st.success("Data Tersimpan!")

    # --- 3. KELOLA KATEGORI (Admin) ---
    elif choice == "Kelola Kategori":
        st.header("🏷️ Kelola Kategori")
        conn = sqlite3.connect(DB_FILE)
        df_kat = pd.read_sql_query("SELECT id, jenis, nama FROM kategori", conn)
        edited_df = st.data_editor(df_kat, num_rows="dynamic", key="kat_editor", hide_index=True)
        
        if st.button("Simpan Perubahan Kategori"):
            c = conn.cursor()
            c.execute("DELETE FROM kategori")
            for i, row in edited_df.iterrows():
                c.execute("INSERT INTO kategori (jenis, nama) VALUES (?,?)", (row['jenis'], row['nama']))
            conn.commit()
            st.success("Kategori diperbarui!")
            st.rerun()
        conn.close()

    # --- 4. KELOLA PENGGUNA (BARU: User Management) ---
    elif choice == "Kelola Pengguna":
        st.header("👥 Kelola Pengguna Aplikasi")
        
        # Form Tambah User
        with st.expander("➕ Tambah User Baru", expanded=False):
            with st.form("add_user_form", clear_on_submit=True):
                new_user = st.text_input("Username (Tanpa Spasi)")
                new_pass = st.text_input("Password", type="password")
                new_name = st.text_input("Nama Lengkap")
                new_role = st.selectbox("Role", ["warga", "admin"])
                
                if st.form_submit_button("Buat User"):
                    if new_user and new_pass:
                        existing = run_query("SELECT * FROM users WHERE username=?", (new_user,), return_data=True)
                        if existing:
                            st.error("Username sudah dipakai!")
                        else:
                            hashed = hash_pass(new_pass)
                            run_query("INSERT INTO users VALUES (?,?,?,?)", (new_user, hashed, new_role, new_name))
                            st.success(f"User {new_name} berhasil dibuat!")
                    else:
                        st.warning("Mohon isi semua field.")

        # Tabel List User
        st.subheader("Daftar Pengguna")
        users = pd.read_sql_query("SELECT username, role, nama_lengkap FROM users", sqlite3.connect(DB_FILE))
        st.dataframe(users, use_container_width=True)
        
        # Hapus User
        st.write("---")
        col_del1, col_del2 = st.columns([3, 1])
        with col_del1:
            user_to_del = st.selectbox("Pilih User untuk Dihapus", users['username'].unique())
        with col_del2:
            st.write("") # Spacer
            st.write("") 
            if st.button("Hapus User"):
                if user_to_del == 'admin' and st.session_state['username'] == 'admin':
                     st.error("Tidak bisa menghapus Admin Utama!")
                elif user_to_del == st.session_state['username']:
                     st.error("Anda tidak bisa menghapus diri sendiri saat login!")
                else:
                    run_query("DELETE FROM users WHERE username=?", (user_to_del,))
                    st.success(f"User {user_to_del} dihapus.")
                    st.rerun()

    # --- 5. RIWAYAT TRANSAKSI ---
    elif choice == "Riwayat Transaksi":
        st.header("🗂️ Riwayat Transaksi")
        df = pd.read_sql_query("SELECT * FROM transaksi ORDER BY tanggal DESC", sqlite3.connect(DB_FILE))
        
        # Simple display
        st.dataframe(df.style.format({"nominal": "Rp {:,.0f}"}), use_container_width=True)
        
        # Fitur Hapus (Admin)
        if st.session_state['role'] == 'admin':
            with st.expander("Hapus Transaksi (Admin Only)"):
                id_del = st.number_input("ID Transaksi", min_value=0)
                if st.button("Hapus Data"):
                    run_query("DELETE FROM transaksi WHERE id=?", (id_del,))
                    st.success("Terhapus.")
                    st.rerun()

    # --- 6. LAPORAN (Updated: PDF Export) ---
    elif choice == "Laporan":
        st.header("📥 Download Laporan")
        
        # Filter Laporan
        col_L1, col_L2 = st.columns(2)
        start_date = col_L1.date_input("Dari Tanggal", datetime(datetime.now().year, 1, 1))
        end_date = col_L2.date_input("Sampai Tanggal", datetime.now())
        
        # Query Data
        query = f"SELECT * FROM transaksi WHERE tanggal BETWEEN '{start_date}' AND '{end_date}' ORDER BY tanggal ASC"
        df = pd.read_sql_query(query, sqlite3.connect(DB_FILE))
        df['tanggal'] = pd.to_datetime(df['tanggal'])
        
        st.dataframe(df.style.format({"nominal": "Rp {:,.0f}"}), use_container_width=True)
        
        col_dl1, col_dl2 = st.columns(2)
        
        # 1. Download CSV
        with col_dl1:
            csv = df.to_csv(index=False).encode('utf-8')
            st.download_button("📄 Download Excel/CSV", data=csv, file_name='laporan.csv', mime='text/csv')
            
        # 2. Download PDF (Fitur Baru)
        with col_dl2:
            if not df.empty:
                pdf_bytes = create_pdf(df)
                st.download_button(
                    label="📕 Download PDF",
                    data=pdf_bytes,
                    file_name=f"Laporan_Keuangan_{start_date}_{end_date}.pdf",
                    mime='application/pdf'
                )
            else:
                st.write("Tidak ada data untuk dicetak.")

if __name__ == '__main__':

    main()
