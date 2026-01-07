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
SHEET_NAME = "DB_KeuanganRT" # Pastikan nama file Google Sheets SAMA PERSIS

def connect_db():
    """Koneksi ke Google Sheets"""
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, SCOPE)
        client = gspread.authorize(creds)
        sheet = client.open(SHEET_NAME)
        return sheet
    except Exception as e:
        st.error(f"Gagal koneksi: {e}")
        return None

# --- FUNGSI CRUD (CREATE, READ, UPDATE, DELETE) ---
def get_data(worksheet_name):
    sheet = connect_db()
    if sheet:
        ws = sheet.worksheet(worksheet_name)
        data = ws.get_all_records()
        df = pd.DataFrame(data)
        # Pastikan kolom ID selalu dianggap string agar tidak error saat pencarian
        if 'id' in df.columns:
            df['id'] = df['id'].astype(str)
        return df
    return pd.DataFrame()

def save_all_data(worksheet_name, df):
    """Fungsi pembantu untuk menimpa seluruh data di sheet (untuk Edit/Delete)"""
    sheet = connect_db()
    if sheet:
        ws = sheet.worksheet(worksheet_name)
        ws.clear() # Hapus semua data lama
        # Tulis ulang header dan data baru
        # Catatan: gspread versi baru butuh [values] dan range
        ws.update(range_name='A1', values=[df.columns.values.tolist()] + df.values.tolist())

def add_row(worksheet_name, row_data):
    sheet = connect_db()
    if sheet:
        ws = sheet.worksheet(worksheet_name)
        ws.append_row(row_data)

def delete_transaction(id_transaksi):
    df = get_data("transaksi")
    # Filter: Ambil semua data KECUALI yang ID-nya dipilih
    df_baru = df[df['id'] != str(id_transaksi)]
    save_all_data("transaksi", df_baru)

def edit_transaction(id_transaksi, tgl_baru, jenis_baru, kat_baru, nom_baru, ket_baru):
    df = get_data("transaksi")
    # Cari index baris yang mau diedit
    idx = df[df['id'] == str(id_transaksi)].index
    
    if not idx.empty:
        idx = idx[0]
        # Update data di DataFrame
        df.at[idx, 'tanggal'] = str(tgl_baru)
        df.at[idx, 'tipe'] = jenis_baru
        df.at[idx, 'kategori'] = kat_baru
        df.at[idx, 'nominal'] = nom_baru
        df.at[idx, 'keterangan'] = ket_baru
        
        # Simpan perubahan ke Google Sheets
        save_all_data("transaksi", df)
        return True
    return False

def update_kategori_bulk(df_baru):
    save_all_data("kategori", df_baru)

# --- FUNGSI LAIN (Hash, PDF, Init) ---
def hash_pass(password):
    return hashlib.sha256(password.encode()).hexdigest()

def init_default_data():
    df_users = get_data("users")
    if df_users.empty:
        pass_admin = hash_pass('admin123')
        add_row("users", ['admin', pass_admin, 'admin', 'Bendahara RT'])

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
    headers = ['Tgl', 'Tipe', 'Kategori', 'Nominal', 'Ket']
    w = [25, 25, 40, 35, 60]
    for i, h in enumerate(headers): pdf.cell(w[i], 10, h, 1)
    pdf.ln()
    total_masuk, total_keluar = 0, 0
    for _, row in dataframe.iterrows():
        try: nom = float(row['nominal'])
        except: nom = 0
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

# --- APLIKASI UTAMA ---
def main():
    st.set_page_config(page_title="Keuangan RT (Cloud)", layout="wide")
    
    # === SIDEBAR DARURAT (PERBAIKAN DATA) ===
    with st.sidebar:
        if st.checkbox("Tampilkan Opsi Perbaikan"):
            if st.button("Reset Header Transaksi"):
                sheet = connect_db()
                if sheet:
                    ws = sheet.worksheet("transaksi")
                    header = ['id', 'tanggal', 'tipe', 'kategori', 'nominal', 'keterangan', 'user_input', 'file_bukti']
                    ws.update(range_name='A1', values=[header])
                    st.success("Header direset!")

    # Login Logic
    if 'logged_in' not in st.session_state:
        st.session_state['logged_in'] = False

    if not st.session_state['logged_in']:
        st.title("🔐 Login Sistem")
        user = st.text_input("Username")
        pwd = st.text_input("Password", type='password')
        if st.button("Masuk"):
            df_users = get_data("users")
            if not df_users.empty:
                df_users['username'] = df_users['username'].astype(str)
                match = df_users[(df_users['username'] == user) & (df_users['password'] == hash_pass(pwd))]
                if not match.empty:
                    st.session_state['logged_in'] = True
                    st.session_state['username'] = match.iloc[0]['username']
                    st.session_state['role'] = match.iloc[0]['role']
                    st.session_state['nama'] = match.iloc[0]['nama_lengkap']
                    st.rerun()
                else:
                    st.error("Login Gagal.")
            else:
                if st.button("Generate Admin Default"):
                    init_default_data()
                    st.success("Admin dibuat: admin/admin123")
        return

    # Menu Navigasi
    st.sidebar.title(f"Halo, {st.session_state['nama']}")
    menu = ["Dashboard", "Riwayat Transaksi", "Laporan"]
    if st.session_state['role'] == 'admin':
        menu = ["Dashboard", "Input Transaksi", "Kelola Kategori", "Kelola Pengguna"] + menu
    choice = st.sidebar.radio("Menu", menu)
    
    if st.sidebar.button("Logout"):
        st.session_state.clear()
        st.rerun()

    # --- 1. DASHBOARD ---
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
            df['bulan'] = df['tanggal'].dt.strftime('%Y-%m')
            chart_data = df.groupby(['bulan', 'tipe'])['nominal'].sum().unstack().fillna(0)
            if 'Pemasukan' not in chart_data.columns: chart_data['Pemasukan'] = 0
            if 'Pengeluaran' not in chart_data.columns: chart_data['Pengeluaran'] = 0
            st.bar_chart(chart_data[['Pemasukan', 'Pengeluaran']], color=["#4CAF50", "#FF4B4B"])
        else:
            st.info("Data kosong.")

    # --- 2. INPUT TRANSAKSI ---
    elif choice == "Input Transaksi":
        st.header("📝 Input Baru")
        jenis = st.radio("Jenis", ["Pemasukan", "Pengeluaran"], horizontal=True)
        df_kat = get_data("kategori")
        list_kat = df_kat[df_kat['jenis'] == jenis]['nama'].tolist() if not df_kat.empty else ["Lainnya"]
        
        with st.form("input"):
            tgl = st.date_input("Tanggal", datetime.now())
            nom = st.number_input("Nominal", min_value=0, step=1000)
            kat = st.selectbox("Kategori", list_kat)
            ket = st.text_area("Keterangan")
            if st.form_submit_button("Simpan"):
                uid = str(uuid.uuid4())[:8]
                add_row("transaksi", [uid, str(tgl), jenis, kat, nom, ket, st.session_state['username'], "-"])
                st.success("Tersimpan!")

    # --- 3. RIWAYAT TRANSAKSI (FITUR BARU: EDIT & DELETE) ---
    elif choice == "Riwayat Transaksi":
        st.header("🗂️ Riwayat Transaksi")
        df = get_data("transaksi")
        
        if df.empty:
            st.info("Belum ada data transaksi.")
        else:
            # Tampilkan Tabel Utama
            st.dataframe(df, use_container_width=True)

            # Fitur Admin: Edit & Hapus
            if st.session_state['role'] == 'admin':
                st.divider()
                st.subheader("🛠️ Kelola Data (Admin)")
                
                # Pilihan Aksi
                aksi = st.radio("Pilih Aksi", ["Edit Data", "Hapus Data"], horizontal=True)
                
                # Dropdown Pilih Transaksi (Tampilkan ID - Keterangan biar mudah dipilih)
                # Buat list label untuk dropdown
                df['label'] = df['id'] + " | " + df['tanggal'].astype(str) + " | Rp " + df['nominal'].astype(str) + " | " + df['keterangan']
                pilihan_trx = st.selectbox("Pilih Transaksi:", df['label'].tolist())
                
                # Ambil ID asli dari pilihan
                id_pilih = pilihan_trx.split(" | ")[0]
                
                # Ambil data baris yang dipilih
                row_data = df[df['id'] == id_pilih].iloc[0]

                if aksi == "Hapus Data":
                    st.error(f"Anda akan menghapus transaksi: {row_data['keterangan']} (Rp {row_data['nominal']})")
                    if st.button("🗑️ HAPUS PERMANEN"):
                        delete_transaction(id_pilih)
                        st.success("Data berhasil dihapus!")
                        st.rerun()

                elif aksi == "Edit Data":
                    st.info("Silakan ubah data di bawah ini:")
                    
                    with st.form("form_edit"):
                        col1, col2 = st.columns(2)
                        
                        # Pre-fill form dengan data lama
                        tgl_edit = col1.date_input("Tanggal", pd.to_datetime(row_data['tanggal']))
                        jenis_edit = col2.selectbox("Jenis", ["Pemasukan", "Pengeluaran"], index=0 if row_data['tipe']=="Pemasukan" else 1)
                        
                        # Ambil kategori sesuai jenis yang dipilih
                        df_kat = get_data("kategori")
                        list_kat = df_kat[df_kat['jenis'] == jenis_edit]['nama'].tolist() if not df_kat.empty else ["Lainnya"]
                        
                        # Coba set default index kategori lama
                        try:
                            idx_kat = list_kat.index(row_data['kategori'])
                        except:
                            idx_kat = 0
                            
                        kat_edit = st.selectbox("Kategori", list_kat, index=idx_kat)
                        nom_edit = st.number_input("Nominal", value=float(row_data['nominal']), step=1000.0)
                        ket_edit = st.text_area("Keterangan", value=row_data['keterangan'])
                        
                        if st.form_submit_button("💾 UPDATE DATA"):
                            edit_transaction(id_pilih, tgl_edit, jenis_edit, kat_edit, nom_edit, ket_edit)
                            st.success("Data berhasil diperbarui!")
                            st.rerun()

    # --- 4. KELOLA KATEGORI ---
    elif choice == "Kelola Kategori":
        st.header("🏷️ Edit Kategori")
        df = get_data("kategori")
        edited = st.data_editor(df, num_rows="dynamic", hide_index=True)
        if st.button("Simpan ke Cloud"):
            update_kategori_bulk(edited)
            st.success("Berhasil update!")
            st.rerun()

    # --- 5. KELOLA PENGGUNA ---
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

    # --- 6. LAPORAN ---
    elif choice == "Laporan":
        st.header("Download Laporan")
        df = get_data("transaksi")
        if not df.empty:
            pdf = create_pdf(df)
            st.download_button("Download PDF", data=pdf, file_name="laporan.pdf")

if __name__ == '__main__':
    main()
