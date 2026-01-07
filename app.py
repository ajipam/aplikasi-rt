import streamlit as st
import pandas as pd
from datetime import datetime
import hashlib
from fpdf import FPDF
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import uuid

# --- KONFIGURASI ---
SCOPE = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
# PASTIKAN NAMA SHEET DI SINI SAMA PERSIS DENGAN NAMA FILE GOOGLE SHEETS ANDA
SHEET_NAME = "DB_KeuanganRT" 

def connect_db():
    """Koneksi ke Google Sheets"""
    try:
        # Mengambil kunci dari file secrets.toml
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, SCOPE)
        client = gspread.authorize(creds)
        sheet = client.open(SHEET_NAME)
        return sheet
    except Exception as e:
        st.error(f"Gagal koneksi ke Google Sheets: {e}")
        return None

# --- FUNGSI BACA/TULIS DATA ---
def get_data(worksheet_name):
    sheet = connect_db()
    if sheet:
        ws = sheet.worksheet(worksheet_name)
        data = ws.get_all_records()
        return pd.DataFrame(data)
    return pd.DataFrame()

def add_row(worksheet_name, row_data):
    sheet = connect_db()
    if sheet:
        ws = sheet.worksheet(worksheet_name)
        ws.append_row(row_data)

def update_kategori_bulk(df_baru):
    sheet = connect_db()
    if sheet:
        ws = sheet.worksheet("kategori")
        ws.clear()
        # Tulis Header
        ws.append_row(df_baru.columns.values.tolist()) 
        # Tulis Data
        ws.update([df_baru.columns.values.tolist()] + df_baru.values.tolist())

# --- FUNGSI PENDUKUNG ---
def hash_pass(password):
    return hashlib.sha256(password.encode()).hexdigest()

def init_default_data():
    """Buat admin pertama jika tabel users kosong"""
    df_users = get_data("users")
    if df_users.empty:
        pass_admin = hash_pass('admin123')
        add_row("users", ['admin', pass_admin, 'admin', 'Bendahara RT'])

# --- FUNGSI PDF ---
class PDF(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 16)
        self.cell(0, 10, 'Laporan Keuangan RT', 0, 1, 'C')
        self.ln(5)
    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.cell(0, 10, f'Hal {self.page_no()}', 0, 0, 'C')

def create_pdf(dataframe):
    pdf = PDF()
    pdf.add_page()
    pdf.set_font("Arial", size=10)
    # Header Tabel
    headers = ['Tgl', 'Tipe', 'Kategori', 'Nominal', 'Ket']
    w = [25, 25, 40, 35, 60]
    for i, h in enumerate(headers): pdf.cell(w[i], 10, h, 1)
    pdf.ln()
    
    total_masuk, total_keluar = 0, 0
    for _, row in dataframe.iterrows():
        try:
            nom = float(row['nominal'])
        except:
            nom = 0
            
        pdf.cell(w[0], 8, str(row['tanggal']), 1)
        pdf.cell(w[1], 8, str(row['tipe']), 1)
        pdf.cell(w[2], 8, str(row['kategori']), 1)
        pdf.cell(w[3], 8, f"{nom:,.0f}", 1, 0, 'R')
        pdf.cell(w[4], 8, str(row['keterangan'])[:30], 1, 1)
        
        if row['tipe'] == 'Pemasukan': total_masuk += nom
        else: total_keluar += nom
            
    pdf.ln(5)
    pdf.cell(0, 8, f"Sisa Saldo: Rp {total_masuk - total_keluar:,.0f}", 0, 1)
    return pdf.output(dest='S').encode('latin-1')

# --- LOGIC UTAMA ---
def main():
    st.set_page_config(page_title="Keuangan RT (Cloud)", layout="wide")
    
    # Init Session
    if 'logged_in' not in st.session_state:
        st.session_state['logged_in'] = False

    # --- LOGIN SCREEN ---
    if not st.session_state['logged_in']:
        st.title("🔐 Login SI-Keuangan RT (Online)")
        
        # Tombol Darurat untuk Buat Admin Pertama
        with st.expander("Klik ini jika baru pertama kali dipakai (Isi Admin)"):
            if st.button("Generate Default Admin"):
                init_default_data()
                st.success("Admin default dibuat: admin / admin123")
        
        user = st.text_input("Username")
        pwd = st.text_input("Password", type='password')
        
        if st.button("Masuk"):
            df_users = get_data("users")
            if not df_users.empty:
                # Cek User Pandas
                hashed = hash_pass(pwd)
                # Pastikan kolom string
                df_users['username'] = df_users['username'].astype(str)
                df_users['password'] = df_users['password'].astype(str)
                
                match = df_users[(df_users['username'] == user) & (df_users['password'] == hashed)]
                
                if not match.empty:
                    st.session_state['logged_in'] = True
                    st.session_state['username'] = match.iloc[0]['username']
                    st.session_state['role'] = match.iloc[0]['role']
                    st.session_state['nama'] = match.iloc[0]['nama_lengkap']
                    st.rerun()
                else:
                    st.error("Login Gagal")
            else:
                st.warning("Database User Kosong. Klik 'Generate Default Admin' dulu.")
        return

    # --- MENU UTAMA ---
    st.sidebar.title(f"Hi, {st.session_state['nama']}")
    
    menu = ["Dashboard", "Riwayat Transaksi", "Laporan"]
    if st.session_state['role'] == 'admin':
        menu = ["Dashboard", "Input Transaksi", "Kelola Kategori", "Kelola Pengguna"] + menu
        
    choice = st.sidebar.radio("Menu", menu)
    
    if st.sidebar.button("Logout"):
        st.session_state.clear()
        st.rerun()

    # --- 1. DASHBOARD (FIXED ERROR) ---
    if choice == "Dashboard":
        st.header("📊 Dashboard")
        df = get_data("transaksi")
        
        if not df.empty:
            df['tanggal'] = pd.to_datetime(df['tanggal'])
            df['nominal'] = pd.to_numeric(df['nominal'], errors='coerce').fillna(0)
            
            masuk = df[df['tipe'] == 'Pemasukan']['nominal'].sum()
            keluar = df[df['tipe'] == 'Pengeluaran']['nominal'].sum()
            
            c1, c2, c3 = st.columns(3)
            c1.metric("Saldo", f"Rp {masuk-keluar:,.0f}")
            c2.metric("Pemasukan", f"Rp {masuk:,.0f}")
            c3.metric("Pengeluaran", f"Rp {keluar:,.0f}")
            
            st.divider()
            
            # CHART HANDLING
            df['bulan'] = df['tanggal'].dt.strftime('%Y-%m')
            chart_data = df.groupby(['bulan', 'tipe'])['nominal'].sum().unstack().fillna(0)
            
            # Paksa kolom agar warna tidak error
            if 'Pemasukan' not in chart_data.columns: chart_data['Pemasukan'] = 0
            if 'Pengeluaran' not in chart_data.columns: chart_data['Pengeluaran'] = 0
            
            chart_data = chart_data[['Pemasukan', 'Pengeluaran']]
            st.bar_chart(chart_data, color=["#4CAF50", "#FF4B4B"])
        else:
            st.info("Belum ada data.")

    # --- 2. INPUT TRANSAKSI ---
    elif choice == "Input Transaksi":
        st.header("📝 Input Baru")
        jenis = st.radio("Jenis", ["Pemasukan", "Pengeluaran"], horizontal=True)
        
        df_kat = get_data("kategori")
        list_kat = ["Umum"]
        if not df_kat.empty:
             # Filter yang sesuai jenis
             list_kat = df_kat[df_kat['jenis'] == jenis]['nama'].tolist()
             if not list_kat: list_kat = ["Lainnya"]
        
        with st.form("input"):
            tgl = st.date_input("Tanggal", datetime.now())
            nom = st.number_input("Nominal", min_value=0, step=1000)
            kat = st.selectbox("Kategori", list_kat)
            ket = st.text_area("Keterangan")
            
            if st.form_submit_button("Simpan"):
                uid = str(uuid.uuid4())[:8]
                add_row("transaksi", [uid, str(tgl), jenis, kat, nom, ket, st.session_state['username'], "-"])
                st.success("Tersimpan!")

    # --- 3. KELOLA KATEGORI ---
    elif choice == "Kelola Kategori":
        st.header("🏷️ Edit Kategori")
        df = get_data("kategori")
        edited = st.data_editor(df, num_rows="dynamic", hide_index=True)
        
        if st.button("Simpan ke Cloud"):
            update_kategori_bulk(edited)
            st.success("Berhasil update kategori!")
            st.rerun()

    # --- 4. KELOLA PENGGUNA ---
    elif choice == "Kelola Pengguna":
        st.header("👥 User Management")
        with st.form("add_u"):
            u = st.text_input("User Baru")
            p = st.text_input("Password", type="password")
            n = st.text_input("Nama")
            r = st.selectbox("Role", ["warga", "admin"])
            if st.form_submit_button("Tambah"):
                add_row("users", [u, hash_pass(p), r, n])
                st.success("User dibuat.")
        
        st.dataframe(get_data("users"))

    # --- 5. RIWAYAT & 6. LAPORAN ---
    elif choice == "Riwayat Transaksi":
        st.header("🗂️ Riwayat")
        st.dataframe(get_data("transaksi"))

    elif choice == "Laporan":
        st.header("Download PDF")
        df = get_data("transaksi")
        if not df.empty:
            pdf = create_pdf(df)
            st.download_button("Download PDF", data=pdf, file_name="laporan.pdf")

if __name__ == '__main__':
    main()
