import streamlit as st
import pandas as pd
from datetime import datetime
import hashlib
from fpdf import FPDF
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import uuid
import random

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

# --- FUNGSI DATABASE (CRUD) ---
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

def delete_row_by_id(worksheet_name, id_val):
    df = get_data(worksheet_name)
    df = df[df['id'] != str(id_val)]
    save_all_data(worksheet_name, df)

# --- LOGIKA ARISAN ---
def kocok_pemenang():
    df = get_data("arisan_peserta")
    if df.empty: return "Belum ada peserta", None
    
    kandidat = df[df['status_menang'] == 'Belum']
    reset_msg = ""
    
    if kandidat.empty:
        df['status_menang'] = 'Belum'
        save_all_data("arisan_peserta", df)
        kandidat = df 
        reset_msg = " (Putaran Baru!)"
    
    pemenang = kandidat.sample(1).iloc[0]
    idx = df[df['id'] == pemenang['id']].index[0]
    df.at[idx, 'status_menang'] = 'Sudah'
    save_all_data("arisan_peserta", df)
    
    return f"🎉 {pemenang['nama_warga']} {reset_msg}", pemenang['nama_warga']

# --- PDF GENERATOR ---
class PDF(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 14)
        self.cell(0, 10, 'Sistem Manajemen RT', 0, 1, 'C')
        self.ln(5)
    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.cell(0, 10, f'Halaman {self.page_no()}', 0, 0, 'C')

def create_pdf_universal(dataframe, judul, headers, cols, widths):
    pdf = PDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 10, judul, 0, 1, 'C')
    pdf.ln(5)
    pdf.set_font("Arial", size=10)
    
    # Header Tabel
    for i, h in enumerate(headers): pdf.cell(widths[i], 10, h, 1, 0, 'C')
    pdf.ln()
    
    total = 0
    has_nominal = False
    
    for _, row in dataframe.iterrows():
        for i, c in enumerate(cols):
            val = str(row[c])
            # Format Rupiah
            if 'nominal' in c and val.replace('.','',1).isdigit(): 
                val_float = float(val)
                val = f"{val_float:,.0f}"
                has_nominal = True
                
                # Logic Saldo sederhana (Kas)
                if 'tipe' in dataframe.columns:
                    if row['tipe'] == 'Pemasukan': total += val_float
                    else: total -= val_float
                else:
                    total += val_float # Default sum
                    
            pdf.cell(widths[i], 8, val, 1)
        pdf.ln()
    
    if has_nominal:
        pdf.ln(5)
        pdf.set_font("Arial", 'B', 10)
        label_total = "Sisa Saldo" if 'tipe' in dataframe.columns else "Total"
        pdf.cell(0, 8, f"{label_total}: Rp {total:,.0f}", 0, 1)
        
    return pdf.output(dest='S').encode('latin-1')

# --- HELPERS ---
def hash_pass(p): return hashlib.sha256(p.encode()).hexdigest()

def get_month_map():
    return {
        "Januari": 1, "Februari": 2, "Maret": 3, "April": 4, "Mei": 5, "Juni": 6,
        "Juli": 7, "Agustus": 8, "September": 9, "Oktober": 10, "November": 11, "Desember": 12
    }

def filter_by_date(df, col_name, month_name, year):
    """Filter DataFrame berdasarkan bulan dan tahun"""
    if df.empty: return df
    try:
        df[col_name] = pd.to_datetime(df[col_name])
        month_idx = get_month_map()[month_name]
        return df[(df[col_name].dt.month == month_idx) & (df[col_name].dt.year == year)]
    except:
        return df

def init_default():
    if get_data("users").empty:
        add_row("users", ['admin', hash_pass('admin123'), 'admin', 'Bendahara'])

# --- MAIN APP ---
def main():
    st.set_page_config(page_title="Sistem RT Final", layout="wide")
    
    # Setup Sidebar
    with st.sidebar:
        if st.checkbox("⚙️ Setup DB"):
            if st.button("Buat Header"):
                sheet = connect_db()
                try:
                    for s in ["tunggakan", "arisan_peserta", "arisan_bayar"]: 
                        try: sheet.add_worksheet(s, 100, 10) 
                        except: pass
                    sheet.worksheet("tunggakan").update(range_name='A1', values=[['id','nama_warga','periode','nominal','status']])
                    sheet.worksheet("arisan_peserta").update(range_name='A1', values=[['id','nama_warga','status_menang']])
                    sheet.worksheet("arisan_bayar").update(range_name='A1', values=[['id','nama_warga','periode','nominal','status_bayar','tanggal_bayar']])
                    st.success("Siap!")
                except: pass

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
    menu_admin = ["Dashboard", "Input Kas", "Kelola Arisan", "Kelola Tunggakan", "User Management", "Laporan Kas"]
    menu_warga = ["Dashboard", "Riwayat Kas", "Info Arisan", "Info Tunggakan", "Laporan Kas"]
    menu = menu_admin if st.session_state['role'] == 'admin' else menu_warga
    choice = st.sidebar.radio("Menu Utama", menu)
    
    if st.sidebar.button("Keluar"): st.session_state.clear(); st.rerun()

    # --- 1. DASHBOARD ---
    if choice == "Dashboard":
        st.header("📊 Dashboard")
        df = get_data("transaksi")
        saldo, tunggak = 0, 0
        if not df.empty:
            df['nominal'] = pd.to_numeric(df['nominal'], errors='coerce').fillna(0)
            saldo = df[df['tipe']=='Pemasukan']['nominal'].sum() - df[df['tipe']=='Pengeluaran']['nominal'].sum()
        
        df_t = get_data("tunggakan")
        if not df_t.empty:
            df_t['nominal'] = pd.to_numeric(df_t['nominal'], errors='coerce').fillna(0)
            tunggak = df_t[df_t['status']=='Belum Lunas']['nominal'].sum()

        c1, c2, c3 = st.columns(3)
        c1.metric("Saldo Kas", f"Rp {saldo:,.0f}")
        c2.metric("Total Tunggakan", f"Rp {tunggak:,.0f}", delta_color="inverse")
        
        df_a = get_data("arisan_peserta")
        win = "-"
        if not df_a.empty:
            w = df_a[df_a['status_menang']=='Sudah']
            if not w.empty: win = w.iloc[-1]['nama_warga']
        c3.metric("Pemenang Arisan Terakhir", win)

    # --- 2. KELOLA TUNGGAKAN ---
    elif choice == "Kelola Tunggakan" or choice == "Info Tunggakan":
        st.header("❗ Manajemen Tunggakan")
        tab1, tab2, tab3 = st.tabs(["Daftar & Edit", "Tambah Data (Admin)", "Laporan PDF"])
        
        with tab1:
            df_t = get_data("tunggakan")
            if not df_t.empty:
                if st.session_state['role'] == 'admin':
                    edited = st.data_editor(df_t, column_config={"id": st.column_config.TextColumn(disabled=True), "status": st.column_config.SelectboxColumn(options=["Belum Lunas", "Lunas"])}, hide_index=True)
                    if st.button("Simpan Perubahan"): save_all_data("tunggakan", edited); st.success("Disimpan!"); st.rerun()
                    
                    with st.expander("Hapus Data"):
                        id_del = st.text_input("ID Hapus")
                        if st.button("Hapus"): delete_row_by_id("tunggakan", id_del); st.rerun()
                else:
                    st.dataframe(df_t[df_t['status']=='Belum Lunas'])
            else: st.info("Kosong")

        with tab2:
            if st.session_state['role'] == 'admin':
                with st.form("add_t"):
                    n = st.text_input("Nama"); p = st.text_input("Periode (Cth: Jan 2026)"); nom = st.number_input("Nominal", step=5000)
                    s = st.selectbox("Status", ["Belum Lunas", "Lunas"])
                    if st.form_submit_button("Simpan"):
                        add_row("tunggakan", [str(uuid.uuid4())[:8], n, p, nom, s])
                        st.success("Ok")
            else: st.warning("Akses Admin")

        with tab3:
            st.subheader("Cetak Laporan Tunggakan")
            # Filter Tunggakan berdasarkan String Periode (Karena bukan format tanggal murni)
            df_t = get_data("tunggakan")
            filter_text = st.text_input("Cari Periode (Contoh: Jan 2026)", "")
            
            if not df_t.empty:
                df_print = df_t.copy()
                if filter_text:
                    # Filter teks case-insensitive
                    df_print = df_print[df_print['periode'].str.contains(filter_text, case=False, na=False)]
                
                st.dataframe(df_print)
                
                if st.button("Download PDF Tunggakan"):
                    title = f"Laporan Tunggakan ({filter_text})" if filter_text else "Laporan Semua Tunggakan"
                    pdf = create_pdf_universal(
                        df_print, title,
                        ['Nama', 'Periode', 'Nominal', 'Status'],
                        ['nama_warga', 'periode', 'nominal', 'status'],
                        [50, 50, 40, 40]
                    )
                    st.download_button("Download PDF", pdf, "tunggakan.pdf")

    # --- 3. KELOLA ARISAN ---
    elif choice == "Kelola Arisan" or choice == "Info Arisan":
        st.header("🎲 Manajemen Arisan")
        tab1, tab2, tab3 = st.tabs(["Peserta & Kocokan", "Pembayaran", "Laporan PDF"])
        
        with tab1: # Kocokan
            if st.session_state['role']=='admin':
                if st.button("🎲 KOCOK ARISAN"):
                    msg, win = kocok_pemenang()
                    if win: st.balloons(); st.success(msg)
                    else: st.warning(msg)
                with st.expander("Tambah Peserta"):
                    nm = st.text_input("Nama Baru")
                    if st.button("Simpan Peserta"): add_row("arisan_peserta", [str(uuid.uuid4())[:8], nm, 'Belum']); st.rerun()
            st.dataframe(get_data("arisan_peserta"), use_container_width=True)

        with tab2: # Bayar
            if st.session_state['role']=='admin':
                with st.form("bayar_ar"):
                    df_p = get_data("arisan_peserta")
                    n = st.selectbox("Nama", df_p['nama_warga'].tolist() if not df_p.empty else [])
                    p = st.text_input("Periode (Cth: Jan 2026)"); nom = st.number_input("Nominal", step=10000)
                    if st.form_submit_button("Bayar"):
                        add_row("arisan_bayar", [str(uuid.uuid4())[:8], n, p, nom, 'Lunas', str(datetime.now().date())])
                        st.success("Ok"); st.rerun()
            st.dataframe(get_data("arisan_bayar"))

        with tab3: # Laporan
            st.subheader("Cetak Laporan Pembayaran Arisan")
            
            # === FILTER BULAN & TAHUN ===
            c_m, c_y = st.columns(2)
            sel_month = c_m.selectbox("Pilih Bulan", list(get_month_map().keys()))
            sel_year = c_y.number_input("Pilih Tahun", min_value=2020, max_value=2030, value=datetime.now().year)
            
            df_ab = get_data("arisan_bayar")
            if not df_ab.empty:
                # Filter Data
                df_ab_filtered = filter_by_date(df_ab, 'tanggal_bayar', sel_month, sel_year)
                
                st.write(f"Menampilkan data: {sel_month} {sel_year}")
                st.dataframe(df_ab_filtered)
                
                if not df_ab_filtered.empty and st.button("Download Laporan Arisan"):
                    pdf = create_pdf_universal(
                        df_ab_filtered, f"Laporan Arisan - {sel_month} {sel_year}",
                        ['Nama', 'Periode', 'Nominal', 'Tgl Bayar'],
                        ['nama_warga', 'periode', 'nominal', 'tanggal_bayar'],
                        [50, 40, 40, 40]
                    )
                    st.download_button("Download PDF", pdf, f"arisan_{sel_month}_{sel_year}.pdf")
            else:
                st.info("Data pembayaran kosong.")

    # --- 4. INPUT KAS ---
    elif choice == "Input Kas":
        st.header("📝 Input Kas")
        jenis = st.radio("Tipe", ["Pemasukan","Pengeluaran"], horizontal=True)
        cats = ["Iuran", "Sumbangan", "Lainnya"] # Bisa ambil DB jika mau
        with st.form("trx"):
            tgl = st.date_input("Tanggal", datetime.now())
            nom = st.number_input("Nominal", step=1000)
            kat = st.selectbox("Kategori", cats)
            ket = st.text_area("Ket")
            if st.form_submit_button("Simpan"):
                add_row("transaksi", [str(uuid.uuid4())[:8], str(tgl), jenis, kat, nom, ket, st.session_state['username'], "-"])
                st.success("Ok")

    # --- 5. LAPORAN KAS ---
    elif choice == "Laporan Kas":
        st.header("🖨️ Laporan Kas Bulanan")
        
        # === FILTER BULAN & TAHUN ===
        c_m, c_y = st.columns(2)
        sel_month = c_m.selectbox("Pilih Bulan", list(get_month_map().keys()), key="kas_m")
        sel_year = c_y.number_input("Pilih Tahun", min_value=2020, max_value=2030, value=datetime.now().year, key="kas_y")
        
        df = get_data("transaksi")
        if not df.empty:
            df_filtered = filter_by_date(df, 'tanggal', sel_month, sel_year)
            
            st.dataframe(df_filtered)
            
            if not df_filtered.empty:
                c1, c2 = st.columns(2)
                with c1:
                    if st.button("Download PDF Kas"):
                        pdf = create_pdf_universal(
                            df_filtered, f"Laporan Kas - {sel_month} {sel_year}",
                            ['Tgl', 'Tipe', 'Kat', 'Nominal'], 
                            ['tanggal', 'tipe', 'kategori', 'nominal'], 
                            [30, 30, 40, 40]
                        )
                        st.download_button("Download PDF", pdf, f"kas_{sel_month}.pdf")
                with c2:
                    csv = df_filtered.to_csv(index=False).encode('utf-8')
                    st.download_button("Download Excel/CSV", csv, "kas.csv")
        else:
            st.info("Belum ada data transaksi.")

    elif choice == "User Management":
        with st.form("u"):
            u=st.text_input("User"); p=st.text_input("Pass", type='password'); r=st.selectbox("Role",["warga","admin"])
            if st.form_submit_button("Add"): add_row("users",[u,hash_pass(p),r,u]); st.success("Ok")
        st.dataframe(get_data("users"))

if __name__ == '__main__':
    main()
