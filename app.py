import streamlit as st
import pandas as pd
from datetime import datetime
import hashlib
from fpdf import FPDF
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import uuid
import random
from fpdf import FPDF
import io

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
    
    for i, h in enumerate(headers): pdf.cell(widths[i], 10, h, 1, 0, 'C')
    pdf.ln()
    
    total = 0
    has_nominal = False
    
    for _, row in dataframe.iterrows():
        for i, c in enumerate(cols):
            val = str(row[c])
            if 'nominal' in c and val.replace('.','',1).isdigit(): 
                val_float = float(val)
                val = f"{val_float:,.0f}"
                has_nominal = True
                if 'tipe' in dataframe.columns:
                    if row['tipe'] == 'Pemasukan': total += val_float
                    else: total -= val_float
                else: total += val_float
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
    return {"Januari": 1, "Februari": 2, "Maret": 3, "April": 4, "Mei": 5, "Juni": 6, "Juli": 7, "Agustus": 8, "September": 9, "Oktober": 10, "November": 11, "Desember": 12}

def filter_by_date(df, col_name, month_name, year):
    if df.empty: return df
    try:
        df[col_name] = pd.to_datetime(df[col_name])
        month_idx = get_month_map()[month_name]
        return df[(df[col_name].dt.month == month_idx) & (df[col_name].dt.year == year)]
    except: return df

def init_default():
    if get_data("users").empty:
        add_row("users", ['admin', hash_pass('admin123'), 'admin', 'Bendahara'])

# --- MAIN APP ---
def main():
    st.set_page_config(page_title="Sistem RT Dashboard Pro", layout="wide")
    
    # Sidebar Setup
    with st.sidebar:
        if st.checkbox("⚙️ Setup DB"):
            if st.button("Buat Header"):
                sheet = connect_db()
                try:
                    for s in ["tunggakan", "arisan_peserta", "arisan_bayar", "kategori"]: 
                        try: sheet.add_worksheet(s, 100, 10) 
                        except: pass
                    sheet.worksheet("tunggakan").update(range_name='A1', values=[['id','nama_warga','periode','nominal','status']])
                    sheet.worksheet("arisan_peserta").update(range_name='A1', values=[['id','nama_warga','status_menang']])
                    sheet.worksheet("arisan_bayar").update(range_name='A1', values=[['id','nama_warga','periode','nominal','status_bayar','tanggal_bayar']])
                    sheet.worksheet("kategori").update(range_name='A1', values=[['id','nama','jenis']])
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

    # MENU (Diperbarui: Menambahkan 'Riwayat Kas' yang eksplisit)
    st.sidebar.title(f"Hi, {st.session_state['nama']}")
    
    menu_admin = ["Dashboard", "Input Kas", "Riwayat Kas", "Kelola Arisan", "Kelola Tunggakan", "Kelola Kategori", "User Management", "Laporan Kas"]
    menu_warga = ["Dashboard", "Riwayat Kas", "Info Arisan", "Info Tunggakan", "Laporan Kas"]
    
    menu = menu_admin if st.session_state['role'] == 'admin' else menu_warga
    choice = st.sidebar.radio("Menu Utama", menu)
    
    if st.sidebar.button("Keluar"): st.session_state.clear(); st.rerun()

    # --- 1. DASHBOARD (DIREVISI SESUAI PERMINTAAN) ---
    if choice == "Dashboard":
        st.header("📊 Dashboard Keuangan RT")
        
        df = get_data("transaksi")
        df_t = get_data("tunggakan")
        
        # Variabel Default
        saldo = 0
        pemasukan_total = 0
        pengeluaran_total = 0
        tunggakan_total = 0
        
        # Hitung Transaksi Kas
        if not df.empty:
            df['nominal'] = pd.to_numeric(df['nominal'], errors='coerce').fillna(0)
            df['tanggal'] = pd.to_datetime(df['tanggal'])
            
            pemasukan_total = df[df['tipe']=='Pemasukan']['nominal'].sum()
            pengeluaran_total = df[df['tipe']=='Pengeluaran']['nominal'].sum()
            saldo = pemasukan_total - pengeluaran_total
        
        # Hitung Tunggakan
        if not df_t.empty:
            df_t['nominal'] = pd.to_numeric(df_t['nominal'], errors='coerce').fillna(0)
            tunggakan_total = df_t[df_t['status']=='Belum Lunas']['nominal'].sum()

        # TAMPILAN 4 METRIK UTAMA
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("💰 Saldo Kas Saat Ini", f"Rp {saldo:,.0f}")
        c2.metric("📈 Total Pemasukan", f"Rp {pemasukan_total:,.0f}")
        c3.metric("📉 Total Pengeluaran", f"Rp {pengeluaran_total:,.0f}")
        c4.metric("❗ Total Tunggakan", f"Rp {tunggakan_total:,.0f}", delta_color="inverse")
        
        st.divider()
        
        # TAMPILAN GRAFIK TAHUN BERJALAN
        st.subheader(f"Grafik Keuangan Tahun {datetime.now().year}")
        if not df.empty:
            df_year = df[df['tanggal'].dt.year == datetime.now().year]
            if not df_year.empty:
                df_year['bulan'] = df_year['tanggal'].dt.strftime('%Y-%m')
                chart_data = df_year.groupby(['bulan', 'tipe'])['nominal'].sum().unstack().fillna(0)
                
                # Paksa agar kolom Pemasukan & Pengeluaran selalu ada (Anti Error Warna)
                if 'Pemasukan' not in chart_data.columns: chart_data['Pemasukan'] = 0
                if 'Pengeluaran' not in chart_data.columns: chart_data['Pengeluaran'] = 0
                
                # Urutkan kolom dan render
                st.bar_chart(chart_data[['Pemasukan', 'Pengeluaran']], color=["#4CAF50", "#FF4B4B"])
            else:
                st.info("Belum ada transaksi di tahun ini.")
        else:
            st.info("Belum ada data transaksi kas.")

    # --- 2. RIWAYAT KAS (FITUR YANG DIKEMBALIKAN) ---
    elif choice == "Riwayat Kas":
        st.header("🗂️ Riwayat Transaksi Kas")
        df = get_data("transaksi")
        
        if not df.empty:
            # Tampilkan Tabel
            st.dataframe(df.sort_values(by='tanggal', ascending=False), use_container_width=True)
            
            # Fitur Hapus (Khusus Admin)
            if st.session_state['role'] == 'admin':
                st.divider()
                with st.expander("🗑️ Hapus Transaksi (Admin Only)"):
                    id_del = st.text_input("Masukkan ID Transaksi untuk dihapus")
                    if st.button("Hapus Permanen"):
                        delete_row_by_id("transaksi", id_del)
                        st.success("Transaksi berhasil dihapus.")
                        st.rerun()
        else:
            st.info("Belum ada data riwayat transaksi.")

    # --- 3. INPUT KAS ---
    elif choice == "Input Kas":
        st.header("📝 Input Kas")
        jenis = st.radio("Tipe", ["Pemasukan","Pengeluaran"], horizontal=True)
        df_k = get_data("kategori")
        cats = ["Umum"]
        if not df_k.empty:
             cats = df_k[df_k['jenis'] == jenis]['nama'].tolist()
             if not cats: cats = ["Lainnya"]
             
        with st.form("trx"):
            tgl = st.date_input("Tanggal", datetime.now())
            nom = st.number_input("Nominal", step=1000)
            kat = st.selectbox("Kategori", cats)
            ket = st.text_area("Ket")
            if st.form_submit_button("Simpan"):
                add_row("transaksi", [str(uuid.uuid4())[:8], str(tgl), jenis, kat, nom, ket, st.session_state['username'], "-"])
                st.success("Ok")

    # --- 4. KELOLA TUNGGAKAN ---
    elif choice == "Kelola Tunggakan" or choice == "Info Tunggakan":
        st.header("❗ Manajemen Tunggakan")
        tab1, tab2, tab3 = st.tabs(["Daftar & Edit", "Tambah Data", "Laporan PDF"])
        
        with tab1:
            df_t = get_data("tunggakan")
            if not df_t.empty:
                if st.session_state['role'] == 'admin':
                    edited = st.data_editor(df_t, column_config={"id": st.column_config.TextColumn(disabled=True), "status": st.column_config.SelectboxColumn(options=["Belum Lunas", "Lunas"])}, hide_index=True)
                    if st.button("Simpan Perubahan"): save_all_data("tunggakan", edited); st.success("Disimpan!"); st.rerun()
                    with st.expander("Hapus Data"):
                         id_del = st.text_input("Masukkan ID untuk Hapus")
                         if st.button("Hapus Permanen"): delete_row_by_id("tunggakan", id_del); st.rerun()
                else: st.dataframe(df_t[df_t['status']=='Belum Lunas'])
            else: st.info("Kosong")

        with tab2:
            if st.session_state['role'] == 'admin':
                with st.form("add_t"):
                    n = st.text_input("Nama"); p = st.text_input("Periode"); nom = st.number_input("Nominal", step=5000)
                    s = st.selectbox("Status", ["Belum Lunas", "Lunas"])
                    if st.form_submit_button("Simpan"):
                        add_row("tunggakan", [str(uuid.uuid4())[:8], n, p, nom, s]); st.success("Ok")
            else: st.warning("Akses Admin")

        with tab3:
            df_t = get_data("tunggakan")
            ft = st.text_input("Cari Periode (Cth: Jan 2026)")
            if not df_t.empty:
                if ft: df_t = df_t[df_t['periode'].str.contains(ft, case=False, na=False)]
                st.dataframe(df_t)
                if st.button("Download PDF Tunggakan"):
                    pdf = create_pdf_universal(df_t, f"Laporan Tunggakan ({ft})", ['Nama', 'Periode', 'Nominal', 'Status'], ['nama_warga', 'periode', 'nominal', 'status'], [50, 50, 40, 40])
                    st.download_button("Download", pdf, "tunggakan.pdf")

    # --- 5. KELOLA ARISAN ---
    elif choice == "Kelola Arisan" or choice == "Info Arisan":
        st.header("🎲 Manajemen Arisan")
        tab1, tab2, tab3 = st.tabs(["Peserta & Kocokan", "Pembayaran", "Laporan PDF"])
        
        with tab1:
            if st.session_state['role']=='admin':
                if st.button("🎲 KOCOK ARISAN"):
                    msg, win = kocok_pemenang()
                    if win: st.balloons(); st.success(msg)
                    else: st.warning(msg)
                with st.expander("Tambah Peserta"):
                    nm = st.text_input("Nama Baru")
                    if st.button("Simpan Peserta"): add_row("arisan_peserta", [str(uuid.uuid4())[:8], nm, 'Belum']); st.rerun()
            st.dataframe(get_data("arisan_peserta"), use_container_width=True)

        with tab2:
            if st.session_state['role']=='admin':
                with st.form("bayar_ar"):
                    df_p = get_data("arisan_peserta")
                    n = st.selectbox("Nama", df_p['nama_warga'].tolist() if not df_p.empty else [])
                    p = st.text_input("Periode"); nom = st.number_input("Nominal", step=10000)
                    if st.form_submit_button("Bayar"):
                        add_row("arisan_bayar", [str(uuid.uuid4())[:8], n, p, nom, 'Lunas', str(datetime.now().date())])
                        st.success("Ok"); st.rerun()
            st.dataframe(get_data("arisan_bayar"))

        with tab3:
            c_m, c_y = st.columns(2)
            sel_month = c_m.selectbox("Bulan", list(get_month_map().keys()))
            sel_year = c_y.number_input("Tahun", min_value=2020, value=datetime.now().year)
            df_ab = filter_by_date(get_data("arisan_bayar"), 'tanggal_bayar', sel_month, sel_year)
            st.dataframe(df_ab)
            if not df_ab.empty and st.button("Download PDF Arisan"):
                pdf = create_pdf_universal(df_ab, f"Arisan {sel_month} {sel_year}", ['Nama', 'Periode', 'Nominal', 'Tgl'], ['nama_warga', 'periode', 'nominal', 'tanggal_bayar'], [50, 40, 40, 40])
                st.download_button("Download", pdf, "arisan.pdf")

    # --- 6. KELOLA KATEGORI ---
    elif choice == "Kelola Kategori":
        st.header("🏷️ Kelola Kategori")
        df_k = get_data("kategori")
        if not df_k.empty:
            edited = st.data_editor(df_k, num_rows="dynamic", hide_index=True)
            if st.button("Simpan Kategori"):
                save_all_data("kategori", edited)
                st.success("Tersimpan!")
                st.rerun()
        else:
            if st.button("Init Kategori"): 
                add_row("kategori", ["1", "Iuran", "Pemasukan"])
                st.rerun()

    # --- 7. LAPORAN & USER ---
    elif choice == "Laporan Kas":
        st.header("🖨️ Laporan Kas")
        c_m, c_y = st.columns(2)
        sel_month = c_m.selectbox("Bulan", list(get_month_map().keys()), key="kas_m")
        sel_year = c_y.number_input("Tahun", min_value=2020, value=datetime.now().year, key="kas_y")
        df = filter_by_date(get_data("transaksi"), 'tanggal', sel_month, sel_year)
        st.dataframe(df)
        if not df.empty and st.button("Download PDF Kas"):
             pdf = create_pdf_universal(df, f"Kas {sel_month} {sel_year}", ['Tgl', 'Tipe', 'Kat', 'Nominal'], ['tanggal', 'tipe', 'kategori', 'nominal'], [30, 30, 40, 40])
             st.download_button("Download", pdf, "kas.pdf")

    elif choice == "User Management":
        with st.form("u"):
            u=st.text_input("User"); p=st.text_input("Pass", type='password'); r=st.selectbox("Role",["warga","admin"])
            if st.form_submit_button("Add"): add_row("users",[u,hash_pass(p),r,u]); st.success("Ok")
        st.dataframe(get_data("users"))


if __name__ == '__main__':
    main()




