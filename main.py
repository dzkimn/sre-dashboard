
from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
import uvicorn
import os
import requests
import pandas as pd
import io
from datetime import datetime
from pydantic import BaseModel
import google.generativeai as genai

app = FastAPI(title="SRE Management Dashboard")

os.makedirs("templates", exist_ok=True)
os.makedirs("static", exist_ok=True)

templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

# Setup Gemini AI
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "AIzaSyBCIf9gn9pGv3fkIk10EeTMwb9I5jiu9S4")
if GEMINI_API_KEY and GEMINI_API_KEY != "MASUKKAN_API_KEY_ANDA_DISINI":
    genai.configure(api_key=GEMINI_API_KEY)

APPS_SCRIPT_URL = os.environ.get("APPS_SCRIPT_URL", "https://script.google.com/macros/s/AKfycby7a1WPGQzToLQ55Iz2YYw2dNm1TAhH4X0VVHlC2U3wQ9vqy7YIrLbSjtRn_k-UHf4M/exec")
GOOGLE_SHEET_URL = os.environ.get("GOOGLE_SHEET_URL", "https://docs.google.com/spreadsheets/d/1j1HHrH1AUCfaZe39uTtCyYMeeT0UjqpeNn4zBMk5m0E/edit?usp=sharing")

# =============================================
# PYDANTIC MODELS
# =============================================
class ProposalRequest(BaseModel):
    kompetisi: str
    tujuan_konteks: str
    tim: str
    anggaran: str

class ReportData(BaseModel):
    program: str
    pic: str
    tanggal: str
    status_kompetisi: str  # 'Selesai', 'Berlangsung', 'Persiapan'
    persen_persiapan: int
    persen_berlangsung: int
    persen_selesai: int
    target_minggu: str
    realisasi: str
    kendala: str
    rencana: str

# =============================================
# HELPER: Baca Database
# =============================================
def read_db():
    if not APPS_SCRIPT_URL:
        return pd.DataFrame()
    try:
        response = requests.get(APPS_SCRIPT_URL, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if data and isinstance(data, list):
                return pd.DataFrame(data)
    except Exception as e:
        print("Error fetching from Google Sheets:", e)
    return pd.DataFrame()

# =============================================
# ROUTES HALAMAN
# =============================================
@app.get("/")
async def dashboard(request: Request):
    df = read_db()
    competitions = []
    notifications = []
    stats = {"total": 0, "selesai": 0, "berlangsung": 0, "persiapan": 0}

    if not df.empty:
        # Konversi tanggal, abaikan error
        df['Tanggal Laporan'] = pd.to_datetime(df['Tanggal Laporan'], errors='coerce')
        df_sorted = df.sort_values(by='Tanggal Laporan', ascending=False)
        
        # Isi nilai kolom yang mungkin belum ada (agar tidak crash di template)
        for col in ['PIC', 'Status Kompetisi', 'Progres Persiapan (%)', 'Progres Berlangsung (%)', 'Progres Selesai (%)', 'Target Minggu Ini', 'Realisasi', 'Rencana Minggu Depan']:
            if col not in df_sorted.columns:
                df_sorted[col] = 'Berlangsung' if col == 'Status Kompetisi' else ('-' if col == 'PIC' else 0)
        
        competitions = df_sorted.head(10).to_dict('records')

        stats["total"] = len(df)
        try:
            if 'Status Kompetisi' in df.columns:
                stats["selesai"]     = int((df['Status Kompetisi'] == 'Selesai').sum())
                stats["berlangsung"] = int((df['Status Kompetisi'] == 'Berlangsung').sum())
                stats["persiapan"]   = int((df['Status Kompetisi'] == 'Persiapan').sum())
        except Exception:
            pass

        today = datetime.now()
        for _, row in df.iterrows():
            try:
                tgl = pd.to_datetime(row['Tanggal Laporan'], errors='coerce')
                if pd.notna(tgl):
                    diff = (tgl - today).days
                    if 0 <= diff <= 7:
                        notifications.append({
                            "title": "⚠️ Deadline Mendekat!",
                            "msg": f"{row.get('Program', '?')} - {row.get('PIC', '-')} | {diff} hari lagi",
                            "type": "warning"
                        })
            except Exception:
                pass

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "title": "SRE Dashboard",
        "competitions": competitions,
        "stats": stats,
        "notifications": notifications
    })

@app.get("/reporting")
async def reporting(request: Request):
    return templates.TemplateResponse("reporting.html", {"request": request, "title": "Smart Reporting"})

@app.get("/proposal")
async def proposal(request: Request):
    return templates.TemplateResponse("proposal.html", {"request": request, "title": "AI Proposal Generator"})

@app.get("/surattugas")
async def surattugas(request: Request):
    return templates.TemplateResponse("surattugas.html", {"request": request, "title": "Surat Tugas Generator"})

# =============================================
# API: SUBMIT LAPORAN (SESUAI SOP)
# =============================================
@app.post("/api/submit_report")
async def submit_report(data: ReportData):
    if not APPS_SCRIPT_URL:
        return {"status": "error", "message": "APPS_SCRIPT_URL belum diatur. Tidak bisa menyimpan ke Google Sheets."}
        
    new_row = {
        "Timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "Program": data.program,
        "PIC": data.pic,
        "Tanggal Laporan": data.tanggal,
        "Status Kompetisi": data.status_kompetisi,
        "Progres Persiapan (%)": data.persen_persiapan,
        "Progres Berlangsung (%)": data.persen_berlangsung,
        "Progres Selesai (%)": data.persen_selesai,
        "Target Minggu Ini": data.target_minggu,
        "Realisasi": data.realisasi,
        "Kendala": data.kendala,
        "Rencana Minggu Depan": data.rencana,
    }
    
    try:
        response = requests.post(APPS_SCRIPT_URL, json=new_row, timeout=10)
        if response.status_code == 200:
            return {"status": "success", "message": "Laporan berhasil disimpan ke Google Spreadsheet!"}
        else:
            return {"status": "error", "message": f"Gagal menyimpan. Status: {response.status_code}"}
    except Exception as e:
        return {"status": "error", "message": f"Terjadi kesalahan: {str(e)}"}

# =============================================
# API: EXPORT LAPORAN (DATA ASLI DARI DATABASE)
# =============================================
@app.get("/api/export_laporan")
async def export_laporan():
    """Redirect langsung ke Google Spreadsheet."""
    return RedirectResponse(url=GOOGLE_SHEET_URL)

# =============================================
# API: EXPORT LAPORAN FORMAT SOP (HTML Print)
# =============================================
@app.get("/api/export_laporan_sop")
async def export_laporan_sop():
    """Generate halaman HTML yang siap di-print/PDF sesuai format SOP weekly report."""
    df = read_db()
    rows_html = ""
    if df.empty:
        rows_html = "<tr><td colspan='8' style='text-align:center;padding:20px;color:#999;'>Belum ada data laporan.</td></tr>"
    else:
        df['Tanggal Laporan'] = pd.to_datetime(df['Tanggal Laporan'], errors='coerce')
        df = df.sort_values(by='Tanggal Laporan', ascending=False)
        for i, (_, row) in enumerate(df.iterrows(), 1):
            p_persiapan   = row.get('Progres Persiapan (%)', 0)
            p_berlangsung = row.get('Progres Berlangsung (%)', 0)
            p_selesai     = row.get('Progres Selesai (%)', 0)
            rows_html += f"""
            <tr>
                <td>{i}</td>
                <td><b>{row.get('Program','-')}</b></td>
                <td>{row.get('PIC','-')}</td>
                <td>{str(row.get('Tanggal Laporan','-'))[:10]}</td>
                <td>
                    <div style='font-size:11px;'>Persiapan: <b>{p_persiapan}%</b></div>
                    <div style='font-size:11px;'>Berlangsung: <b>{p_berlangsung}%</b></div>
                    <div style='font-size:11px;color:green;'>Selesai: <b>{p_selesai}%</b></div>
                </td>
                <td style='font-size:11px;'>{row.get('Target Minggu Ini','-')}</td>
                <td style='font-size:11px;'>{row.get('Realisasi','-')}</td>
                <td style='font-size:11px;'>{row.get('Kendala','-')}</td>
                <td style='font-size:11px;'>{row.get('Rencana Minggu Depan','-')}</td>
            </tr>"""

    html = f"""<!DOCTYPE html><html lang="id"><head><meta charset="UTF-8">
    <title>Weekly Report - SRE Divisi Competition</title>
    <style>
        body {{ font-family: 'Times New Roman', serif; margin: 20mm; font-size: 12pt; }}
        h2 {{ text-align: center; text-transform: uppercase; }}
        h3 {{ text-align: center; }}
        .kop {{ display: flex; align-items: center; border-bottom: 4px double black; padding-bottom: 10px; margin-bottom: 20px; }}
        .kop-text {{ flex: 1; text-align: center; }}
        .kop-text h2 {{ margin: 0; font-size: 14pt; }}
        .kop-text p {{ margin: 2px 0; font-size: 9pt; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 15px; font-size: 10pt; }}
        th, td {{ border: 1px solid black; padding: 6px 8px; vertical-align: top; }}
        th {{ background-color: #d4edda; text-align: center; }}
        .title-row {{ text-align: center; margin: 20px 0 5px 0; font-weight: bold; font-size: 13pt; text-decoration: underline; }}
        .subtitle {{ text-align: center; font-size: 11pt; margin-bottom: 10px; }}
        .footer {{ margin-top: 40px; display: flex; justify-content: flex-end; }}
        @media print {{ body {{ margin: 15mm; }} button {{ display: none; }} }}
    </style>
    </head><body>
    <div class="kop">
        <div class="kop-text">
            <h2>Society of Renewable Energy</h2>
            <h2>Universitas Telkom</h2>
            <p>Sekretariat: Jl. Telekomunikasi. 1, Terusan Buahbatu Bandung 40257, Jawa Barat</p>
            <p>Email: telkomuniversity@sre.co.id</p>
        </div>
    </div>
    <div class="title-row">LAPORAN MINGGUAN DIVISI EVENT & COMPETITION</div>
    <div class="subtitle">Society of Renewable Energy (SRE) Telkom University</div>
    <p style="text-align:right; font-size:10pt;">Dicetak pada: {datetime.now().strftime('%d %B %Y, %H:%M')}</p>
    <table>
        <thead>
            <tr>
                <th style="width:30px;">No</th>
                <th>Nama Program / Kompetisi</th>
                <th>PIC</th>
                <th>Tgl Laporan</th>
                <th>Progres</th>
                <th>Target Minggu Ini</th>
                <th>Realisasi</th>
                <th>Kendala</th>
                <th>Rencana Depan</th>
            </tr>
        </thead>
        <tbody>{rows_html}</tbody>
    </table>
    <div class="footer">
        <div style="text-align:center;">
            <p>Bandung, {datetime.now().strftime('%d %B %Y')}</p>
            <p style="font-weight:bold; margin-top:5px;">Director Event & Competition</p>
            <br><br><br>
            <p style="text-decoration:underline; font-weight:bold;">______________________</p>
            <p>NIM: ___________________</p>
        </div>
    </div>
    <div style="text-align:center; margin-top:20px;">
        <button onclick="window.print()" style="padding:10px 30px; background:#16a34a; color:white; border:none; border-radius:8px; font-size:14px; cursor:pointer;">🖨️ Print / Save as PDF</button>
        <button onclick="window.close()" style="padding:10px 30px; background:#64748b; color:white; border:none; border-radius:8px; font-size:14px; cursor:pointer; margin-left:10px;">✕ Tutup</button>
    </div>
    </body></html>"""
    return HTMLResponse(content=html)

# =============================================
# API: GENERATE PROPOSAL (GEMINI AI)
# =============================================
@app.post("/api/generate_proposal")
async def generate_proposal_api(req: ProposalRequest):
    if not GEMINI_API_KEY or GEMINI_API_KEY == "MASUKKAN_API_KEY_ANDA_DISINI":
        return {"status": "error", "message": "GEMINI_API_KEY belum dikonfigurasi."}
    try:
        model = genai.GenerativeModel('gemini-3.1-flash-lite')
        prompt = f"""
        Buatkan bagian Latar Belakang dan Tujuan Kegiatan untuk proposal kegiatan kompetisi mahasiswa.
        Organisasi: Society of Renewable Energy (SRE) Telkom University.
        Kompetisi: {req.kompetisi}
        Konteks Tujuan Khusus: {req.tujuan_konteks}
        Format output: JSON murni dengan 2 key: "latar_belakang" dan "tujuan" (tujuan gunakan HTML <ul><li>).
        JANGAN tambahkan markdown, hanya JSON.
        """
        response = model.generate_content(prompt)
        import json
        text_res = response.text.replace("```json", "").replace("```", "").strip()
        data = json.loads(text_res)
        return {"status": "success", "latar_belakang": data.get("latar_belakang", ""), "tujuan": data.get("tujuan", "")}
    except Exception as e:
        return {"status": "error", "message": str(e)}

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
