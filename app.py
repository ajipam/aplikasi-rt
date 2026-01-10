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

# --- FUNGSI KHUSUS ---
def delete_row_by_id(worksheet_name, id_val):
    df = get_data(worksheet_name)
    df = df[df['id'] != str(id_val)]
    save_all_data(worksheet_name, df)

def kocok_pemenang():
    df = get_data("arisan_peserta")
    if df.empty: return "Belum ada peserta", None
    
    kandidat = df[df['status_menang'] == 'Belum']
    reset_msg = ""
    
    # Jika semua sudah menang, reset semua
    if kandidat.empty:
        df['status_menang'] = 'Belum'
        save_all_data("arisan_peserta", df)
        kandidat = df 
        reset_msg = " (Putaran Baru!)"
    
    # Acak
    pemenang = kandidat.sample(1).iloc[0]
    nama_pemenang = pemenang['nama_warga']
    
    # Update status
    idx = df[df['id'] == pemenang['id']].index[0]
    df.at[idx, 'status_menang'] = 'Sudah'
    save_all_data("arisan_peserta", df)
    
    return f"🎉 {nama_pemenang} {reset_msg}", nama_pemenang

# --- PDF GENERATOR (LENGKAP: KAS, TUNGGAKAN, ARISAN) ---
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
    
    # Isi Tabel
    total = 0
    for _, row in dataframe.iterrows():
        for i, c in enumerate(cols):
            val = str(row[c])
            # Format Angka/Rupiah otomatis jika kolom mengandung 'nominal'
            if 'nominal' in c and val.replace('.','',1).isdigit(): 
                val_float = float(val)
                val = f"{val_float:,.0f}"
                if 'status' not in c: # Summing logic sederhana
                     total += val_float
            pdf.cell(widths[i], 8, val, 1)
        pdf.ln()
        
    return pdf.output(dest='S').encode('latin-1')

# --- HELPERS ---
def hash_pass(p): return hashlib.sha256(p.encode()).hexdigest()
def init_default():
    if get_data("users").empty:
        add_row("users", ['admin', hash_pass('admin123'), 'admin', 'Bendahara'])

# --- MAIN APPLICATION ---
def main():
    st.set_page_config(page_title="Sistem RT Super App", layout="wide")
    
    # Sidebar Setup Database (Sekali jalan)
    with st.sidebar:
        if st.checkbox("⚙️ Setup Database"):
            if st.button("Buat Semua Header Sheet"):
                sheet = connect_db()
                try:
                    # Buat sheet jika belum ada
                    sheets_needed = ["tunggakan", "arisan_peserta", "arisan_bayar"]
                    for s in sheets_needed:
                        try: sheet.add_worksheet(s, 100, 10)
                        except: pass
                    
                    # Isi Header default
                    sheet.worksheet("tunggakan").update(range_name='A1', values=[['id','nama_warga','periode','nominal','status']])
                    sheet.worksheet("arisan_peserta").update(range_name='A1', values=[['id','nama_warga','status_menang']])
                    sheet.worksheet("arisan_bayar").update(range_name='A1', values=[['id','nama_warga','periode','nominal','status_bayar','tanggal_bayar']])
                    st.success("Database Lengkap Siap!")
                except Exception as e: st.error(e)

    # LOGIN SYSTEM
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

    # NAVIGASI
    st.sidebar.title(f"Hi, {st.session_state['nama']}")
    menu_admin = ["Dashboard", "Input Kas", "Kelola Arisan", "Kelola Tunggakan", "Kelola Kategori", "User Management", "Laporan Kas"]
    menu_warga = ["Dashboard", "Riwayat Kas", "Info Arisan", "Info Tunggakan", "Laporan Kas"]
    
    menu = menu_admin if st.session_state['role'] == 'admin' else menu_warga
    choice = st.sidebar.radio("Menu Utama", menu)
    
    if st.sidebar.button("Keluar"): st.session_state.clear(); st.rerun()

    # --- 1. DASHBOARD ---
    if choice == "Dashboard":
        st.header("📊 Dashboard")
        
        # Info Kas
        df = get_data("transaksi")
        saldo = 0
        if not df.empty:
            df['nominal'] = pd.to_numeric(df['nominal'], errors='coerce').fillna(0)
            saldo = df[df['tipe']=='Pemasukan']['nominal'].sum() - df[df['tipe']=='Pengeluaran']['nominal'].sum()
        
        # Info Tunggakan
        df_t = get_data("tunggakan")
        tot_tunggak = 0
        if not df_t.empty:
            df_t['nominal'] = pd.to_numeric(df_t['nominal'], errors='coerce').fillna(0)
            tot_tunggak = df_t[df_t['status']=='Belum Lunas']['nominal'].sum()

        c1, c2, c3 = st.columns(3)
        c1.metric("Saldo Kas RT", f"Rp {saldo:,.0f}")
        c2.metric("Total Tunggakan Warga", f"Rp {tot_tunggak:,.0f}", delta_color="inverse")
        
        # Info Arisan
        df_a = get_data("arisan_peserta")
        if not df_a.empty:
            menang = df_a[df_a['status_menang']=='Sudah']
            last_win = menang.iloc[-1]['nama_warga'] if not menang.empty else "-"
            c3.metric("Pemenang Arisan Terakhir", last_win)

    # --- 2. KELOLA TUNGGAKAN (FITUR YANG SEMPAT HILANG - KEMBALI LENGKAP) ---
    elif choice == "Kelola Tunggakan" or choice == "Info Tunggakan":
        st.header("❗ Manajemen Tunggakan")
        
        # Warga hanya bisa melihat (Read Only)
        if st.session_state['role'] != 'admin':
            st.warning("Halaman ini berisi daftar kewajiban warga yang belum lunas.")
            df_t = get_data("tunggakan")
            if not df_t.empty:
                st.dataframe(df_t[df_t['status']=='Belum Lunas'])
            else:
                st.info("Tidak ada tunggakan.")
        
        # Admin Full Access
        else:
            tab1, tab2, tab3 = st.tabs(["➕ Tambah Data", "📝 Daftar & Update", "🖨️ Laporan PDF"])
            
            # Tab 1: Tambah
            with tab1:
                with st.form("tambah_tunggakan"):
                    col_a, col_b = st.columns(2)
                    nama = col_a.text_input("Nama Warga")
                    periode = col_b.text_input("Periode (Misal: Iuran Jan 2026)")
                    nominal = st.number_input("Nominal (Rp)", step=5000)
                    status = st.selectbox("Status Awal", ["Belum Lunas", "Lunas"])
                    
                    if st.form_submit_button("Simpan Tagihan"):
                        if nama:
                            add_row("tunggakan", [str(uuid.uuid4())[:8], nama, periode, nominal, status])
                            st.success("Tersimpan!")
                        else: st.error("Nama wajib diisi")

            # Tab 2: Edit/Delete
            with tab2:
                df_t = get_data("tunggakan")
                if not df_t.empty:
                    st.info("Edit langsung di tabel untuk ubah Status, lalu klik Simpan.")
                    edited = st.data_editor(
                        df_t, 
                        column_config={
                            "id": st.column_config.TextColumn(disabled=True),
                            "status": st.column_config.SelectboxColumn("Status", options=["Belum Lunas", "Lunas"], required=True)
                        },
                        hide_index=True, num_rows="dynamic"
                    )
                    
                    c_btn1, c_btn2 = st.columns(2)
                    if c_btn1.button("💾 Simpan Perubahan Status"):
                        save_all_data("tunggakan", edited)
                        st.success("Database Updated!")
                        st.rerun()
                    
                    with c_btn2:
                        with st.expander("Hapus Data"):
                            id_del = st.text_input("ID untuk dihapus")
                            if st.button("Hapus Permanen"):
                                delete_row_by_id("tunggakan", id_del)
                                st.success("Dihapus")
                                st.rerun()
                else: st.info("Data kosong")

            # Tab 3: Laporan
            with tab3:
                df_t = get_data("tunggakan")
                if not df_t.empty:
                    filter_s = st.selectbox("Filter", ["Semua", "Belum Lunas", "Lunas"])
                    if filter_s != "Semua":
                        df_t = df_t[df_t['status'] == filter_s]
                    
                    st.dataframe(df_t)
                    if st.button("Download PDF Tunggakan"):
                        pdf = create_pdf_universal(
                            df_t, 
                            "Laporan Tunggakan Warga",
                            ['Nama', 'Periode', 'Nominal', 'Status'],
                            ['nama_warga', 'periode', 'nominal', 'status'],
                            [50, 50, 40, 40]
                        )
                        st.download_button("Download PDF", pdf, "tunggakan.pdf")

    # --- 3. KELOLA ARISAN ---
    elif choice == "Kelola Arisan" or choice == "Info Arisan":
        st.header("🎲 Manajemen Arisan")
        tab1, tab2, tab3 = st.tabs(["👥 Peserta & Kocokan", "💰 Pembayaran", "📄 Laporan"])
        
        # Tab 1: Kocokan
        with tab1:
            if st.session_state['role'] == 'admin':
                with st.expander("Tambah Peserta"):
                    with st.form("add_p"):
                        nm = st.text_input("Nama")
                        if st.form_submit_button("Simpan"):
                            add_row("arisan_peserta", [str(uuid.uuid4())[:8], nm, 'Belum'])
                            st.success("Oke"); st.rerun()
                
                if st.button("🎲 KOCOK ARISAN", type="primary"):
                    msg, win = kocok_pemenang()
                    if win: 
                        st.balloons()
                        st.success(f"PEMENANG: {win}")
                    else: st.warning(msg)
            
            st.dataframe(get_data("arisan_peserta"), use_container_width=True)

        # Tab 2: Pembayaran
        with tab2:
            if st.session_state['role'] == 'admin':
                with st.form("bayar_ar"):
                    df_p = get_data("arisan_peserta")
                    nama = st.selectbox("Nama", df_p['nama_warga'].tolist() if not df_p.empty else [])
                    per = st.text_input("Periode (Cth: Feb 2026)")
                    nom = st.number_input("Nominal", step=10000)
                    if st.form_submit_button("Bayar"):
                        add_row("arisan_bayar", [str(uuid.uuid4())[:8], nama, per, nom, 'Lunas', str(datetime.now().date())])
                        st.success("Tercatat!"); st.rerun()
            st.dataframe(get_data("arisan_bayar"))

        # Tab 3: Laporan Arisan
        with tab3:
            df_ab = get_data("arisan_bayar")
            if not df_ab.empty and st.button("PDF Pembayaran Arisan"):
                pdf = create_pdf_universal(
                    df_ab, "Laporan Pembayaran Arisan",
                    ['Nama', 'Periode', 'Nominal', 'Tgl Bayar'],
                    ['nama_warga', 'periode', 'nominal', 'tanggal_bayar'],
                    [50, 40, 40, 40]
                )
                st.download_button("Download PDF", pdf, "arisan_bayar.pdf")

    # --- 4. INPUT KAS (Admin Only) ---
    elif choice == "Input Kas":
        st.header("📝 Input Kas RT")
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

    # --- 5. MENU LAINNYA ---
    elif choice == "Laporan Kas":
        st.header("Laporan Kas")
        df = get_data("transaksi")
        st.dataframe(df)
        if not df.empty and st.button("Download PDF Kas"):
             pdf = create_pdf_universal(df, "Laporan Kas RT", ['Tgl', 'Tipe', 'Kat', 'Nominal'], ['tanggal', 'tipe', 'kategori', 'nominal'], [30, 30, 40, 40])
             st.download_button("Download", pdf, "kas.pdf")

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
