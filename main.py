import os
import sys
import json
import random
import shutil
import sqlite3
import tempfile
import threading
import textwrap
import inspect
import http.server
import socketserver
import urllib.parse
import webbrowser
from datetime import datetime
import flet as ft

try:
    from fpdf import FPDF
    FPDF_VAR = True
except ImportError:
    FPDF_VAR = False

try:
    import tkinter as tk
    from tkinter import filedialog
    TKINTER_VAR = True
except ImportError:
    TKINTER_VAR = False

# =====================================================================
# --- SATIŞ, FİYAT VE WHATSAPP AYARLARI (KENDİ NUMARANI BURAYA YAZ) ---
# =====================================================================
PRO_FIYAT_METNI = "499 TL (Tek Seferlik / Sınırsız Lisans)"
SATIS_WHATSAPP_NO = "905000000000"  # Kendi WhatsApp numaranı başında 90 ile yaz
PRO_ANA_SIFRE = "PRO2026"           # Senin genel yönetici şifren

VERI_DIZINI = os.environ.get("FLET_APP_STORAGE_DATA")
if not VERI_DIZINI:
    if os.name == "nt":
        if getattr(sys, "frozen", False):
            VERI_DIZINI = os.path.dirname(sys.executable)
        else:
            VERI_DIZINI = os.path.dirname(os.path.abspath(__file__))
    else:
        VERI_DIZINI = tempfile.gettempdir()

DB_FILE = os.path.join(VERI_DIZINI, "teklifcepte.db")
LOGO_KLASORU = os.path.join(VERI_DIZINI, "logolar")
ARSIV_KLASORU = os.path.join(VERI_DIZINI, "teklifler_arsiv")

PDF_PORT = [0]


def cihaza_ozel_sifre_uret(cihaz_kodu):
    temiz = "".join(filter(str.isdigit, str(cihaz_kodu))) or "10000"
    sayi = int(temiz)
    ozel_kod = ((sayi * 73) + 1923) % 90000 + 10000
    return f"TC-{ozel_kod}"


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
    if "firma_adres" not in sutunlar:
        c.execute("ALTER TABLE ayarlar ADD COLUMN firma_adres TEXT DEFAULT ''")
    if "cihaz_kodu" not in sutunlar:
        c.execute("ALTER TABLE ayarlar ADD COLUMN cihaz_kodu TEXT DEFAULT ''")

    c.execute("UPDATE ayarlar SET gecerlilik='30 Gün' WHERE gecerlilik='15 Gün' OR gecerlilik IS NULL OR gecerlilik=''")

    c.execute("""CREATE TABLE IF NOT EXISTS hazir_kalemler (
        id INTEGER PRIMARY KEY AUTOINCREMENT, ad TEXT, fiyat REAL
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS musteriler (
        id INTEGER PRIMARY KEY AUTOINCREMENT, ad TEXT, tel TEXT, adres TEXT
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

    c.execute("PRAGMA table_info(gecmis_teklifler)")
    g_sutunlar = [s[1] for s in c.fetchall()]
    if "durum" not in g_sutunlar:
        c.execute("ALTER TABLE gecmis_teklifler ADD COLUMN durum TEXT DEFAULT 'Bekliyor'")
    if "kalem_json" not in g_sutunlar:
        c.execute("ALTER TABLE gecmis_teklifler ADD COLUMN kalem_json TEXT DEFAULT ''")
    if "para_birimi" not in g_sutunlar:
        c.execute("ALTER TABLE gecmis_teklifler ADD COLUMN para_birimi TEXT DEFAULT 'TL'")
    if "musteri_adres" not in g_sutunlar:
        c.execute("ALTER TABLE gecmis_teklifler ADD COLUMN musteri_adres TEXT DEFAULT ''")

    rastgele_cihaz = str(random.randint(10000, 99999))
    c.execute("SELECT COUNT(*) FROM ayarlar")
    if c.fetchone()[0] == 0:
        c.execute(
            "INSERT INTO ayarlar (id, firma_adi, firma_tel, firma_iban, pro_mu, kalan_hak, logo_yolu, gecerlilik, firma_adres, cihaz_kodu) "
            "VALUES (1, 'Kurum / Firma Adınız', '0500 000 00 00', 'TR00 0000 0000 0000 0000 00', 0, 5, '', '30 Gün', '', ?)",
            (rastgele_cihaz,)
        )
        ornekler = [("Örnek Hizmet / İşçilik", 1000.0), ("Malzeme Bedeli", 500.0)]
        c.executemany("INSERT INTO hazir_kalemler (ad, fiyat) VALUES (?, ?)", ornekler)
    else:
        c.execute("SELECT cihaz_kodu FROM ayarlar WHERE id=1")
        mevcut_kod = c.fetchone()[0]
        if not mevcut_kod:
            c.execute("UPDATE ayarlar SET cihaz_kodu=? WHERE id=1", (rastgele_cihaz,))

    conn.commit()
    conn.close()


def musteri_rehbere_kaydet(ad, tel="", adres=""):
    temiz_ad = (ad or "").strip()
    if not temiz_ad or temiz_ad in ["Sayın Müşterimiz", "Müşterimiz", "İsimsiz Müşteri"]:
        return False
    temiz_tel = (tel or "").strip()
    temiz_adres = (adres or "").strip()

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT id, tel, adres FROM musteriler WHERE LOWER(ad)=LOWER(?)", (temiz_ad,))
    mevcut = c.fetchone()
    if mevcut:
        yeni_tel = temiz_tel if temiz_tel else (mevcut[1] or "")
        yeni_adres = temiz_adres if temiz_adres else (mevcut[2] or "")
        c.execute("UPDATE musteriler SET ad=?, tel=?, adres=? WHERE id=?", (temiz_ad, yeni_tel, yeni_adres, mevcut[0]))
    else:
        c.execute("INSERT INTO musteriler (ad, tel, adres) VALUES (?, ?, ?)", (temiz_ad, temiz_tel, temiz_adres))
    conn.commit()
    conn.close()
    return True


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


def yedek_pdf_uret(dosya_adi, ayar, musteri_adi, kalemler, ara_toplam, iskonto, kdv_oran, kdv_tutar, genel_toplam, gecerlilik_suresi, notlar="", pb="TL", musteri_adres=""):
    satirlar = [
        f"RESMI FIYAT TEKLIFI - Tarih: {datetime.now().strftime('%d.%m.%Y')}",
    ]
    uzun_firma = tr_temizle(ayar["firma_adi"] or "FIRMA ADI").upper()
    for parca in textwrap.wrap(uzun_firma, width=55) or ["FIRMA ADI"]:
        satirlar.append(parca.center(60))
    satirlar.append(f"Tel: {tr_temizle(ayar['firma_tel'])}".center(60))
    if ayar.get("firma_adres"):
        for a_parca in textwrap.wrap(f"Adres: {tr_temizle(ayar['firma_adres'])}", width=58):
            satirlar.append(a_parca.center(60))
    satirlar.extend([
        "------------------------------------------------------------",
        f"SAYIN: {tr_temizle(musteri_adi)}",
    ])
    if musteri_adres:
        satirlar.append(f"Musteri Adres/Bilgi: {tr_temizle(musteri_adres)}")
    satirlar.append("------------------------------------------------------------")
    for i, k in enumerate(kalemler):
        birim = tr_temizle(k.get("birim", "Adet"))
        satirlar.append(f"{i+1}. {tr_temizle(k['ad'])} | {k['miktar']:g} {birim} x {k['fiyat']:,.2f} {pb} = {k['toplam']:,.2f} {pb}")
    satirlar.extend([
        "------------------------------------------------------------",
        f"Ara Toplam: {ara_toplam:,.2f} {pb}",
        f"Iskonto: -{iskonto:,.2f} {pb}",
        f"KDV (%{kdv_oran}): {kdv_tutar:,.2f} {pb}",
        f"GENEL TOPLAM: {genel_toplam:,.2f} {pb}",
        "------------------------------------------------------------",
        f"IBAN: {tr_temizle(ayar['firma_iban'])}",
        f"Teklif Gecerlilik Suresi: {tr_temizle(gecerlilik_suresi)}",
    ])
    if notlar:
        satirlar.append(f"Not / Odeme Sarti: {tr_temizle(notlar)}")
    satirlar.append("YETKILI KASE / IMZA")

    icerik_komutlari = ["BT", "/F1 11 Tf", "50 780 Td", "16 TL"]
    for s in satirlar:
        temiz_s = s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        icerik_komutlari.append(f"({temiz_s}) Tj T*")
    icerik_komutlari.append("ET")
    stream_data = "\n".join(icerik_komutlari).encode("latin-1", errors="ignore")

    nesneler = [
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n",
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n",
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>\nendobj\n",
        f"4 0 obj\n<< /Length {len(stream_data)} >>\nstream\n".encode("ascii") + stream_data + b"\nendstream\nendobj\n",
        b"5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n"
    ]

    with open(dosya_adi, "wb") as f:
        f.write(b"%PDF-1.4\n")
        konumlar = []
        for n in nesneler:
            konumlar.append(f.tell())
            f.write(n)
        xref_konum = f.tell()
        f.write(f"xref\n0 {len(nesneler)+1}\n0000000000 65535 f \n".encode("ascii"))
        for k in konumlar:
            f.write(f"{k:010d} 00000 n \n".encode("ascii"))
        f.write(f"trailer\n<< /Size {len(nesneler)+1} /Root 1 0 R >>\nstartxref\n{xref_konum}\n%%EOF".encode("ascii"))
    return os.path.abspath(dosya_adi)


def _pdf_ciz(ayar, musteri_adi, kalemler, ara_toplam, iskonto, kdv_oran, kdv_tutar, genel_toplam, gecerlilik_suresi, notlar="", pb="TL", musteri_adres="", font_kullan=True):
    temiz_isim = "".join(c if c.isalnum() else "_" for c in tr_temizle(musteri_adi)) or "Musteri"
    zaman_eki = datetime.now().strftime("%Y%m%d_%H%M%S")
    dosya_adi = os.path.join(ARSIV_KLASORU, f"Teklif_{temiz_isim}_{zaman_eki}.pdf")

    if not FPDF_VAR:
        return yedek_pdf_uret(dosya_adi, ayar, musteri_adi, kalemler, ara_toplam, iskonto, kdv_oran, kdv_tutar, genel_toplam, gecerlilik_suresi, notlar, pb, musteri_adres)

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

    firma_y = 33 if logo_basildi else 24
    pdf.set_xy(10, firma_y)
    pdf.set_text_color(30, 58, 138)
    f_adi_metni = ayar["firma_adi"].upper() if ayar["firma_adi"] else "FIRMA ADI"
    baslik_punto = 13 if len(f_adi_metni) > 38 else 15
    pdf.set_font(font_name, "B", baslik_punto)
    pdf.multi_cell(190, 7, yaz(f_adi_metni), align="C")

    alt_bilgi = f"İletişim / Tel: {ayar['firma_tel']}"
    if ayar.get("firma_adres"):
        alt_bilgi += f" | {ayar['firma_adres']}"

    pdf.set_x(10)
    pdf.set_text_color(70, 70, 70)
    pdf.set_font(font_name, "", 10)
    pdf.multi_cell(190, 5.5, yaz(alt_bilgi), align="C")

    cizgi_y = pdf.get_y() + 3
    pdf.set_draw_color(200, 200, 200)
    pdf.line(10, cizgi_y, 200, cizgi_y)

    pdf.set_xy(10, cizgi_y + 4)
    pdf.set_fill_color(241, 245, 249)
    pdf.set_text_color(0, 0, 0)
    pdf.set_font(font_name, "B", 11)
    sayin_metni = f"  SAYIN: {musteri_adi}"
    if musteri_adres and musteri_adres.strip():
        sayin_metni += f"\n  Adres / Bilgi: {musteri_adres.strip()}"
    pdf.multi_cell(190, 6.5, yaz(sayin_metni), fill=True)
    pdf.ln(3)

    pdf.set_fill_color(30, 58, 138)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font(font_name, "B", 11)
    pdf.cell(90, 9, yaz(" Hizmet / Malzeme Açıklaması"), border=1, fill=True)
    pdf.cell(30, 9, yaz("Miktar"), border=1, align="C", fill=True)
    pdf.cell(35, 9, yaz("Birim Fiyat"), border=1, align="R", fill=True)
    pdf.cell(35, 9, yaz("Toplam"), border=1, new_x="LMARGIN", new_y="NEXT", align="R", fill=True)

    pdf.set_text_color(0, 0, 0)
    pdf.set_font(font_name, "", 10)
    for k in kalemler:
        birim = k.get("birim", "Adet")
        pdf.cell(90, 8, yaz(f" {k['ad']}"), border=1)
        pdf.cell(30, 8, yaz(f"{k['miktar']:g} {birim}"), border=1, align="C")
        pdf.cell(35, 8, yaz(f"{k['fiyat']:,.2f} {pb}"), border=1, align="R")
        pdf.cell(35, 8, yaz(f"{k['toplam']:,.2f} {pb}"), border=1, new_x="LMARGIN", new_y="NEXT", align="R")

    pdf.ln(3)
    pdf.set_font(font_name, "", 10)
    pdf.cell(155, 7, yaz("Ara Toplam:"), align="R")
    pdf.cell(35, 7, yaz(f"{ara_toplam:,.2f} {pb}"), border=1, new_x="LMARGIN", new_y="NEXT", align="R")

    if iskonto > 0:
        pdf.cell(155, 7, yaz("İskonto (İndirim):"), align="R")
        pdf.cell(35, 7, yaz(f"-{iskonto:,.2f} {pb}"), border=1, new_x="LMARGIN", new_y="NEXT", align="R")

    if kdv_oran > 0:
        pdf.cell(155, 7, yaz(f"KDV (%{kdv_oran}):"), align="R")
        pdf.cell(35, 7, yaz(f"{kdv_tutar:,.2f} {pb}"), border=1, new_x="LMARGIN", new_y="NEXT", align="R")

    pdf.set_font(font_name, "B", 12)
    pdf.cell(155, 10, yaz("GENEL TOPLAM:"), align="R")
    pdf.set_fill_color(220, 252, 231)
    pdf.cell(35, 10, yaz(f"{genel_toplam:,.2f} {pb}"), border=1, new_x="LMARGIN", new_y="NEXT", align="R", fill=True)

    if pdf.get_y() > 210:
        pdf.add_page()

    if notlar and notlar.strip():
        pdf.ln(4)
        pdf.set_x(10)
        pdf.set_fill_color(254, 249, 195)
        pdf.set_font(font_name, "B", 9.5)
        pdf.set_text_color(133, 77, 14)
        pdf.multi_cell(190, 6, yaz(f"  Not / Ödeme Şartları: {notlar.strip()}"), fill=True)

    pdf.ln(4)
    pdf.set_x(10)
    pdf.set_fill_color(241, 245, 249)
    pdf.set_font(font_name, "B", 10)
    pdf.set_text_color(30, 58, 138)
    pdf.cell(190, 8, yaz(f"  Ödeme İçin IBAN: {ayar['firma_iban']}"), new_x="LMARGIN", new_y="NEXT", fill=True)

    alt_y = pdf.get_y() + 6
    pdf.set_xy(10, alt_y)
    pdf.set_font(font_name, "B", 10)
    pdf.set_text_color(180, 83, 9)
    pdf.cell(112, 6, yaz(f"Teklif Geçerlilik Süresi: {gecerlilik_suresi}"), new_x="LMARGIN", new_y="NEXT")

    kutu_x = 130
    kutu_w = 70
    kutu_h = 36
    pdf.set_draw_color(160, 175, 195)
    pdf.set_fill_color(250, 251, 253)
    pdf.rect(kutu_x, alt_y, kutu_w, kutu_h, style="DF")

    pdf.set_xy(kutu_x, alt_y + 2)
    pdf.set_font(font_name, "B", 10)
    pdf.set_text_color(30, 58, 138)
    pdf.cell(kutu_w, 6, yaz("YETKİLİ KAŞE / İMZA"), align="C")

    pdf.set_xy(kutu_x + 2, alt_y + 8)
    pdf.set_font(font_name, "", 7.5)
    pdf.set_text_color(90, 90, 90)
    pdf.multi_cell(kutu_w - 4, 3.8, yaz(f_adi_metni[:95]), align="C")

    pdf.set_draw_color(210, 215, 220)
    pdf.line(kutu_x + 10, alt_y + 28, kutu_x + kutu_w - 10, alt_y + 28)
    sag_bitis_y = alt_y + kutu_h

    if ayar["pro_mu"] == 0:
        pdf.set_y(sag_bitis_y + 5)
        pdf.set_font(font_name, "B", 9)
        pdf.set_text_color(180, 83, 9)
        pdf.cell(0, 6, yaz("Bu fiyat teklifi TeklifCepte uygulaması ile ücretsiz hazırlanmıştır."), align="C")

    pdf.output(dosya_adi)
    return os.path.abspath(dosya_adi)


def create_quote_pdf(ayar, musteri_adi, kalemler, ara_toplam, iskonto, kdv_oran, kdv_tutar, genel_toplam, gecerlilik_suresi, notlar="", pb="TL", musteri_adres=""):
    try:
        return _pdf_ciz(ayar, musteri_adi, kalemler, ara_toplam, iskonto, kdv_oran, kdv_tutar, genel_toplam, gecerlilik_suresi, notlar, pb, musteri_adres, font_kullan=True)
    except Exception:
        try:
            return _pdf_ciz(ayar, musteri_adi, kalemler, ara_toplam, iskonto, kdv_oran, kdv_tutar, genel_toplam, gecerlilik_suresi, notlar, pb, musteri_adres, font_kullan=False)
        except Exception:
            temiz_isim = "".join(c if c.isalnum() else "_" for c in tr_temizle(musteri_adi)) or "Musteri"
            zaman_eki = datetime.now().strftime("%Y%m%d_%H%M%S")
            dosya_adi = os.path.join(ARSIV_KLASORU, f"Teklif_{temiz_isim}_{zaman_eki}.pdf")
            return yedek_pdf_uret(dosya_adi, ayar, musteri_adi, kalemler, ara_toplam, iskonto, kdv_oran, kdv_tutar, genel_toplam, gecerlilik_suresi, notlar, pb, musteri_adres)


def ozel_buton(yazi, tiklama=None, renk="#1E3A8A", padding_degeri=10, url=None):
    return ft.Container(
        content=ft.Text(yazi, color="#FFFFFF", weight="bold", size=13),
        bgcolor=renk,
        padding=padding_degeri,
        border_radius=8,
        on_click=tiklama,
        url=url,
    )


def main(page: ft.Page):
    init_db()
    pdf_sunucu_baslat()
    page.title = "TeklifCepte Pro v4.3"
    page.theme_mode = ft.ThemeMode.LIGHT
    page.padding = 12
    page.scroll = ft.ScrollMode.AUTO

    kalemler = []
    secili_kdv = [20]
    secili_birim = ["Adet"]
    secili_pb = ["TL"]

    async def url_baslat(hedef):
        if os.name == "nt":
            try:
                webbrowser.open(hedef)
            except Exception:
                pass
            return
        try:
            sonuc = page.launch_url(hedef)
            if inspect.iscoroutine(sonuc):
                await sonuc
        except Exception:
            try:
                webbrowser.open(hedef)
            except Exception:
                pass

    def pdf_url_getir(dosya_yolu):
        port = pdf_sunucu_baslat()
        dosya_ismi = urllib.parse.quote(os.path.basename(dosya_yolu))
        return f"http://127.0.0.1:{port}/{dosya_ismi}"

    async def cihazda_pdf_ac_async(dosya_yolu):
        if not dosya_yolu or not os.path.exists(dosya_yolu):
            mesaj_goster("⚠️ PDF dosyası bulunamadı!", "#DC2626", "#FEE2E2")
            return
        if os.name == "nt":
            os.startfile(dosya_yolu)
        else:
            await url_baslat(pdf_url_getir(dosya_yolu))

    def get_ayarlar():
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT firma_adi, firma_tel, firma_iban, pro_mu, kalan_hak, logo_yolu, gecerlilik, firma_adres, cihaz_kodu FROM ayarlar WHERE id=1")
        r = c.fetchone()
        conn.close()
        return {
            "firma_adi": r[0] or "",
            "firma_tel": r[1] or "",
            "firma_iban": r[2] or "",
            "pro_mu": r[3],
            "kalan_hak": r[4],
            "logo_yolu": r[5] or "",
            "gecerlilik": r[6] or "30 Gün",
            "firma_adres": r[7] or "",
            "cihaz_kodu": r[8] or "10000",
        }

    ust_logo_kutusu = ft.Container(width=50, height=50, bgcolor="#F1F5F9", border_radius=8, padding=4)
    ust_firma_baslik = ft.Text("", size=16, weight="bold", color="#1E3A8A")
    durum_mesaji = ft.Text("", color="#15803D", weight="bold", size=13)
    alt_bildirim_kutusu = ft.Container(visible=False, padding=10, border_radius=8)
    pdf_sonuc_kutusu = ft.Column(spacing=8, tight=True)
    paket_etiketi = ft.Text("", weight="bold", size=12)
    icerik_alani = ft.Column(spacing=10, tight=True)

    def mesaj_goster(metin, renk="#15803D", arka="#DCFCE7"):
        durum_mesaji.value = metin
        durum_mesaji.color = renk
        alt_bildirim_kutusu.content = ft.Text(metin, color=renk, weight="bold", size=14)
        alt_bildirim_kutusu.bgcolor = arka
        alt_bildirim_kutusu.visible = True
        page.update()

    def hizli_logo_sec(e):
        yeni_yol = cihazdan_logo_yukle()
        if yeni_yol:
            conn = sqlite3.connect(DB_FILE)
            conn.execute("UPDATE ayarlar SET logo_yolu=? WHERE id=1", (yeni_yol,))
            conn.commit()
            conn.close()
            ust_bilgiyi_yenile()
            mesaj_goster("✅ Kurum logonuz yüklendi!")
        elif not TKINTER_VAR:
            mesaj_goster("ℹ️ Mobil sürümde firma bilgilerinizi '5. Firma/Pro' sekmesinden düzenleyebilirsiniz.", "#1E40AF", "#DBEAFE")

    ilk_ayar = get_ayarlar()
    musteri_adi = ft.TextField(label="Müşteri Adı Soyadı / Firma", width=280)
    musteri_tel = ft.TextField(label="Müşteri WhatsApp No (05...)", width=220)
    musteri_adres = ft.TextField(label="Müşteri Adresi / Vergi No (İsteğe Bağlı)", width=300)
    musteri_filtre_input = ft.TextField(label="🔍 Kayıtlı Müşteri Ara...", width=220, height=45)

    urun_adi = ft.TextField(label="Hizmet veya Malzeme Adı", width=260)
    miktar = ft.TextField(label="Miktar", value="1", width=90)
    birim_fiyat = ft.TextField(label="Birim Fiyat", width=140)
    iskonto_input = ft.TextField(label="İskonto", value="0", width=120)
    gecerlilik_input = ft.TextField(label="Geçerlilik Süresi", value=ilk_ayar["gecerlilik"], width=140)
    teklif_notu = ft.TextField(label="Özel Not / Ödeme Şartı (Örn: %50 Peşin, Kalanı Teslimde)", width=340)

    birim_etiketi = ft.Text("Seçili Birim: Adet | Para Birimi: TL", size=13, weight="bold", color="#0F766E")
    kalem_tablosu = ft.Column(spacing=6, tight=True)
    ozet_text = ft.Text("Genel Toplam: 0.00 TL", size=16, weight="bold", color="#1E3A8A")
    hazir_butonlar_row = ft.Row(wrap=True, spacing=6)
    kayitli_musteriler_row = ft.Row(wrap=True, spacing=6)

    def hesapla():
        ara = sum(k["toplam"] for k in kalemler)
        try:
            isk = float(iskonto_input.value.replace(",", "."))
        except ValueError:
            isk = 0.0
        kdv_matrah = max(0.0, ara - isk)
        kdv_tutari = kdv_matrah * (secili_kdv[0] / 100.0)
        genel = kdv_matrah + kdv_tutari
        return ara, isk, kdv_tutari, genel

    def yazili_kalemi_otomatik_ekle():
        if urun_adi.value and urun_adi.value.strip() and birim_fiyat.value and birim_fiyat.value.strip():
            try:
                m = float((miktar.value or "1").replace(",", "."))
                f = float(birim_fiyat.value.replace(",", "."))
                kalemler.append({
                    "ad": urun_adi.value.strip(),
                    "miktar": m,
                    "birim": secili_birim[0],
                    "fiyat": f,
                    "toplam": m * f
                })
                urun_adi.value = ""
                birim_fiyat.value = ""
                miktar.value = "1"
                return True
            except ValueError:
                return False
        return False

    def wp_url_olustur():
        m_adi = musteri_adi.value.strip() if (musteri_adi.value and musteri_adi.value.strip()) else "Sayın Müşterimiz"
        m_adr = musteri_adres.value.strip() if (musteri_adres.value and musteri_adres.value.strip()) else ""
        ara, isk, kdv_t, genel = hesapla()
        pb = secili_pb[0]
        ayar = get_ayarlar()
        tel = "".join(filter(str.isdigit, musteri_tel.value or ""))
        if tel.startswith("0"):
            tel = "9" + tel
        elif len(tel) == 10 and tel.startswith("5"):
            tel = "90" + tel
        kalem_listesi = "\n".join(
            f"• {k['ad']} ({k['miktar']:g} {k.get('birim', 'Adet')}): {k['toplam']:,.2f} {pb}"
            for k in kalemler
        ) or "• Fiyat Teklifi"
        adres_satiri = f"Adres/Bilgi: {m_adr}\n" if m_adr else ""
        not_satiri = f"\nNot: {teklif_notu.value.strip()}\n" if (teklif_notu.value and teklif_notu.value.strip()) else "\n"
        mesaj = (
            f"*RESMİ FİYAT TEKLİFİ*\n"
            f"*{ayar['firma_adi']}* ({ayar['firma_tel']})\n"
            f"Tarih: {datetime.now().strftime('%d.%m.%Y')}\n\n"
            f"Sayın *{m_adi}*,\n"
            f"{adres_satiri}\n"
            f"{kalem_listesi}\n\n"
            f"Ara Toplam: {ara:,.2f} {pb}\n"
            f"KDV (%{secili_kdv[0]}): {kdv_t:,.2f} {pb}\n"
            f"*GENEL TOPLAM: {genel:,.2f} {pb}*"
            f"{not_satiri}"
            f"Geçerlilik Süresi: {gecerlilik_input.value}\n"
            f"IBAN: {ayar['firma_iban']}"
        )
        return f"https://wa.me/{tel}?text={urllib.parse.quote(mesaj)}"

    wp_ana_buton = ozel_buton("💬 WhatsApp'tan Gönder", None, "#16A34A", 12)

    def ust_bilgiyi_yenile():
        ayar = get_ayarlar()
        f_ad = ayar["firma_adi"] if ayar["firma_adi"] else "Firma Adı Girilmedi"
        ust_firma_baslik.value = f"{f_ad}"

        if ayar["logo_yolu"] and os.path.exists(ayar["logo_yolu"]):
            ust_logo_kutusu.content = ft.Image(src=ayar["logo_yolu"], width=42, height=42)
        else:
            ust_logo_kutusu.content = ft.Text("🏢", size=22)

        if ayar["pro_mu"] == 1:
            paket_etiketi.value = "💎 PRO SÜRÜM (Sınırsız Lisanslı)"
            paket_etiketi.color = "#047857"
        else:
            paket_etiketi.value = f"🎁 ÜCRETSİZ (Kalan PDF: {ayar['kalan_hak']}/5)"
            paket_etiketi.color = "#B45309"

    def kayitli_musterileri_yukle():
        kayitli_musteriler_row.controls.clear()
        filtre = (musteri_filtre_input.value or "").strip().lower()
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT id, ad, tel, adres FROM musteriler ORDER BY id DESC")
        tum_musteriler = c.fetchall()
        conn.close()

        secilenler = [m for m in tum_musteriler if filtre in (m[1] or "").lower() or filtre in (m[2] or "").lower()]

        if not secilenler:
            kayitli_musteriler_row.controls.append(
                ft.Text("Henüz kayıtlı müşteri yok (Teklif verdikçe veya '💾 Müşteriyi Kaydet'e bastıkça buraya eklenir).", size=12, color="#64748B")
            )
        else:
            for mid, m_ad, m_tel, m_adr in secilenler[:15]:
                def musteri_getir(a=m_ad, t=m_tel, adr=m_adr):
                    def _sec(e):
                        musteri_adi.value = a or ""
                        musteri_tel.value = t or ""
                        musteri_adres.value = adr or ""
                        mesaj_goster(f"👤 '{a}' bilgileri otomatik dolduruldu!")
                        guncelle_teklif_ekrani()
                    return _sec

                etiket = f"👤 {m_ad}" + (f" ({m_tel})" if m_tel else "")
                kayitli_musteriler_row.controls.append(ozel_buton(etiket, musteri_getir(), "#0284C7", 7))

    def manuel_musteri_kaydet(e):
        if not musteri_adi.value or not musteri_adi.value.strip():
            mesaj_goster("⚠️ Kaydetmek için önce Müşteri Adı girin!", "#DC2626", "#FEE2E2")
            return
        musteri_rehbere_kaydet(musteri_adi.value, musteri_tel.value, musteri_adres.value)
        kayitli_musterileri_yukle()
        mesaj_goster(f"✅ '{musteri_adi.value.strip()}' müşteri rehberine kaydedildi!")

    def musteri_kutulari_temizle(e):
        musteri_adi.value = ""
        musteri_tel.value = ""
        musteri_adres.value = ""
        guncelle_teklif_ekrani()

    musteri_filtre_input.on_change = lambda e: (kayitli_musterileri_yukle(), page.update())

    def guncelle_teklif_ekrani():
        ust_bilgiyi_yenile()
        pb = secili_pb[0]
        birim_etiketi.value = f"📏 Seçili Birim: {secili_birim[0]}   |   💱 Para Birimi: {pb}"
        kalem_tablosu.controls.clear()
        for i, k in enumerate(kalemler):
            def sil_yap(idx=i):
                def _sil(e):
                    kalemler.pop(idx)
                    guncelle_teklif_ekrani()
                return _sil

            b_ad = k.get("birim", "Adet")
            kalem_tablosu.controls.append(
                ft.Container(
                    content=ft.Row([
                        ft.Column([
                            ft.Text(f"{i+1}. {k['ad']}", weight="bold", size=14),
                            ft.Text(f"{k['miktar']:g} {b_ad} x {k['fiyat']:,.2f} {pb} = {k['toplam']:,.2f} {pb}", color="#1E3A8A", weight="bold", size=13),
                        ], spacing=2, tight=True),
                        ozel_buton("🗑️ Sil", sil_yap(i), "#DC2626", 7)
                    ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN, wrap=True),
                    padding=10, bgcolor="#F1F5F9", border_radius=8
                )
            )
        ara, isk, kdv_t, genel = hesapla()
        ozet_text.value = f"Ara: {ara:,.2f} {pb} | KDV (%{secili_kdv[0]}): {kdv_t:,.2f} {pb} | TOPLAM: {genel:,.2f} {pb}"
        wp_ana_buton.url = wp_url_olustur()
        page.update()

    musteri_adi.on_change = lambda e: guncelle_teklif_ekrani()
    musteri_tel.on_change = lambda e: guncelle_teklif_ekrani()
    musteri_adres.on_change = lambda e: guncelle_teklif_ekrani()
    iskonto_input.on_change = lambda e: guncelle_teklif_ekrani()
    gecerlilik_input.on_change = lambda e: guncelle_teklif_ekrani()
    teklif_notu.on_change = lambda e: guncelle_teklif_ekrani()

    def birim_sec(b):
        def _sec(e):
            secili_birim[0] = b
            guncelle_teklif_ekrani()
        return _sec

    def pb_sec(p):
        def _sec(e):
            secili_pb[0] = p
            guncelle_teklif_ekrani()
        return _sec

    def hazir_kalemleri_yukle():
        hazir_butonlar_row.controls.clear()
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT ad, fiyat FROM hazir_kalemler")
        for ad, fiy in c.fetchall():
            def hizli_ekle(a=ad, f=fiy):
                def _ekle(e):
                    kalemler.append({"ad": a, "miktar": 1.0, "birim": secili_birim[0], "fiyat": f, "toplam": f})
                    mesaj_goster(f"✅ '{a}' listeye eklendi.")
                    guncelle_teklif_ekrani()
                return _ekle
            hazir_butonlar_row.controls.append(ozel_buton(f"⚡ + {ad} ({fiy:,.0f})", hizli_ekle(), "#475569", 8))
        conn.close()

    def kalem_ekle(e):
        if not urun_adi.value or not birim_fiyat.value:
            mesaj_goster("⚠️ Hizmet adı ve birim fiyat girin!", "#DC2626", "#FEE2E2")
            return
        try:
            m = float(miktar.value.replace(",", "."))
            f = float(birim_fiyat.value.replace(",", "."))
            eklenen_ad = urun_adi.value.strip()
            kalemler.append({
                "ad": eklenen_ad,
                "miktar": m,
                "birim": secili_birim[0],
                "fiyat": f,
                "toplam": m * f
            })
            urun_adi.value = ""
            birim_fiyat.value = ""
            miktar.value = "1"
            mesaj_goster(f"✅ '{eklenen_ad}' ({m:g} {secili_birim[0]}) eklendi!")
            guncelle_teklif_ekrani()
        except ValueError:
            mesaj_goster("⚠️ Miktar ve fiyata sadece sayı girin!", "#DC2626", "#FEE2E2")

    def kdv_degistir(oran):
        def _degis(e):
            secili_kdv[0] = oran
            guncelle_teklif_ekrani()
        return _degis

    async def whatsapp_gonder(e=None):
        yazili_kalemi_otomatik_ekle()
        if not kalemler:
            mesaj_goster("⚠️ WhatsApp gönderimi için en az 1 hizmet kalemi ekleyin!", "#DC2626", "#FEE2E2")
            return
        musteri_rehbere_kaydet(musteri_adi.value, musteri_tel.value, musteri_adres.value)
        kayitli_musterileri_yukle()
        hedef_wp = wp_url_olustur()
        wp_ana_buton.url = hedef_wp
        mesaj_goster("💬 WhatsApp sohbet ekranı açılıyor...")
        await url_baslat(hedef_wp)

    wp_ana_buton.on_click = whatsapp_gonder

    async def pdf_olustur_tikla(e):
        try:
            yazili_kalemi_otomatik_ekle()
            ayar = get_ayarlar()
            if ayar["pro_mu"] == 0 and ayar["kalan_hak"] <= 0:
                mesaj_goster(f"🔒 Ücretsiz 5 PDF hakkınız doldu! '5. Firma/Pro' sekmesinden ({PRO_FIYAT_METNI}) Pro'ya geçin.", "#DC2626", "#FEE2E2")
                return
            if not kalemler:
                mesaj_goster("⚠️ Önce yukarıdaki hazır kalemlere dokunun veya hizmet ekleyin!", "#DC2626", "#FEE2E2")
                return

            m_adi = musteri_adi.value.strip() if (musteri_adi.value and musteri_adi.value.strip()) else "Sayın Müşterimiz"
            m_adr = (musteri_adres.value or "").strip()
            musteri_rehbere_kaydet(m_adi, musteri_tel.value, m_adr)
            kayitli_musterileri_yukle()

            ara, isk, kdv_t, genel = hesapla()
            pb = secili_pb[0]
            gecerlilik_str = (gecerlilik_input.value or "30 Gün").strip()
            not_str = (teklif_notu.value or "").strip()

            dosya_yolu = create_quote_pdf(
                ayar, m_adi, kalemler, ara, isk, secili_kdv[0], kdv_t, genel, gecerlilik_str, not_str, pb, m_adr
            )

            ozet_metni = ", ".join(f"{k['ad']} ({k['miktar']:g} {k.get('birim', 'Adet')})" for k in kalemler)
            tarih_str = datetime.now().strftime("%d.%m.%Y %H:%M")
            kalem_json_str = json.dumps(kalemler, ensure_ascii=False)

            conn = sqlite3.connect(DB_FILE)
            conn.execute("UPDATE ayarlar SET gecerlilik=? WHERE id=1", (gecerlilik_str,))
            conn.execute(
                "INSERT INTO gecmis_teklifler (musteri, tel, toplam, tarih, dosya_yolu, kalem_ozeti, durum, kalem_json, para_birimi, musteri_adres) "
                "VALUES (?, ?, ?, ?, ?, ?, 'Bekliyor', ?, ?, ?)",
                (m_adi, (musteri_tel.value or "").strip(), genel, tarih_str, dosya_yolu, ozet_metni, kalem_json_str, pb, m_adr)
            )
            if ayar["pro_mu"] == 0 and ayar["kalan_hak"] > 0:
                conn.execute("UPDATE ayarlar SET kalan_hak = kalan_hak - 1 WHERE id=1")
            conn.commit()
            conn.close()

            hedef_url = pdf_url_getir(dosya_yolu)
            hedef_wp = wp_url_olustur()
            kalem_satirlari = [
                ft.Text(f"• {k['ad']} ({k['miktar']:g} {k.get('birim', 'Adet')} x {k['fiyat']:,.2f} {pb}) = {k['toplam']:,.2f} {pb}", size=13, color="#1E293B")
                for k in kalemler
            ]

            async def _indir_tikla(ev):
                await cihazda_pdf_ac_async(dosya_yolu)

            pdf_sonuc_kutusu.controls.clear()
            pdf_sonuc_kutusu.controls.append(
                ft.Container(
                    content=ft.Column([
                        ft.Text("✅ RESMİ FİYAT TEKLİFİNİZ HAZIRLANDI!", weight="bold", color="#15803D", size=15),
                        ft.Container(
                            content=ft.Column([
                                ft.Text(ayar["firma_adi"].upper(), weight="bold", size=15, color="#1E3A8A", text_align=ft.TextAlign.CENTER),
                                ft.Text(f"Tel: {ayar['firma_tel']} | Tarih: {datetime.now().strftime('%d.%m.%Y')}", size=12, color="#475569"),
                                ft.Divider(height=1),
                                ft.Text(f"SAYIN: {m_adi}", weight="bold", size=14, color="#0F172A"),
                                ft.Text(f"Adres/Bilgi: {m_adr}" if m_adr else "", size=12, color="#475569"),
                                ft.Column(kalem_satirlari, spacing=3, tight=True),
                                ft.Divider(height=1),
                                ft.Text(f"Ara Toplam: {ara:,.2f} {pb} | KDV (%{secili_kdv[0]}): {kdv_t:,.2f} {pb}", size=12, color="#334155"),
                                ft.Text(f"GENEL TOPLAM: {genel:,.2f} {pb}", weight="bold", size=16, color="#047857"),
                                ft.Text(f"Not: {not_str}" if not_str else "", size=12, color="#854D0E"),
                                ft.Text(f"IBAN: {ayar['firma_iban']}", weight="bold", size=12, color="#1E3A8A"),
                                ft.Text(f"Geçerlilik Süresi: {gecerlilik_str} | Yetkili Kaşe / İmza", size=11, color="#B45309"),
                            ], spacing=5, tight=True),
                            padding=12, bgcolor="#FFFFFF", border_radius=8
                        ),
                        ft.Row([
                            ozel_buton(
                                "📥 PDF Dosyasını Aç / İndir",
                                _indir_tikla,
                                "#1E40AF",
                                12,
                                url=hedef_url if os.name != "nt" else None
                            ),
                            ozel_buton(
                                "💬 WhatsApp ile Hemen Gönder",
                                whatsapp_gonder,
                                "#16A34A",
                                12,
                                url=hedef_wp
                            ),
                        ], wrap=True, spacing=8)
                    ], spacing=8, tight=True),
                    padding=12, bgcolor="#DCFCE7", border_radius=10
                )
            )

            mesaj_goster("✅ Teklif hazırlandı ve müşteri rehbere kaydedildi!")
            guncelle_teklif_ekrani()
            await cihazda_pdf_ac_async(dosya_yolu)
        except Exception as ex:
            mesaj_goster(f"⚠️ Hata oluştu: {ex}", "#DC2626", "#FEE2E2")

    def cariye_aktar(e):
        yazili_kalemi_otomatik_ekle()
        if not kalemler:
            mesaj_goster("⚠️ Cariye kaydetmek için en az 1 kalem ekleyin!", "#DC2626", "#FEE2E2")
            return
        m_adi = musteri_adi.value.strip() if (musteri_adi.value and musteri_adi.value.strip()) else "Sayın Müşterimiz"
        musteri_rehbere_kaydet(m_adi, musteri_tel.value, musteri_adres.value)
        kayitli_musterileri_yukle()
        _, _, _, genel = hesapla()
        conn = sqlite3.connect(DB_FILE)
        conn.execute("INSERT INTO cariler (musteri, tel, toplam_borc, odenen, tarih) VALUES (?, ?, ?, 0, ?)",
                     (m_adi, (musteri_tel.value or "").strip(), genel, datetime.now().strftime("%d.%m.%Y")))
        conn.commit()
        conn.close()
        mesaj_goster(f"✅ {m_adi} ({genel:,.2f} {secili_pb[0]}) Cari Hesaplara ve Rehbere kaydedildi!")

    def goster_teklif_ekrani(e=None):
        icerik_alani.controls.clear()
        kayitli_musterileri_yukle()
        hazir_kalemleri_yukle()
        guncelle_teklif_ekrani()
        icerik_alani.controls.extend([
            ft.Container(
                content=ft.Column([
                    ft.Row([
                        ft.Text("1. Müşteri Bilgileri (Rehberden Seç veya Yeni Yaz)", weight="bold", size=15, color="#1E3A8A"),
                        musteri_filtre_input,
                    ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN, wrap=True),
                    ft.Text("👥 Kayıtlı Müşterileriniz (Tek Tıkla Bilgileri Doldur):", size=12, weight="bold", color="#0284C7"),
                    kayitli_musteriler_row,
                    ft.Row([musteri_adi, musteri_tel], wrap=True),
                    ft.Row([
                        musteri_adres,
                        ozel_buton("💾 Müşteriyi Kaydet", manuel_musteri_kaydet, "#0284C7", 10),
                        ozel_buton("🧹 Temizle", musteri_kutulari_temizle, "#64748B", 10),
                    ], wrap=True),
                ], spacing=8, tight=True),
                padding=10, bgcolor="#F8FAFC", border_radius=10
            ),
            ft.Text("2. Kayıtlı Hizmetlerden Tek Tıkla Ekle:", weight="bold", size=13, color="#475569"),
            hazir_butonlar_row,
            birim_etiketi,
            ft.Row([
                ozel_buton("Adet", birim_sec("Adet"), "#0F766E", 6),
                ozel_buton("m²", birim_sec("m²"), "#0F766E", 6),
                ozel_buton("Metre", birim_sec("Metre"), "#0F766E", 6),
                ozel_buton("Kg", birim_sec("Kg"), "#0F766E", 6),
                ozel_buton("Saat", birim_sec("Saat"), "#0F766E", 6),
                ozel_buton("₺ TL", pb_sec("TL"), "#1E3A8A", 6),
                ozel_buton("$ USD", pb_sec("USD"), "#1E3A8A", 6),
                ozel_buton("€ EUR", pb_sec("EUR"), "#1E3A8A", 6),
            ], wrap=True, spacing=5),
            ft.Row([urun_adi, miktar, birim_fiyat, ozel_buton("➕ Kalem Ekle", kalem_ekle, "#2563EB", 12)], wrap=True),
            kalem_tablosu,
            ft.Row([
                iskonto_input,
                gecerlilik_input,
                ozel_buton("%0 KDV", kdv_degistir(0), "#64748B", 8),
                ozel_buton("%10 KDV", kdv_degistir(10), "#64748B", 8),
                ozel_buton("%20 KDV", kdv_degistir(20), "#64748B", 8),
            ], wrap=True),
            teklif_notu,
            ft.Divider(),
            ozet_text,
            ft.Row([
                ozel_buton("📄 PDF Oluştur ve Aç", pdf_olustur_tikla, "#1E40AF", 12),
                wp_ana_buton,
                ozel_buton("📒 Cariye Kaydet", cariye_aktar, "#D97706", 12),
            ], wrap=True, spacing=8),
            alt_bildirim_kutusu,
            pdf_sonuc_kutusu,
        ])
        page.update()

    arama_kutusu = ft.TextField(label="🔍 Müşteri Adına Göre Ara...", width=300)

    def goster_gecmis_teklifler(e=None):
        icerik_alani.controls.clear()
        aranan = (arama_kutusu.value or "").strip().lower()

        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT id, musteri, tel, toplam, tarih, dosya_yolu, kalem_ozeti, durum, kalem_json, para_birimi, musteri_adres FROM gecmis_teklifler ORDER BY id DESC")
        tum_teklifler = c.fetchall()
        conn.close()

        filtreli = [t for t in tum_teklifler if aranan in (t[1] or "").lower()]
        toplam_teklif_tutari = sum(t[3] for t in filtreli)
        onayli_toplam = sum(t[3] for t in filtreli if t[7] == "Onaylandı")
        arama_kutusu.on_change = lambda ev: goster_gecmis_teklifler()

        icerik_alani.controls.extend([
            ft.Text(f"📂 Arşiv ({len(filtreli)} Teklif) | Toplam: {toplam_teklif_tutari:,.2f} TL | ✅ Onaylanan: {onayli_toplam:,.2f} TL", size=15, weight="bold", color="#1E3A8A"),
            arama_kutusu,
        ])

        for tid, mus, tel, top, tar, yol, ozet, drm, k_json, pb, m_adr in filtreli:
            pb = pb or "TL"
            drm = drm or "Bekliyor"
            indir_linki = pdf_url_getir(yol) if (yol and os.path.exists(yol) and os.name != "nt") else None
            ayar = get_ayarlar()
            no = "".join(filter(str.isdigit, tel or ""))
            if no.startswith("0"):
                no = "9" + no
            elif len(no) == 10 and no.startswith("5"):
                no = "90" + no
            wp_msj = (
                f"Sayın *{mus}*,\n"
                f"*{ayar['firma_adi']}* olarak hazırladığımız fiyat teklifi:\n"
                f"Kalemler: {ozet}\n"
                f"*TOPLAM: {top:,.2f} {pb}*\n"
                f"IBAN: {ayar['firma_iban']}"
            )
            arsiv_wp_link = f"https://wa.me/{no}?text={urllib.parse.quote(wp_msj)}"

            def pdf_ac(dosya=yol):
                async def _ac(ev):
                    await cihazda_pdf_ac_async(dosya)
                return _ac

            def arsiv_wp_ac(hedef=arsiv_wp_link):
                async def _wp(ev):
                    await url_baslat(hedef)
                return _wp

            def teklifi_duzenle(m=mus, t=tel, kj=k_json, p_birim=pb, adr=m_adr):
                def _duz(ev):
                    musteri_adi.value = m
                    musteri_tel.value = t or ""
                    musteri_adres.value = adr or ""
                    secili_pb[0] = p_birim or "TL"
                    kalemler.clear()
                    if kj:
                        try:
                            yuklenen = json.loads(kj)
                            for item in yuklenen:
                                kalemler.append(item)
                        except Exception:
                            pass
                    mesaj_goster(f"✏️ '{m}' teklifi düzenleme ekranına yüklendi!")
                    goster_teklif_ekrani()
                return _duz

            def onayla_ve_cariye_at(kayit_id=tid, m=mus, t=tel, tutar=top):
                def _onay(ev):
                    conn2 = sqlite3.connect(DB_FILE)
                    conn2.execute("UPDATE gecmis_teklifler SET durum='Onaylandı' WHERE id=?", (kayit_id,))
                    conn2.execute(
                        "INSERT INTO cariler (musteri, tel, toplam_borc, odenen, tarih) VALUES (?, ?, ?, 0, ?)",
                        (m, t, tutar, datetime.now().strftime("%d.%m.%Y"))
                    )
                    conn2.commit()
                    conn2.close()
                    mesaj_goster(f"✅ '{m}' teklifi ONAYLANDI ve Cari Hesaplara aktarıldı!")
                    goster_gecmis_teklifler()
                return _onay

            def arsiv_sil(kayit_id=tid):
                def _sil(ev):
                    conn2 = sqlite3.connect(DB_FILE)
                    conn2.execute("DELETE FROM gecmis_teklifler WHERE id=?", (kayit_id,))
                    conn2.commit()
                    conn2.close()
                    goster_gecmis_teklifler()
                return _sil

            durum_rozeti = "✅ ONAYLANDI" if drm == "Onaylandı" else "⏳ BEKLİYOR"
            kart_rengi = "#DCFCE7" if drm == "Onaylandı" else "#F1F5F9"

            icerik_alani.controls.append(
                ft.Container(
                    content=ft.Column([
                        ft.Text(f"📄 {mus} ({tel or 'Tel Yok'}) | {durum_rozeti} | 🕒 {tar}", weight="bold", size=14, color="#1E3A8A"),
                        ft.Text(f"Kalemler: {ozet}", size=12, color="#475569"),
                        ft.Text(f"Teklif Tutarı: {top:,.2f} {pb}", weight="bold", size=14, color="#047857"),
                        ft.Row([
                            ozel_buton("📥 PDF Aç", pdf_ac(), "#1E40AF", 8, url=indir_linki),
                            ozel_buton("✏️ Düzenle", teklifi_duzenle(), "#0284C7", 8),
                            ozel_buton("💬 WP", arsiv_wp_ac(), "#16A34A", 8, url=arsiv_wp_link),
                            ozel_buton("✅ Onayla & Cariye At", onayla_ve_cariye_at(), "#D97706", 8),
                            ozel_buton("🗑️ Sil", arsiv_sil(), "#DC2626", 8),
                        ], wrap=True, spacing=6)
                    ], spacing=4, tight=True),
                    padding=10, bgcolor=kart_rengi, border_radius=8
                )
            )
        page.update()

    def goster_cari_ekrani(e=None):
        icerik_alani.controls.clear()
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT id, musteri, tel, toplam_borc, odenen, tarih FROM cariler ORDER BY id DESC")
        kayitlar = c.fetchall()
        conn.close()

        toplam_kalan = sum(r[3] - r[4] for r in kayitlar)
        icerik_alani.controls.append(
            ft.Text(f"💰 Toplam Bekleyen Alacak: {toplam_kalan:,.2f} TL", size=18, weight="bold", color="#B91C1C")
        )

        for r in kayitlar:
            cid, mus, tel, borc, odenen, tar = r
            kalan = borc - odenen
            tahsilat_kutusu = ft.TextField(label="Tahsilat (TL)", width=130)

            ayar = get_ayarlar()
            no = "".join(filter(str.isdigit, tel or ""))
            if no.startswith("0"):
                no = "9" + no
            elif len(no) == 10 and no.startswith("5"):
                no = "90" + no
            hatirlat_msj = f"Sayın *{mus}*, *{ayar['firma_adi']}* hesabınızda *{kalan:,.2f} TL* kalan bakiyeniz bulunmaktadır. IBAN: {ayar['firma_iban']}"
            cari_wp_link = f"https://wa.me/{no}?text={urllib.parse.quote(hatirlat_msj)}" if ayar["pro_mu"] == 1 else None

            def odeme_al(kayit_id=cid, kutu=tahsilat_kutusu):
                def _ode(ev):
                    try:
                        tutar = float(kutu.value.replace(",", "."))
                        conn2 = sqlite3.connect(DB_FILE)
                        conn2.execute("UPDATE cariler SET odenen = odenen + ? WHERE id=?", (tutar, kayit_id))
                        conn2.commit()
                        conn2.close()
                        mesaj_goster(f"✅ {tutar:,.2f} TL tahsilat düşüldü!")
                        goster_cari_ekrani()
                    except ValueError:
                        pass
                return _ode

            def wp_hatirlat(hedef=cari_wp_link):
                async def _wp(ev):
                    ayar_kontrol = get_ayarlar()
                    if ayar_kontrol["pro_mu"] == 0:
                        mesaj_goster(f"🔒 WhatsApp Hatırlatma PRO özelliğidir! '5. Firma/Pro' sekmesinden ({PRO_FIYAT_METNI}) Pro'yu açın.", "#DC2626", "#FEE2E2")
                        return
                    if hedef:
                        await url_baslat(hedef)
                return _wp

            def cari_sil(kayit_id=cid):
                def _sil(ev):
                    conn2 = sqlite3.connect(DB_FILE)
                    conn2.execute("DELETE FROM cariler WHERE id=?", (kayit_id,))
                    conn2.commit()
                    conn2.close()
                    goster_cari_ekrani()
                return _sil

            icerik_alani.controls.append(
                ft.Container(
                    content=ft.Column([
                        ft.Text(f"👤 {mus} ({tel}) - {tar}", weight="bold", size=14),
                        ft.Text(f"Toplam: {borc:,.2f} TL | Ödenen: {odenen:,.2f} TL | KALAN: {kalan:,.2f} TL", color="#B91C1C", weight="bold", size=13),
                        ft.Row([
                            tahsilat_kutusu,
                            ozel_buton("💵 Tahsilat Düş", odeme_al(), "#15803D", 8),
                            ozel_buton("📲 WP Hatırlat", wp_hatirlat(), "#0D9488", 8, url=cari_wp_link),
                            ozel_buton("🗑️", cari_sil(), "#DC2626", 8),
                        ], wrap=True, spacing=6)
                    ], spacing=4, tight=True),
                    padding=10, bgcolor="#FEF3C7", border_radius=8
                )
            )
        page.update()

    def goster_fiyat_listesi(e=None):
        icerik_alani.controls.clear()
        yeni_ad = ft.TextField(label="Yeni Hizmet / Malzeme Adı", width=260)
        yeni_fiyat = ft.TextField(label="Birim Fiyatı (TL)", width=140)

        def yeni_kaydet(ev):
            try:
                f = float(yeni_fiyat.value.replace(",", "."))
                conn = sqlite3.connect(DB_FILE)
                conn.execute("INSERT INTO hazir_kalemler (ad, fiyat) VALUES (?, ?)", (yeni_ad.value, f))
                conn.commit()
                conn.close()
                goster_fiyat_listesi()
            except ValueError:
                pass

        icerik_alani.controls.append(ft.Text("📦 Hazır Hizmet & Malzeme Listem", size=17, weight="bold", color="#1E3A8A"))
        icerik_alani.controls.append(ft.Row([yeni_ad, yeni_fiyat, ozel_buton("➕ Hizmet Kaydet", yeni_kaydet, "#2563EB")], wrap=True))

        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT id, ad, fiyat FROM hazir_kalemler")
        for hid, ad, fiy in c.fetchall():
            def sil_hazir(k_id=hid):
                def _s(ev):
                    conn2 = sqlite3.connect(DB_FILE)
                    conn2.execute("DELETE FROM hazir_kalemler WHERE id=?", (k_id,))
                    conn2.commit()
                    conn2.close()
                    goster_fiyat_listesi()
                return _s

            icerik_alani.controls.append(
                ft.Container(
                    content=ft.Row([
                        ft.Text(f"• {ad} ({fiy:,.2f} TL)", weight="bold", color="#1E3A8A"),
                        ozel_buton("🗑️ Sil", sil_hazir(), "#DC2626", 6)
                    ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                    padding=8, bgcolor="#F1F5F9", border_radius=6
                )
            )

        icerik_alani.controls.append(ft.Divider())
        icerik_alani.controls.append(ft.Text("👥 Kayıtlı Müşteri Rehberim", size=17, weight="bold", color="#0284C7"))

        c.execute("SELECT id, ad, tel, adres FROM musteriler ORDER BY id DESC")
        musteri_listesi = c.fetchall()
        conn.close()

        if not musteri_listesi:
            icerik_alani.controls.append(ft.Text("Henüz kayıtlı müşteri bulunmuyor.", size=13, color="#64748B"))
        else:
            for mid, m_ad, m_tel, m_adr in musteri_listesi:
                def teklife_sec(a=m_ad, t=m_tel, adr=m_adr):
                    def _sec(ev):
                        musteri_adi.value = a or ""
                        musteri_tel.value = t or ""
                        musteri_adres.value = adr or ""
                        mesaj_goster(f"👤 '{a}' seçildi, teklif kalemlerini ekleyebilirsiniz!")
                        goster_teklif_ekrani()
                    return _sec

                def sil_musteri(k_id=mid):
                    def _sm(ev):
                        conn2 = sqlite3.connect(DB_FILE)
                        conn2.execute("DELETE FROM musteriler WHERE id=?", (k_id,))
                        conn2.commit()
                        conn2.close()
                        goster_fiyat_listesi()
                    return _sm

                icerik_alani.controls.append(
                    ft.Container(
                        content=ft.Row([
                            ft.Column([
                                ft.Text(f"👤 {m_ad} ({m_tel or 'Tel Yok'})", weight="bold", color="#0F172A"),
                                ft.Text(f"📍 {m_adr}" if m_adr else "", size=12, color="#475569"),
                            ], spacing=2, tight=True),
                            ft.Row([
                                ozel_buton("📝 Teklif Ver", teklife_sec(), "#0284C7", 6),
                                ozel_buton("🗑️ Sil", sil_musteri(), "#DC2626", 6),
                            ], spacing=6)
                        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN, wrap=True),
                        padding=8, bgcolor="#E0F2FE", border_radius=6
                    )
                )
        page.update()

    def goster_ayarlar(e=None):
        icerik_alani.controls.clear()
        ayar = get_ayarlar()
        cihaz_no = ayar["cihaz_kodu"]
        dogru_cihaz_sifresi = cihaza_ozel_sifre_uret(cihaz_no)

        f_adi = ft.TextField(label="Kendi Firma / Şirket / Usta Adınız", value=ayar["firma_adi"], width=320)
        f_tel = ft.TextField(label="İletişim Telefonunuz", value=ayar["firma_tel"], width=280)
        f_adres = ft.TextField(label="Firma Adresi / Vergi Dairesi (PDF'te Görünür)", value=ayar["firma_adres"], width=320)
        f_iban = ft.TextField(label="IBAN Numaranız (PDF'te Görünür)", value=ayar["firma_iban"], width=320)
        lisans_input = ft.TextField(label="🔑 PRO Aktivasyon Kodunuzu Girin", width=260)

        satin_alma_mesaji = (
            f"Merhaba, *TeklifCepte PRO* ({PRO_FIYAT_METNI}) lisans kodu satın almak istiyorum.\n"
            f"Firma Adım: {ayar['firma_adi']}\n"
            f"Cihaz Kodum: *{cihaz_no}*"
        )
        wp_satis_url = f"https://wa.me/{SATIS_WHATSAPP_NO}?text={urllib.parse.quote(satin_alma_mesaji)}"

        async def wp_satis_ac(ev):
            await url_baslat(wp_satis_url)

        def kaydet_ayar(ev):
            conn = sqlite3.connect(DB_FILE)
            conn.execute("UPDATE ayarlar SET firma_adi=?, firma_tel=?, firma_iban=?, firma_adres=? WHERE id=1",
                         (f_adi.value.strip(), f_tel.value.strip(), f_iban.value.strip(), f_adres.value.strip()))
            conn.commit()
            conn.close()
            ust_bilgiyi_yenile()
            mesaj_goster(f"✅ '{f_adi.value.strip()}' olarak firma bilgileriniz kaydedildi!")
            goster_teklif_ekrani()

        def lisans_dogrula(ev):
            girilen = (lisans_input.value or "").strip().upper()
            if girilen.startswith("URET-"):
                musteri_cihaz = girilen.replace("URET-", "").strip()
                uretilen = cihaza_ozel_sifre_uret(musteri_cihaz)
                mesaj_goster(f"🔐 Müşteri ({musteri_cihaz}) İçin Özel PRO Şifresi: {uretilen}", "#1E40AF", "#DBEAFE")
                return

            if girilen in [PRO_ANA_SIFRE, dogru_cihaz_sifresi]:
                conn = sqlite3.connect(DB_FILE)
                conn.execute("UPDATE ayarlar SET pro_mu=1, kalan_hak=999 WHERE id=1")
                conn.commit()
                conn.close()
                mesaj_goster("🎉 Tebrikler! PRO Sürüm Sınırsız Lisansınız Aktif Edildi!")
                ust_bilgiyi_yenile()
                goster_ayarlar()
            else:
                mesaj_goster("⚠️ Geçersiz Lisans Kodu! Lütfen satın aldığınız aktivasyon kodunu kontrol edin.", "#DC2626", "#FEE2E2")

        def ucretsiz_don(ev):
            conn = sqlite3.connect(DB_FILE)
            conn.execute("UPDATE ayarlar SET pro_mu=0, kalan_hak=5 WHERE id=1")
            conn.commit()
            conn.close()
            mesaj_goster("ℹ️ Ücretsiz deneme sürümüne dönüldü.")
            ust_bilgiyi_yenile()
            goster_ayarlar()

        pro_satis_karti = ft.Container(
            content=ft.Column([
                ft.Text("💎 TeklifCepte PRO Sürüm Paketi", size=17, weight="bold", color="#6D28D9"),
                ft.Container(
                    content=ft.Column([
                        ft.Text(f"🏷️ Paket Ücreti: {PRO_FIYAT_METNI}", size=16, weight="bold", color="#047857"),
                        ft.Text(f"📱 Cihaz Lisans No: {cihaz_no} (Bu cihaza özeldir)", size=12, weight="bold", color="#475569"),
                        ft.Divider(height=1),
                        ft.Text("✔️ Sınırsız PDF Fiyat Teklifi Oluşturma", size=13, color="#1E293B"),
                        ft.Text("✔️ PDF Altındaki 'Ücretsiz Hazırlanmıştır' Yazısını Kaldırma", size=13, color="#1E293B"),
                        ft.Text("✔️ Cari Hesaplarda Tek Tıkla WhatsApp Borç Hatırlatma", size=13, color="#1E293B"),
                        ft.Text("✔️ Kurumsal Logo, Kaşe ve Dövizli ($ / € / ₺) Teklif Desteği", size=13, color="#1E293B"),
                    ], spacing=4, tight=True),
                    padding=12, bgcolor="#FFFFFF", border_radius=8
                ),
                ozel_buton("💬 WhatsApp'tan PRO Lisans Satın Al (Havale / FAST)", wp_satis_ac, "#16A34A", 14, url=wp_satis_url),
                ft.Divider(height=1),
                ft.Text("WhatsApp'tan aldığınız aktivasyon şifresini aşağıya girin:", size=12, color="#475569", weight="bold"),
                ft.Row([
                    lisans_input,
                    ozel_buton("🔓 PRO Sürümü Aktifleştir", lisans_dogrula, "#7C3AED", 12),
                ], wrap=True, spacing=8),
                alt_bildirim_kutusu,
            ], spacing=8, tight=True),
            padding=12, bgcolor="#F3E8FF", border_radius=10
        )

        pro_aktif_karti = ft.Container(
            content=ft.Column([
                ft.Text("💎 PRO SÜRÜM LİSANSINIZ AKTİF", size=16, weight="bold", color="#047857"),
                ft.Text(f"Cihaz Lisans No: {cihaz_no} | Tüm sınırsız özellikler açık.", size=13, color="#1E293B"),
                ozel_buton("🔄 Ücretsiz Sürüme Dön (Test İçin)", ucretsiz_don, "#64748B", 10),
                alt_bildirim_kutusu,
            ], spacing=8, tight=True),
            padding=12, bgcolor="#DCFCE7", border_radius=10
        )

        icerik_alani.controls.extend([
            ft.Container(
                content=ft.Column([
                    ft.Text("⚙️ Firma Bilgilerini Düzenle", size=17, weight="bold", color="#1E3A8A"),
                    f_adi,
                    f_tel,
                    f_adres,
                    f_iban,
                    ft.Row([
                        ozel_buton("💾 Firma Bilgilerini Kaydet", kaydet_ayar, "#15803D", 12),
                    ], wrap=True, spacing=10)
                ], spacing=10, tight=True),
                padding=12, bgcolor="#F8FAFC", border_radius=10
            ),
            ft.Divider(),
            pro_aktif_karti if ayar["pro_mu"] == 1 else pro_satis_karti,
        ])
        page.update()

    ust_bilgiyi_yenile()
    ana_duzen = ft.Column([
        ft.Container(
            content=ft.Column([
                ft.Row([
                    ust_logo_kutusu,
                    ft.Column([
                        ust_firma_baslik,
                        paket_etiketi
                    ], spacing=2, tight=True, width=260)
                ], spacing=10, wrap=True),
                ft.Row([
                    ozel_buton("✏️ Firma Adı / IBAN Değiştir", goster_ayarlar, "#475569", 7),
                    ozel_buton("🖼️ Logo Seç (PC)", hizli_logo_sec, "#0284C7", 7),
                ], wrap=True, spacing=6)
            ], spacing=6, tight=True),
            padding=10, bgcolor="#F8FAFC", border_radius=10
        ),
        ft.Row([
            ozel_buton("📝 1. Teklif", goster_teklif_ekrani, "#1E3A8A", 9),
            ozel_buton("📂 2. Arşiv", goster_gecmis_teklifler, "#0284C7", 9),
            ozel_buton("📒 3. Cari", goster_cari_ekrani, "#B45309", 9),
            ozel_buton("📦 4. Fiyat & Müşteri", goster_fiyat_listesi, "#0F766E", 9),
            ozel_buton("⚙️ 5. Firma/Pro", goster_ayarlar, "#6D28D9", 9),
        ], wrap=True, spacing=6),
        durum_mesaji,
        ft.Divider(height=1),
        icerik_alani
    ], spacing=8, tight=True)

    page.add(ft.SafeArea(content=ana_duzen))
    goster_teklif_ekrani()

if hasattr(ft, "run"):
    ft.run(main)
else:
    ft.app(target=main)
