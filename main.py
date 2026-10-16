import os
import shutil
import sqlite3
import tempfile
import threading
import inspect
import http.server
import socketserver
import urllib.parse
import webbrowser
from datetime import datetime
import flet as ft
from fpdf import FPDF

try:
    import tkinter as tk
    from tkinter import filedialog
    TKINTER_VAR = True
except ImportError:
    TKINTER_VAR = False

VERI_DIZINI = os.environ.get("FLET_APP_STORAGE_DATA")
if not VERI_DIZINI:
    if os.name == "nt":
        VERI_DIZINI = os.path.abspath(".")
    else:
        VERI_DIZINI = tempfile.gettempdir()

DB_FILE = os.path.join(VERI_DIZINI, "teklifcepte.db")
LOGO_KLASORU = os.path.join(VERI_DIZINI, "logolar")
ARSIV_KLASORU = os.path.join(VERI_DIZINI, "teklifler_arsiv")

PDF_PORT = [0]


def pdf_sunucu_baslat():
    if PDF_PORT[0] != 0:
        return PDF_PORT[0]

    class MobilPDFHandler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            try:
                temiz_yol = urllib.parse.unquote(self.path.lstrip("/"))
                dosya_adi = os.path.basename(temiz_yol)
                tam_yol = os.path.join(ARSIV_KLASORU, dosya_adi)

                if not os.path.exists(tam_yol):
                    self.send_response(404)
                    self.end_headers()
                    return

                with open(tam_yol, "rb") as f:
                    pdf_bytes = f.read()

                self.send_response(200)
                self.send_header("Content-Type", "application/pdf")
                self.send_header("Content-Disposition", f'attachment; filename="{dosya_adi}"')
                self.send_header("Content-Length", str(len(pdf_bytes)))
                self.end_headers()
                self.wfile.write(pdf_bytes)
            except Exception:
                pass

        def log_message(self, format, *args):
            pass

    try:
        httpd = socketserver.TCPServer(("127.0.0.1", 0), MobilPDFHandler)
        PDF_PORT[0] = httpd.server_address[1]
        t = threading.Thread(target=httpd.serve_forever, daemon=True)
        t.start()
    except Exception:
        pass
    return PDF_PORT[0]


def init_db():
    for klasor in [VERI_DIZINI, LOGO_KLASORU, ARSIV_KLASORU]:
        if not os.path.exists(klasor):
            os.makedirs(klasor, exist_ok=True)

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS ayarlar (
        id INTEGER PRIMARY KEY, firma_adi TEXT, firma_tel TEXT, firma_iban TEXT, pro_mu INTEGER, kalan_hak INTEGER
    )""")

    c.execute("PRAGMA table_info(ayarlar)")
    sutunlar = [s[1] for s in c.fetchall()]
    if "logo_yolu" not in sutunlar:
        c.execute("ALTER TABLE ayarlar ADD COLUMN logo_yolu TEXT DEFAULT ''")
    if "gecerlilik" not in sutunlar:
        c.execute("ALTER TABLE ayarlar ADD COLUMN gecerlilik TEXT DEFAULT '30 Gün'")

    c.execute("UPDATE ayarlar SET gecerlilik='30 Gün' WHERE gecerlilik='15 Gün' OR gecerlilik IS NULL OR gecerlilik=''")

    c.execute("""CREATE TABLE IF NOT EXISTS hazir_kalemler (
        id INTEGER PRIMARY KEY AUTOINCREMENT, ad TEXT, fiyat REAL
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS cariler (
        id INTEGER PRIMARY KEY AUTOINCREMENT, musteri TEXT, tel TEXT, toplam_borc REAL, odenen REAL, tarih TEXT
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS gecmis_teklifler (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        musteri TEXT,
        tel TEXT,
        toplam REAL,
        tarih TEXT,
        dosya_yolu TEXT,
        kalem_ozeti TEXT
    )""")

    c.execute("SELECT COUNT(*) FROM ayarlar")
    if c.fetchone()[0] == 0:
        c.execute(
            "INSERT INTO ayarlar (id, firma_adi, firma_tel, firma_iban, pro_mu, kalan_hak, logo_yolu, gecerlilik) "
            "VALUES (1, 'Kurum / Firma Adınız', '0500 000 00 00', 'TR00 0000 0000 0000 0000 00', 0, 5, '', '30 Gün')"
        )
        ornekler = [("Örnek Hizmet / İşçilik", 1000.0), ("Malzeme Bedeli", 500.0)]
        c.executemany("INSERT INTO hazir_kalemler (ad, fiyat) VALUES (?, ?)", ornekler)

    conn.commit()
    conn.close()


def cihazdan_logo_yukle():
    if not TKINTER_VAR:
        return None
    root = tk.Tk()
    root.withdraw()
    root.wm_attributes("-topmost", 1)
    secilen_dosya = filedialog.askopenfilename(
        parent=root,
        title="PDF Sol Üst Köşede Çıkacak Kurum Logosunu Seçin",
        filetypes=[("Resim Dosyaları", "*.png *.jpg *.jpeg"), ("Tüm Dosyalar", "*.*")]
    )
    root.destroy()

    if secilen_dosya and os.path.exists(secilen_dosya):
        uzanti = os.path.splitext(secilen_dosya)[1].lower()
        zaman_damgasi = int(datetime.now().timestamp())
        hedef_yol = os.path.abspath(os.path.join(LOGO_KLASORU, f"logo_{zaman_damgasi}{uzanti}"))
        shutil.copy2(secilen_dosya, hedef_yol)
        return hedef_yol
    return None


def tr_temizle(metin):
    harita = str.maketrans("ğĞıİöÖüÜşŞçÇ", "gGiIoOuUsScC")
    return str(metin).translate(harita)


def _pdf_ciz(ayar, musteri_adi, kalemler, ara_toplam, iskonto, kdv_oran, kdv_tutar, genel_toplam, gecerlilik_suresi, font_kullan=True):
    pdf = FPDF()
    pdf.add_page()

    baz_dizin = os.path.dirname(os.path.abspath(__file__))
    yerel_font = os.path.join(baz_dizin, "font.ttf")
    yerel_bold = os.path.join(baz_dizin, "font_bold.ttf")
    win_font = "C:/Windows/Fonts/arial.ttf"
    win_bold = "C:/Windows/Fonts/arialbd.ttf"

    tr_destekli = False
    font_name = "Helvetica"

    if font_kullan:
        try:
            if os.path.exists(yerel_font):
                pdf.add_font("TRFont", "", yerel_font)
                pdf.add_font("TRFont", "B", yerel_bold if os.path.exists(yerel_bold) else yerel_font)
                font_name = "TRFont"
                tr_destekli = True
            elif os.path.exists(win_font):
                pdf.add_font("TRFont", "", win_font)
                pdf.add_font("TRFont", "B", win_bold if os.path.exists(win_bold) else win_font)
                font_name = "TRFont"
                tr_destekli = True
        except Exception:
            font_name = "Helvetica"
            tr_destekli = False

    def yaz(m):
        return str(m) if tr_destekli else tr_temizle(m)

    logo_yolu = ayar.get("logo_yolu", "").strip()
    logo_basildi = False
    if logo_yolu and os.path.exists(logo_yolu):
        try:
            pdf.image(logo_yolu, x=10, y=10, h=20)
            logo_basildi = True
        except Exception:
            logo_basildi = False

    pdf.set_xy(110, 12)
    pdf.set_font(font_name, "B", 11)
    pdf.set_text_color(37, 99, 235)
    pdf.cell(90, 6, yaz("RESMİ FİYAT TEKLİFİ"), align="R")

    pdf.set_xy(110, 18)
    pdf.set_font(font_name, "", 10)
    pdf.set_text_color(80, 80, 80)
    pdf.cell(90, 6, yaz(f"Tarih: {datetime.now().strftime('%d.%m.%Y')}"), align="R")

    firma_y = 33 if logo_basildi else 22
    pdf.set_xy(10, firma_y)
    pdf.set_text_color(30, 58, 138)
    pdf.set_font(font_name, "B", 16)
    f_adi_metni = ayar["firma_adi"].upper() if ayar["firma_adi"] else "FIRMA ADI"
    pdf.cell(0, 8, yaz(f_adi_metni), new_x="LMARGIN", new_y="NEXT", align="C")

    pdf.set_xy(10, firma_y + 8)
    pdf.set_text_color(70, 70, 70)
    pdf.set_font(font_name, "", 10)
    pdf.cell(0, 6, yaz(f"İletişim / Tel: {ayar['firma_tel']}"), new_x="LMARGIN", new_y="NEXT", align="C")

    cizgi_y = firma_y + 16
    pdf.set_draw_color(200, 200, 200)
    pdf.line(10, cizgi_y, 200, cizgi_y)

    pdf.set_xy(10, cizgi_y + 4)
    pdf.set_fill_color(241, 245
