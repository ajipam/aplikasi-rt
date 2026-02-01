import streamlit as st
import pandas as pd
from datetime import datetime, date
import hashlib
from fpdf import FPDF
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import uuid
import random
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

# --- PDF GENERATOR (LAPORAN BIASA) ---
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
