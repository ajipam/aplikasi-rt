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

# --- FUNGSI CRUD UMUM ---
def get_data(worksheet_name):
    sheet = connect_db()
    if sheet:
        try:
            ws = sheet.worksheet(worksheet_name)
            data = ws.get_all_records()
            df = pd.DataFrame(data)
            if 'id' in df.columns: df['id'] = df['id'].astype(str)
            return df
        except: return pd.DataFrame() # Jika sheet belum ada
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

# --- FUNGSI KHUSUS TUNGGAKAN ---
def delete_tunggakan(id_item):
    df = get_data("tunggakan")
    df = df[df['id'] != str(id_item)]
    save_all_data("tunggakan", df)

def update_status_tunggakan(df_edited):
    # Simpan perubahan status dari tabel editor
    save_all_data("tunggakan", df_edited)

# --- PDF GENERATOR ---
class PDF(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 14)
        self.cell(0, 10, 'Sistem Keuangan & Tunggakan RT', 0, 1, 'C')
        self.ln(5)
    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.cell(0, 10, f'Halaman {self.page_no()}', 0, 0, 'C')

def create_pdf_laporan(dataframe):
    pdf = PDF()
    pdf.add_page()
    pdf.set_font("Arial", size=10)
    # Header
    headers = ['Tgl', 'Tipe', 'Kategori', 'Nominal', 'Ket']
    w = [25, 25, 40, 35, 60]
    for i, h in enumerate(headers): pdf.cell(w[i], 10, h, 1)
    pdf.ln()
    # Isi
    total = 0
    for _, row in dataframe.iterrows():
        try: nom = float(row['nominal'])
        except: nom = 0
        if row['tipe'] == 'Pemasukan': total += nom
        else: total -= nom
        
        pdf.cell(w[0], 8, str(row['tanggal']), 1)
        pdf.cell(w[1], 8, str(row['tipe']), 1)
        pdf.cell(w[2], 8, str(row['kategori']), 1)
        pdf.cell(w[3], 8, f"{nom:,.0f}", 1, 0, 'R')
        pdf.cell(w[4], 8, str(row['keterangan'])[:30], 1, 1)
    pdf.ln(5)
    pdf.cell(0, 8, f"Saldo Akhir: Rp {total:,.0f}", 0, 1)
    return pdf.output(dest='S').encode('latin-1')

def create_pdf_tunggakan(dataframe):
    pdf = PDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 10, 'LAPORAN DAFTAR TUNGGAKAN WARGA', 0, 1, 'C')
    pdf.ln(5)
    
    pdf.set_font("Arial", size=10)
    headers = ['Nama Warga', 'Periode', 'Nominal', 'Status']
    w = [60, 40, 40, 40]
    
    # Header Tabel
    for i, h in enumerate(headers): pdf.cell(w[i], 10, h, 1, 0, 'C')
    pdf.ln()
    
    total_tunggakan = 0
    for _, row in dataframe.iterrows():
        try: nom = float(row['nominal'])
        except: nom = 0
        if row['status'] == 'Belum Lunas':
            total_tunggakan += nom
            
        pdf.cell(w[0], 8, str(row['nama_warga']), 1)
        pdf.cell(w[1], 8, str(row['periode']), 1)
        pdf.cell(w[2], 8, f"{nom:,.0f}", 1, 0, 'R')
        pdf.cell(w[3], 8, str(row['status']), 1, 1, 'C')
        
    pdf.ln(5)
    pdf.set_font("Arial", 'B', 10)
    pdf.cell(0, 8, f"Total Potensi Tunggakan: Rp {total_tunggakan:,.0f}", 0, 1)
    return pdf.output(dest='S').encode('latin-1')

# --- HELPERS ---
def hash_pass(p): return hashlib.sha256(p.encode()).hexdigest()
def init_default():
    if get_data("users").empty:
        add_row("users", ['admin', hash_pass('admin123'), 'admin', 'Bendahara'])

# --- MAIN APP ---
def main():
    st.set_page_config(page_title="Sistem RT", layout="wide")
    
    # Sidebar Reset (Opsional)
    with st.sidebar:
        if st.checkbox("⚙️ Opsi Database"):
            if st.button("Reset Header Tunggakan"):
                sheet = connect_db()
                if sheet:
                    try: sheet.add_worksheet("tunggakan", 100, 5)
                    except: pass
                    ws = sheet.worksheet("tunggakan")
                    ws.update(range_name='A1', values=[['id','nama_warga','periode','nominal','status']])
                    st.success("Header Tunggakan Dibuat!")

    # Login Logic
    if 'logged_in' not in st.session_state: st.session_state['logged_in'] = False
    if not st.session_state['logged_in']:
        st.title("🔐 Login Sistem")
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
    st.sidebar.title(f"Halo, {st.session_state['nama']}")
    menu = ["Dashboard", "Riwayat Transaksi", "Laporan Keuangan"]
    if st.session_state['role'] == 'admin':
        # Menambahkan menu khusus Tunggakan di tengah
        menu = ["Dashboard", "Input Transaksi", "Kelola Tunggakan", "Kelola Kategori", "Kelola Pengguna"] + menu
    
    choice = st.sidebar.radio("Menu", menu)
    if st.sidebar.button("Logout"): st.session_state.clear(); st.rerun()

    # --- 1. DASHBOARD ---
    if choice == "Dashboard":
        st.header("📊 Dashboard")
        df = get_data("transaksi")
        if not df.empty:
            df['tanggal'] = pd.to_datetime(df['tanggal'])
            df['nominal'] = pd.to_numeric(df['nominal'], errors='coerce').fillna(0)
            masuk = df[df['tipe']=='Pemasukan']['nominal'].sum()
            keluar = df[df['tipe']=='Pengeluaran']['nominal'].sum()
            
            # Info Tunggakan di Dashboard
            df_tunggakan = get_data("tunggakan")
            total_hutang = 0
            if not df_tunggakan.empty:
                df_tunggakan['nominal'] = pd.to_numeric(df_tunggakan['nominal'], errors='coerce').fillna(0)
                total_hutang = df_tunggakan[df_tunggakan['status']=='Belum Lunas']['nominal'].sum()

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Saldo Kas", f"Rp {masuk-keluar:,.0f}")
            c2.metric("Pemasukan", f"Rp {masuk:,.0f}")
            c3.metric("Pengeluaran", f"Rp {keluar:,.0f}")
            c4.metric("Total Tunggakan", f"Rp {total_hutang:,.0f}", delta_color="inverse")
            
            st.divider()
            df['bulan'] = df['tanggal'].dt.strftime('%Y-%m')
            chart = df.groupby(['bulan','tipe'])['nominal'].sum().unstack().fillna(0)
            if 'Pemasukan' not in chart.columns: chart['Pemasukan']=0
            if 'Pengeluaran' not in chart.columns: chart['Pengeluaran']=0
            st.bar_chart(chart[['Pemasukan','Pengeluaran']], color=["#4CAF50", "#FF4B4B"])
        else: st.info("Data Kosong")

    # --- 2. INPUT TRANSAKSI ---
    elif choice == "Input Transaksi":
        st.header("📝 Input Kas (Masuk/Keluar)")
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

    # --- 3. KELOLA TUNGGAKAN (FITUR BARU) ---
    elif choice == "Kelola Tunggakan":
        st.header("❗ Kelola Tunggakan & Iuran Warga")
        
        # Tab Navigasi
        tab1, tab2, tab3 = st.tabs(["➕ Tambah Data", "📝 Daftar & Edit Status", "🖨️ Laporan Tunggakan"])
        
        # TAB 1: CREATE
        with tab1:
            st.subheader("Catat Warga yang Belum Bayar")
            with st.form("add_tunggakan"):
                col_a, col_b = st.columns(2)
                nama = col_a.text_input("Nama Warga")
                periode = col_b.text_input("Periode (Misal: Januari 2024)")
                nominal_tagihan = st.number_input("Nominal Tagihan (Rp)", min_value=0, step=5000)
                status_awal = st.selectbox("Status Awal", ["Belum Lunas", "Lunas"])
                
                if st.form_submit_button("Simpan Data Tunggakan"):
                    if nama and periode:
                        uid = str(uuid.uuid4())[:8]
                        add_row("tunggakan", [uid, nama, periode, nominal_tagihan, status_awal])
                        st.success(f"Data tagihan untuk {nama} berhasil disimpan.")
                    else:
                        st.warning("Nama dan Periode wajib diisi.")

        # TAB 2: READ & UPDATE & DELETE
        with tab2:
            st.subheader("Daftar Tagihan/Tunggakan")
            df_t = get_data("tunggakan")
            
            if not df_t.empty:
                # CRUD UPDATE: Pakai Data Editor
                st.info("Anda bisa mengubah status 'Belum Lunas' menjadi 'Lunas' langsung di tabel ini.")
                
                edited_df = st.data_editor(
                    df_t,
                    column_config={
                        "id": st.column_config.TextColumn(disabled=True),
                        "status": st.column_config.SelectboxColumn(
                            "Status Pembayaran",
                            options=["Belum Lunas", "Lunas"],
                            required=True
                        ),
                        "nominal": st.column_config.NumberColumn(format="Rp %d")
                    },
                    hide_index=True,
                    key="editor_tunggakan"
                )
                
                col_btn1, col_btn2 = st.columns(2)
                
                # Tombol Simpan Perubahan (UPDATE)
                if col_btn1.button("💾 Simpan Perubahan Status"):
                    update_status_tunggakan(edited_df)
                    st.success("Status berhasil diperbarui ke Database!")
                    st.rerun()

                # Tombol Hapus (DELETE)
                with col_btn2:
                    with st.expander("Hapus Data Tunggakan"):
                        list_del = df_t['nama_warga'] + " - " + df_t['periode'] + " (ID: " + df_t['id'] + ")"
                        pilih_del = st.selectbox("Pilih data untuk dihapus", list_del)
                        if st.button("Hapus Permanen"):
                            id_del = pilih_del.split("(ID: ")[1].replace(")", "")
                            delete_tunggakan(id_del)
                            st.success("Data dihapus.")
                            st.rerun()
            else:
                st.info("Belum ada data tunggakan.")

        # TAB 3: REPORT (PDF)
        with tab3:
            st.subheader("Download Laporan")
            filter_status = st.selectbox("Filter Laporan", ["Semua", "Hanya Belum Lunas", "Hanya Lunas"])
            
            df_print = get_data("tunggakan")
            if not df_print.empty:
                if filter_status == "Hanya Belum Lunas":
                    df_print = df_print[df_print['status'] == 'Belum Lunas']
                elif filter_status == "Hanya Lunas":
                    df_print = df_print[df_print['status'] == 'Lunas']
                
                st.dataframe(df_print)
                
                if st.button("Generate PDF Tunggakan"):
                    pdf_bytes = create_pdf_tunggakan(df_print)
                    st.download_button("⬇️ Download PDF", pdf_bytes, "laporan_tunggakan.pdf", "application/pdf")

    # --- 4. RIWAYAT KAS (EXISTING) ---
    elif choice == "Riwayat Transaksi":
        st.header("🗂️ Riwayat Kas")
        df = get_data("transaksi")
        st.dataframe(df)
        if st.session_state['role']=='admin':
            with st.expander("Hapus Data Kas"):
                del_id = st.text_input("ID Transaksi")
                if st.button("Hapus"):
                    df_new = df[df['id']!=del_id]
                    save_all_data("transaksi", df_new)
                    st.success("Dihapus"); st.rerun()

    # --- 5. LAPORAN KAS ---
    elif choice == "Laporan Keuangan":
        st.header("Laporan Keuangan (Kas)")
        df = get_data("transaksi")
        if not df.empty:
            pdf = create_pdf_laporan(df)
            st.download_button("Download PDF Kas", pdf, "laporan_kas.pdf")

    # --- MENU LAINNYA ---
    elif choice == "Kelola Kategori":
        st.header("Edit Kategori")
        df = get_data("kategori")
        edited = st.data_editor(df, num_rows="dynamic", hide_index=True)
        if st.button("Simpan"): save_all_data("kategori", edited); st.success("Disimpan!"); st.rerun()

    elif choice == "Kelola Pengguna":
        st.header("User Management")
        with st.form("u"):
            u=st.text_input("User"); p=st.text_input("Pass", type='password'); r=st.selectbox("Role",["warga","admin"])
            if st.form_submit_button("Add"): add_row("users",[u,hash_pass(p),r,u]); st.success("Ok")
        st.dataframe(get_data("users"))

if __name__ == '__main__':
    main()
