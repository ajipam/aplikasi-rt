import streamlit as st
import pandas as pd
from datetime import datetime
import hashlib
from fpdf import FPDF
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import uuid
import random # Library untuk acak arisan

# --- KONFIGURASI ---
SCOPE = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
SHEET_NAME = "DB_KeuanganRT" 

def connect_db():
    try:
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, SCOPE)
        client = gspread.authorize(creds)
        sheet = client.open(SHEET_NAME)
        return sheet
    except Exception as e:
        st.error(f"Error Koneksi: {e}")
        return None

# --- FUNGSI CRUD DATABASE ---
def get_data(worksheet_name):
    sheet = connect_db()
    if sheet:
        try:
            ws = sheet.worksheet(worksheet_name)
            data = ws.get_all_records()
            df = pd.DataFrame(data)
            if 'id' in df.columns: df['id'] = df['id'].astype(str)
            return df
        except: return pd.DataFrame()
    return pd.DataFrame()

def add_row(worksheet_name, row_data):
    sheet = connect_db()
    if sheet:
        ws = sheet.worksheet(worksheet_name)
        ws.append_row(row_data)

def save_all_data(worksheet_name, df):
    sheet = connect_db()
    if sheet:
        ws = sheet.worksheet(worksheet_name)
        ws.clear()
        ws.update(range_name='A1', values=[df.columns.values.tolist()] + df.values.tolist())

# --- LOGIKA ARISAN ---
def kocok_pemenang():
    df = get_data("arisan_peserta")
    if df.empty:
        return "Belum ada peserta", None

    # Filter siapa yang belum menang
    kandidat = df[df['status_menang'] == 'Belum']

    # Jika KOSONG (Semua sudah menang), Reset putaran
    reset_msg = ""
    if kandidat.empty:
        df['status_menang'] = 'Belum' # Reset lokal
        save_all_data("arisan_peserta", df) # Simpan reset ke DB
        kandidat = df # Ambil semua lagi
        reset_msg = " (Putaran Baru Dimulai!)"

    # Acak 1 Pemenang
    pemenang = kandidat.sample(1).iloc[0]
    nama_pemenang = pemenang['nama_warga']
    id_pemenang = pemenang['id']

    # Update status pemenang jadi 'Sudah'
    idx = df[df['id'] == id_pemenang].index[0]
    df.at[idx, 'status_menang'] = 'Sudah'
    save_all_data("arisan_peserta", df)

    return f"🎉 {nama_pemenang} {reset_msg}", nama_pemenang

# --- FUNGSI PDF (Lap Kas, Tunggakan, Arisan) ---
class PDF(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 14)
        self.cell(0, 10, 'Sistem Manajemen RT', 0, 1, 'C')
        self.ln(5)
    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.cell(0, 10, f'Halaman {self.page_no()}', 0, 0, 'C')

def create_pdf_arisan(dataframe, judul):
    pdf = PDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 10, judul, 0, 1, 'C')
    pdf.ln(5)
    pdf.set_font("Arial", size=10)
    
    # Deteksi Kolom
    if 'status_menang' in dataframe.columns: # Laporan Peserta
        headers = ['Nama Peserta', 'Status Menang']
        cols = ['nama_warga', 'status_menang']
        w = [100, 50]
    else: # Laporan Pembayaran
        headers = ['Nama', 'Periode', 'Nominal', 'Status', 'Tgl Bayar']
        cols = ['nama_warga', 'periode', 'nominal', 'status_bayar', 'tanggal_bayar']
        w = [40, 40, 35, 35, 35]

    for i, h in enumerate(headers): pdf.cell(w[i], 10, h, 1, 0, 'C')
    pdf.ln()
    
    for _, row in dataframe.iterrows():
        for i, c in enumerate(cols):
            val = str(row[c])
            if c == 'nominal': val = f"{float(val):,.0f}"
            pdf.cell(w[i], 8, val, 1)
        pdf.ln()
    return pdf.output(dest='S').encode('latin-1')

# --- HELPERS ---
def hash_pass(p): return hashlib.sha256(p.encode()).hexdigest()
def init_default():
    if get_data("users").empty:
        add_row("users", ['admin', hash_pass('admin123'), 'admin', 'Bendahara'])

# --- MAIN APP ---
def main():
    st.set_page_config(page_title="Sistem RT Super App", layout="wide")
    
    # Sidebar Setup
    with st.sidebar:
        if st.checkbox("⚙️ Setup Database Awal"):
            if st.button("Buat Header Arisan"):
                sheet = connect_db()
                try: 
                    sheet.add_worksheet("arisan_peserta", 100, 5)
                    sheet.add_worksheet("arisan_bayar", 100, 6)
                except: pass
                
                # Isi Header
                ws1 = sheet.worksheet("arisan_peserta")
                ws1.update(range_name='A1', values=[['id','nama_warga','status_menang']])
                ws2 = sheet.worksheet("arisan_bayar")
                ws2.update(range_name='A1', values=[['id','nama_warga','periode','nominal','status_bayar','tanggal_bayar']])
                st.success("Database Arisan Siap!")

    # Login
    if 'logged_in' not in st.session_state: st.session_state['logged_in'] = False
    if not st.session_state['logged_in']:
        st.title("🔐 Login Sistem RT")
        user = st.text_input("Username")
        pwd = st.text_input("Password", type='password')
        if st.button("Masuk"):
            df = get_data("users")
            if not df.empty:
                df['username'] = df['username'].astype(str)
                match = df[(df['username']==user) & (df['password']==hash_pass(pwd))]
                if not match.empty:
                    st.session_state.update({'logged_in':True, 'role':match.iloc[0]['role'], 'nama':match.iloc[0]['nama_lengkap'], 'username':match.iloc[0]['username']})
                    st.rerun()
            else:
                if st.button("Init Admin"): init_default()
        return

    # Menu
    st.sidebar.title(f"Hi, {st.session_state['nama']}")
    
    menu_admin = ["Dashboard", "Input Kas", "Kelola Arisan", "Kelola Tunggakan", "Kelola Kategori", "User Management", "Laporan Kas"]
    menu_warga = ["Dashboard", "Riwayat Kas", "Info Arisan", "Laporan Kas"]
    
    menu = menu_admin if st.session_state['role'] == 'admin' else menu_warga
    choice = st.sidebar.radio("Menu Utama", menu)
    
    if st.sidebar.button("Keluar"): st.session_state.clear(); st.rerun()

    # --- 1. DASHBOARD ---
    if choice == "Dashboard":
        st.header("📊 Dashboard Warga")
        df = get_data("transaksi")
        if not df.empty:
            df['nominal'] = pd.to_numeric(df['nominal'], errors='coerce').fillna(0)
            saldo = df[df['tipe']=='Pemasukan']['nominal'].sum() - df[df['tipe']=='Pengeluaran']['nominal'].sum()
            st.metric("Saldo Kas RT", f"Rp {saldo:,.0f}")
        
        # Info Pemenang Arisan Terakhir (Ambil dari yang status 'Sudah' paling bawah/acak kalau belum ada timestamp)
        df_arisan = get_data("arisan_peserta")
        if not df_arisan.empty:
            pemenang = df_arisan[df_arisan['status_menang']=='Sudah']
            if not pemenang.empty:
                st.info(f"🏆 Pemenang Arisan Terakhir: {pemenang.iloc[-1]['nama_warga']}")
            else:
                st.info("Belum ada pemenang arisan periode ini.")

    # --- 2. KELOLA ARISAN (FITUR UTAMA BARU) ---
    elif choice == "Kelola Arisan" or choice == "Info Arisan":
        st.header("🎲 Manajemen Arisan")
        
        tab1, tab2, tab3 = st.tabs(["👥 Peserta & Kocokan", "💰 Pembayaran", "📄 Laporan"])
        
        # TAB 1: PESERTA & KOCOKAN
        with tab1:
            if st.session_state['role'] == 'admin':
                with st.expander("➕ Tambah Peserta Baru"):
                    with st.form("add_peserta"):
                        nm = st.text_input("Nama Warga")
                        if st.form_submit_button("Simpan Peserta"):
                            add_row("arisan_peserta", [str(uuid.uuid4())[:8], nm, 'Belum'])
                            st.success("Peserta ditambahkan")
                            st.rerun()

            col_kocok, col_list = st.columns([1, 2])
            
            with col_kocok:
                st.subheader("Kocokan")
                if st.session_state['role'] == 'admin':
                    if st.button("🎲 KOCOK ARISAN SEKARANG", type="primary"):
                        msg, win = kocok_pemenang()
                        if win:
                            st.balloons()
                            st.success(f"PEMENANG: {win}")
                        else:
                            st.warning(msg)
                else:
                    st.write("Hanya Admin yang bisa mengocok arisan.")
            
            with col_list:
                st.subheader("Daftar Peserta")
                df_p = get_data("arisan_peserta")
                st.dataframe(df_p, use_container_width=True)
                
                # Fitur Reset Manual (Admin)
                if st.session_state['role'] == 'admin' and not df_p.empty:
                    if st.button("🔄 Reset Manual Semua Status ke 'Belum'"):
                        df_p['status_menang'] = 'Belum'
                        save_all_data("arisan_peserta", df_p)
                        st.success("Status direset!")
                        st.rerun()

        # TAB 2: PEMBAYARAN BULANAN
        with tab2:
            st.subheader("Pembayaran Arisan")
            
            if st.session_state['role'] == 'admin':
                # Form Input Pembayaran
                with st.form("bayar_arisan"):
                    c1, c2, c3 = st.columns(3)
                    df_peserta = get_data("arisan_peserta")
                    opts = df_peserta['nama_warga'].tolist() if not df_peserta.empty else []
                    
                    nama_byr = c1.selectbox("Nama Warga", opts)
                    periode_byr = c2.text_input("Periode (Cth: Jan 2026)")
                    nom_byr = c3.number_input("Nominal", step=10000)
                    
                    if st.form_submit_button("Catat Pembayaran"):
                        add_row("arisan_bayar", [str(uuid.uuid4())[:8], nama_byr, periode_byr, nom_byr, 'Lunas', str(datetime.now().date())])
                        st.success("Pembayaran dicatat!")
                        st.rerun()
            
            # Tabel Pembayaran
            df_b = get_data("arisan_bayar")
            if not df_b.empty:
                st.dataframe(df_b, use_container_width=True)
                # Fitur Delete (Admin)
                if st.session_state['role'] == 'admin':
                     with st.expander("Hapus Data Pembayaran"):
                         id_hapus = st.text_input("Masukkan ID untuk dihapus")
                         if st.button("Hapus Data Bayar"):
                             df_new = df_b[df_b['id'] != id_hapus]
                             save_all_data("arisan_bayar", df_new)
                             st.success("Dihapus")
                             st.rerun()
            else:
                st.info("Belum ada data pembayaran.")

        # TAB 3: LAPORAN
        with tab3:
            st.subheader("Laporan Arisan")
            col_L1, col_L2 = st.columns(2)
            
            with col_L1:
                st.write("**Laporan Status Pemenang**")
                df_peserta = get_data("arisan_peserta")
                if st.button("Download PDF Status Peserta"):
                    pdf = create_pdf_arisan(df_peserta, "Laporan Status Arisan")
                    st.download_button("Unduh PDF", pdf, "status_arisan.pdf")
            
            with col_L2:
                st.write("**Laporan Pembayaran**")
                df_bayar = get_data("arisan_bayar")
                if st.button("Download PDF Pembayaran"):
                    pdf = create_pdf_arisan(df_bayar, "Laporan Pembayaran Arisan")
                    st.download_button("Unduh PDF", pdf, "pembayaran_arisan.pdf")

    # --- 3. INPUT KAS (Admin Only) ---
    elif choice == "Input Kas":
        st.header("📝 Input Kas RT")
        # (Kode sama seperti sebelumnya...)
        jenis = st.radio("Tipe", ["Pemasukan","Pengeluaran"], horizontal=True)
        df_k = get_data("kategori")
        cats = df_k[df_k['jenis']==jenis]['nama'].tolist() if not df_k.empty else ["Umum"]
        with st.form("trx"):
            tgl = st.date_input("Tanggal", datetime.now())
            nom = st.number_input("Nominal", step=1000)
            kat = st.selectbox("Kategori", cats)
            ket = st.text_area("Keterangan")
            if st.form_submit_button("Simpan"):
                add_row("transaksi", [str(uuid.uuid4())[:8], str(tgl), jenis, kat, nom, ket, st.session_state['username'], "-"])
                st.success("Tersimpan!")

    # --- 4. KELOLA TUNGGAKAN (Sama seperti sebelumnya) ---
    elif choice == "Kelola Tunggakan":
        st.header("❗ Kelola Tunggakan Iuran Warga")
        # (Copy logika tunggakan yang sebelumnya di sini atau gunakan kode lengkap di atas yang sudah saya gabung)
        # Sederhananya menampilkan tabel tunggakan
        df_t = get_data("tunggakan")
        if not df_t.empty:
            edited = st.data_editor(df_t, key="edit_tunggakan", num_rows="dynamic")
            if st.button("Simpan Perubahan Tunggakan"):
                save_all_data("tunggakan", edited)
                st.success("Updated!")
        else:
            st.info("Tidak ada tunggakan.")

    # --- FITUR LAINNYA ---
    elif choice == "Laporan Kas":
        # (Fitur laporan lama)
        st.dataframe(get_data("transaksi"))
    
    elif choice == "User Management":
        st.header("👥 User Management")
        with st.form("u"):
            u=st.text_input("User"); p=st.text_input("Pass", type='password'); r=st.selectbox("Role",["warga","admin"])
            if st.form_submit_button("Add"): add_row("users",[u,hash_pass(p),r,u]); st.success("Ok")
        st.dataframe(get_data("users"))
        
    elif choice == "Kelola Kategori":
        st.dataframe(get_data("kategori"))

if __name__ == '__main__':
    main()
