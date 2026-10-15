import os
import shutil
import sqlite3
import tempfile
import urllib.parse
import webbrowser
from datetime import datetime
import flet as ft
from fpdf import FPDF

# Masaüstünde tkinter çalışır, Android telefonda hata vermemesi için korumalı yüklenir
try:
    import tkinter as tk
    from tkinter import filedialog
    TKINTER_VAR = True
except ImportError:
    TKINTER_VAR = False

# --- CİHAZ HAFIZA YOLU (ANDROID VE WINDOWS OTOMATİK ALGILAMA) ---
VERI_DIZINI = os.environ.get("FLET_APP_STORAGE_DATA")
if not VERI_DIZINI:
    if os.name == "nt":
        VERI_DIZINI = os.path.abspath(".")
    else:
        VERI_DIZINI = tempfile.gettempdir()

DB_FILE = os.path.join(VERI_DIZINI, "teklifcepte.db")
LOGO_KLASORU = os.path.join(VERI_DIZINI, "logolar")
ARSIV_KLASORU = os.path.join(VERI_DIZINI, "teklifler_arsiv")


# --- 1. VERİTABANI KURULUMU ---
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


# --- 2. CİHAZDAN LOGO SEÇME ---
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


# --- 3. PDF OLUŞTURMA MOTORU (ANDROID & WINDOWS TÜRKÇE FONT DESTEKLİ) ---
def create_quote_pdf(ayar, musteri_adi, kalemler, ara_toplam, iskonto, kdv_oran, kdv_tutar, genel_toplam, gecerlilik_suresi):
    pdf = FPDF()
    pdf.add_page()
    
    # Önce klasördeki gömülü fonta bak (Android için), yoksa Windows fontuna bak
    yerel_font = os.path.join(os.path.dirname(os.path.abspath(__file__)), "font.ttf")
    yerel_bold = os.path.join(os.path.dirname(os.path.abspath(__file__)), "font_bold.ttf")
    win_font = "C:/Windows/Fonts/arial.ttf"
    win_bold = "C:/Windows/Fonts/arialbd.ttf"

    if os.path.exists(yerel_font):
        pdf.add_font("TRFont", "", yerel_font)
        pdf.add_font("TRFont", "B", yerel_bold if os.path.exists(yerel_bold) else yerel_font)
        font_name = "TRFont"
    elif os.path.exists(win_font):
        pdf.add_font("TRFont", "", win_font)
        pdf.add_font("TRFont", "B", win_bold if os.path.exists(win_bold) else win_font)
        font_name = "TRFont"
    else:
        font_name = "Helvetica"

    # 1. SOL ÜST KÖŞEYE KURUM LOGOSU
    logo_yolu = ayar.get("logo_yolu", "").strip()
    logo_basildi = False
    if logo_yolu and os.path.exists(logo_yolu):
        try:
            pdf.image(logo_yolu, x=10, y=10, h=20)
            logo_basildi = True
        except Exception:
            logo_basildi = False

    # 2. SAĞ ÜST KÖŞEYE BELGE BAŞLIĞI VE TARİH
    pdf.set_xy(110, 12)
    pdf.set_font(font_name, "B", 11)
    pdf.set_text_color(37, 99, 235)
    pdf.cell(90, 6, "RESMİ FİYAT TEKLİFİ", align="R")

    pdf.set_xy(110, 18)
    pdf.set_font(font_name, "", 10)
    pdf.set_text_color(80, 80, 80)
    pdf.cell(90, 6, f"Tarih: {datetime.now().strftime('%d.%m.%Y')}", align="R")

    # 3. FİRMA İSMİ VE TELEFON (ALT SATIRDA VE SAYFA ORTASINDA)
    firma_y = 33 if logo_basildi else 22
    pdf.set_xy(10, firma_y)
    pdf.set_text_color(30, 58, 138)
    pdf.set_font(font_name, "B", 16)
    f_adi_metni = ayar["firma_adi"].upper() if ayar["firma_adi"] else "FİRMA ADI"
    pdf.cell(0, 8, f_adi_metni, new_x="LMARGIN", new_y="NEXT", align="C")

    pdf.set_xy(10, firma_y + 8)
    pdf.set_text_color(70, 70, 70)
    pdf.set_font(font_name, "", 10)
    pdf.cell(0, 6, f"İletişim / Tel: {ayar['firma_tel']}", new_x="LMARGIN", new_y="NEXT", align="C")

    cizgi_y = firma_y + 16
    pdf.set_draw_color(200, 200, 200)
    pdf.line(10, cizgi_y, 200, cizgi_y)

    # Müşteri Kutusu
    pdf.set_xy(10, cizgi_y + 4)
    pdf.set_fill_color(241, 245, 249)
    pdf.set_text_color(0, 0, 0)
    pdf.set_font(font_name, "B", 12)
    pdf.cell(0, 10, f"  SAYIN: {musteri_adi}", new_x="LMARGIN", new_y="NEXT", fill=True)
    pdf.ln(4)

    # Tablo Başlığı
    pdf.set_fill_color(30, 58, 138)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font(font_name, "B", 11)
    pdf.cell(95, 9, " Hizmet / Malzeme Açıklaması", border=1, fill=True)
    pdf.cell(25, 9, "Miktar", border=1, align="C", fill=True)
    pdf.cell(35, 9, "Birim Fiyat", border=1, align="R", fill=True)
    pdf.cell(35, 9, "Toplam", border=1, new_x="LMARGIN", new_y="NEXT", align="R", fill=True)

    # Kalemler
    pdf.set_text_color(0, 0, 0)
    pdf.set_font(font_name, "", 10)
    for k in kalemler:
        pdf.cell(95, 8, f" {k['ad']}", border=1)
        pdf.cell(25, 8, str(k['miktar']), border=1, align="C")
        pdf.cell(35, 8, f"{k['fiyat']:,.2f} TL", border=1, align="R")
        pdf.cell(35, 8, f"{k['toplam']:,.2f} TL", border=1, new_x="LMARGIN", new_y="NEXT", align="R")

    # Hesap Özeti
    pdf.ln(3)
    pdf.set_font(font_name, "", 10)
    pdf.cell(155, 7, "Ara Toplam:", align="R")
    pdf.cell(35, 7, f"{ara_toplam:,.2f} TL", border=1, new_x="LMARGIN", new_y="NEXT", align="R")

    if iskonto > 0:
        pdf.cell(155, 7, "İskonto (İndirim):", align="R")
        pdf.cell(35, 7, f"-{iskonto:,.2f} TL", border=1, new_x="LMARGIN", new_y="NEXT", align="R")

    if kdv_oran > 0:
        pdf.cell(155, 7, f"KDV (%{kdv_oran}):", align="R")
        pdf.cell(35, 7, f"{kdv_tutar:,.2f} TL", border=1, new_x="LMARGIN", new_y="NEXT", align="R")

    pdf.set_font(font_name, "B", 12)
    pdf.cell(155, 10, "GENEL TOPLAM:", align="R")
    pdf.set_fill_color(220, 252, 231)
    pdf.cell(35, 10, f"{genel_toplam:,.2f} TL", border=1, new_x="LMARGIN", new_y="NEXT", align="R", fill=True)

    if pdf.get_y() > 220:
        pdf.add_page()

    # IBAN Bilgisi
    pdf.ln(6)
    pdf.set_fill_color(241, 245, 249)
    pdf.set_font(font_name, "B", 10)
    pdf.set_text_color(30, 58, 138)
    pdf.cell(0, 8, f"  Ödeme İçin IBAN: {ayar['firma_iban']}", new_x="LMARGIN", new_y="NEXT", fill=True)

    # --- ALT BÖLÜM: SOLDA GEÇERLİLİK SÜRESİ, SAĞ ALTTA KAŞE / İMZA ---
    alt_y = pdf.get_y() + 6

    pdf.set_xy(10, alt_y)
    pdf.set_font(font_name, "B", 10)
    pdf.set_text_color(180, 83, 9)
    pdf.cell(112, 6, f"Teklif Geçerlilik Süresi: {gecerlilik_suresi}", new_x="LMARGIN", new_y="NEXT")

    kutu_x = 130
    kutu_w = 70
    kutu_h = 34
    pdf.set_draw_color(160, 175, 195)
    pdf.set_fill_color(250, 251, 253)
    pdf.rect(kutu_x, alt_y, kutu_w, kutu_h, style="DF")

    pdf.set_xy(kutu_x, alt_y + 2)
    pdf.set_font(font_name, "B", 10)
    pdf.set_text_color(30, 58, 138)
    pdf.cell(kutu_w, 6, "YETKİLİ KAŞE / İMZA", align="C")

    pdf.set_xy(kutu_x, alt_y + 8)
    pdf.set_font(font_name, "", 8)
    pdf.set_text_color(90, 90, 90)
    pdf.cell(kutu_w, 5, f_adi_metni[:32], align="C")

    pdf.set_draw_color(210, 215, 220)
    pdf.line(kutu_x + 10, alt_y + 26, kutu_x + kutu_w - 10, alt_y + 26)
    sag_bitis_y = alt_y + kutu_h

    if ayar["pro_mu"] == 0:
        pdf.set_y(sag_bitis_y + 6)
        pdf.set_font(font_name, "B", 9)
        pdf.set_text_color(180, 83, 9)
        pdf.cell(0, 6, "Bu fiyat teklifi TeklifCepte uygulaması ile ücretsiz hazırlanmıştır.", align="C")

    temiz_isim = "".join(c if c.isalnum() else "_" for c in musteri_adi)
    zaman_eki = datetime.now().strftime("%Y%m%d_%H%M%S")
    dosya_adi = os.path.join(ARSIV_KLASORU, f"Teklif_{temiz_isim}_{zaman_eki}.pdf")
    pdf.output(dosya_adi)
    return os.path.abspath(dosya_adi)


def ozel_buton(yazi, tiklama, renk="#1E3A8A", padding_degeri=10):
    return ft.Container(
        content=ft.Text(yazi, color="#FFFFFF", weight="bold", size=13),
        bgcolor=renk,
        padding=padding_degeri,
        border_radius=8,
        on_click=tiklama,
    )


# --- 4. ANA UYGULAMA EKRANI (MOBİL + MASAÜSTÜ DUYARLI) ---
def main(page: ft.Page):
    init_db()
    page.title = "TeklifCepte Pro"
    if os.path.exists("ikon.ico"):
        page.window.icon = os.path.abspath("ikon.ico")
    page.window.width = 1080
    page.window.height = 820
    page.theme_mode = ft.ThemeMode.LIGHT
    page.padding = 16
    page.scroll = ft.ScrollMode.AUTO

    kalemler = []
    secili_kdv = [20]

    def get_ayarlar():
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT firma_adi, firma_tel, firma_iban, pro_mu, kalan_hak, logo_yolu, gecerlilik FROM ayarlar WHERE id=1")
        r = c.fetchone()
        conn.close()
        return {
            "firma_adi": r[0] or "",
            "firma_tel": r[1] or "",
            "firma_iban": r[2] or "",
            "pro_mu": r[3],
            "kalan_hak": r[4],
            "logo_yolu": r[5] or "",
            "gecerlilik": r[6] or "30 Gün"
        }

    ust_logo_kutusu = ft.Container(width=56, height=56, bgcolor="#F1F5F9", border_radius=8, padding=4)
    ust_firma_baslik = ft.Text("", size=18, weight="bold", color="#1E3A8A")
    durum_mesaji = ft.Text("", color="#15803D", weight="bold", size=14)
    paket_etiketi = ft.Text("", weight="bold", size=13)
    icerik_alani = ft.Column(spacing=12)

    def hizli_logo_sec(e):
        yeni_yol = cihazdan_logo_yukle()
        if yeni_yol:
            conn = sqlite3.connect(DB_FILE)
            conn.execute("UPDATE ayarlar SET logo_yolu=? WHERE id=1", (yeni_yol,))
            conn.commit()
            conn.close()
            ust_bilgiyi_yenile()
            durum_mesaji.value = "✅ Kurum logonuz yüklendi!"
            page.update()
        elif not TKINTER_VAR:
            durum_mesaji.value = "ℹ️ Mobil cihazda logo ayarlarını '5. Firma & Pro Paket' sekmesinden yapabilirsiniz."
            page.update()

    # --- EKRAN 1: YENİ TEKLİF HAZIRLA ---
    ilk_ayar = get_ayarlar()
    musteri_adi = ft.TextField(label="Müşteri Adı Soyadı / Firma", width=300)
    musteri_tel = ft.TextField(label="Müşteri WhatsApp No (905...)", width=240)
    urun_adi = ft.TextField(label="Hizmet veya Malzeme Adı", width=280)
    miktar = ft.TextField(label="Miktar", value="1", width=90)
    birim_fiyat = ft.TextField(label="Birim Fiyat (TL)", width=140)
    iskonto_input = ft.TextField(label="İskonto / İndirim (TL)", value="0", width=160)
    gecerlilik_input = ft.TextField(label="Teklif Geçerlilik Süresi", value=ilk_ayar["gecerlilik"], width=180)

    kalem_tablosu = ft.Column(spacing=5)
    ozet_text = ft.Text("Genel Toplam: 0.00 TL", size=18, weight="bold", color="#1E3A8A")
    hazir_butonlar_row = ft.Row(wrap=True, spacing=8)

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

    def ust_bilgiyi_yenile():
        ayar = get_ayarlar()
        f_ad = ayar["firma_adi"] if ayar["firma_adi"] else "Firma Adı Girilmedi"
        ust_firma_baslik.value = f"{f_ad}"
        
        if ayar["logo_yolu"] and os.path.exists(ayar["logo_yolu"]):
            ust_logo_kutusu.content = ft.Image(src=ayar["logo_yolu"], width=48, height=48)
        else:
            ust_logo_kutusu.content = ft.Text("Logo", size=11, color="#64748B")

        if ayar["pro_mu"] == 1:
            paket_etiketi.value = "💎 PRO SÜRÜM (Sınırsız)"
            paket_etiketi.color = "#047857"
        else:
            paket_etiketi.value = f"🎁 ÜCRETSİZ (Kalan PDF: {ayar['kalan_hak']}/5)"
            paket_etiketi.color = "#B45309"

    def guncelle_teklif_ekrani():
        ust_bilgiyi_yenile()
        kalem_tablosu.controls.clear()
        for i, k in enumerate(kalemler):
            def sil_yap(idx=i):
                def _sil(e):
                    kalemler.pop(idx)
                    guncelle_teklif_ekrani()
                return _sil

            kalem_tablosu.controls.append(
                ft.Container(
                    content=ft.Row([
                        ft.Text(f"{i+1}. {k['ad']}", expand=True, weight="bold"),
                        ft.Text(f"{k['miktar']} x {k['fiyat']:,.2f} TL = {k['toplam']:,.2f} TL", weight="bold"),
                        ozel_buton("🗑️", sil_yap(i), "#DC2626", 6)
                    ], wrap=True),
                    padding=8, bgcolor="#F3F4F6", border_radius=6
                )
            )
        ara, isk, kdv_t, genel = hesapla()
        ozet_text.value = f"Ara: {ara:,.2f} TL | KDV (%{secili_kdv[0]}): {kdv_t:,.2f} TL | TOPLAM: {genel:,.2f} TL"
        page.update()

    def hazir_kalemleri_yukle():
        hazir_butonlar_row.controls.clear()
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT ad, fiyat FROM hazir_kalemler")
        for ad, fiy in c.fetchall():
            def hizli_ekle(a=ad, f=fiy):
                def _ekle(e):
                    kalemler.append({"ad": a, "miktar": 1.0, "fiyat": f, "toplam": f})
                    guncelle_teklif_ekrani()
                return _ekle
            hazir_butonlar_row.controls.append(ozel_buton(f"⚡ + {ad} ({fiy:,.0f} TL)", hizli_ekle(), "#475569", 8))
        conn.close()

    def kalem_ekle(e):
        if not urun_adi.value or not birim_fiyat.value:
            durum_mesaji.value = "⚠️ Hizmet adı ve birim fiyat girin!"
            page.update()
            return
        try:
            m = float(miktar.value.replace(",", "."))
            f = float(birim_fiyat.value.replace(",", "."))
            kalemler.append({"ad": urun_adi.value, "miktar": m, "fiyat": f, "toplam": m * f})
            urun_adi.value = ""
            birim_fiyat.value = ""
            miktar.value = "1"
            durum_mesaji.value = ""
            guncelle_teklif_ekrani()
        except ValueError:
            durum_mesaji.value = "⚠️ Miktar ve fiyata sadece sayı girin!"
            page.update()

    def kdv_degistir(oran):
        def _degis(e):
            secili_kdv[0] = oran
            guncelle_teklif_ekrani()
        return _degis

    iskonto_input.on_change = lambda e: guncelle_teklif_ekrani()

    def pdf_olustur_tikla(e):
        try:
            ayar = get_ayarlar()
            if ayar["pro_mu"] == 0 and ayar["kalan_hak"] <= 0:
                durum_mesaji.value = "🔒 Ücretsiz 5 PDF hakkınız doldu! '5. Firma & Pro' sekmesinden Pro'ya geçin."
                page.update()
                return
            if not musteri_adi.value or not kalemler:
                durum_mesaji.value = "⚠️ Lütfen Müşteri Adı girin ve en az 1 hizmet kalemi ekleyin!"
                page.update()
                return

            ara, isk, kdv_t, genel = hesapla()
            dosya_yolu = create_quote_pdf(
                ayar, musteri_adi.value, kalemler, ara, isk, secili_kdv[0], kdv_t, genel,
                gecerlilik_input.value.strip()
            )

            ozet_metni = ", ".join(f"{k['ad']} ({k['miktar']:g}x)" for k in kalemler)
            tarih_str = datetime.now().strftime("%d.%m.%Y %H:%M")

            conn = sqlite3.connect(DB_FILE)
            conn.execute("UPDATE ayarlar SET gecerlilik=? WHERE id=1", (gecerlilik_input.value.strip(),))
            conn.execute(
                "INSERT INTO gecmis_teklifler (musteri, tel, toplam, tarih, dosya_yolu, kalem_ozeti) VALUES (?, ?, ?, ?, ?, ?)",
                (musteri_adi.value.strip(), musteri_tel.value.strip(), genel, tarih_str, dosya_yolu, ozet_metni)
            )
            if ayar["pro_mu"] == 0 and ayar["kalan_hak"] > 0:
                conn.execute("UPDATE ayarlar SET kalan_hak = kalan_hak - 1 WHERE id=1")
            conn.commit()
            conn.close()

            durum_mesaji.value = f"✅ PDF Hazırlandı ve Arşivlendi: {os.path.basename(dosya_yolu)}"
            guncelle_teklif_ekrani()
            if os.name == "nt":
                os.startfile(dosya_yolu)
        except Exception as ex:
            durum_mesaji.value = f"⚠️ PDF hatası: {ex}"
            page.update()

    def whatsapp_gonder(e):
        _, _, _, genel = hesapla()
        ayar = get_ayarlar()
        tel = "".join(filter(str.isdigit, musteri_tel.value))
        if tel.startswith("0"):
            tel = "9" + tel
        mesaj = (
            f"Sayın *{musteri_adi.value}*,\n"
            f"*{ayar['firma_adi']}* olarak hazırladığımız fiyat teklifi genel toplamı *{genel:,.2f} TL*'dir.\n"
            f"Geçerlilik Süresi: {gecerlilik_input.value}\n"
            f"Detaylı PDF teklifimizi ekte bilgilerinize sunarız."
        )
        webbrowser.open(f"https://wa.me/{tel}?text={urllib.parse.quote(mesaj)}")

    def cariye_aktar(e):
        if not musteri_adi.value or not kalemler:
            durum_mesaji.value = "⚠️ Cariye kaydetmek için müşteri adı ve kalem girin!"
            page.update()
            return
        _, _, _, genel = hesapla()
        conn = sqlite3.connect(DB_FILE)
        conn.execute("INSERT INTO cariler (musteri, tel, toplam_borc, odenen, tarih) VALUES (?, ?, ?, 0, ?)",
                     (musteri_adi.value, musteri_tel.value, genel, datetime.now().strftime("%d.%m.%Y")))
        conn.commit()
        conn.close()
        durum_mesaji.value = f"✅ {musteri_adi.value} ({genel:,.2f} TL) Cari Hesaplara kaydedildi!"
        page.update()

    # --- MENÜ GEÇİŞ FONKSİYONLARI ---
    def goster_teklif_ekrani(e=None):
        icerik_alani.controls.clear()
        hazir_kalemleri_yukle()
        guncelle_teklif_ekrani()
        icerik_alani.controls.extend([
            ft.Text("1. Müşteri Bilgileri", weight="bold", size=16),
            ft.Row([musteri_adi, musteri_tel], wrap=True),
            ft.Text("2. Kayıtlı Hizmetlerden Tek Tıkla Ekle:", weight="bold", size=14, color="#475569"),
            hazir_butonlar_row,
            ft.Row([urun_adi, miktar, birim_fiyat, ozel_buton("➕ Ekle", kalem_ekle, "#2563EB")], wrap=True),
            kalem_tablosu,
            ft.Row([
                iskonto_input,
                gecerlilik_input,
                ozel_buton("%0 KDV", kdv_degistir(0), "#64748B", 8),
                ozel_buton("%10 KDV", kdv_degistir(10), "#64748B", 8),
                ozel_buton("%20 KDV", kdv_degistir(20), "#64748B", 8),
            ], wrap=True),
            ft.Divider(),
            ozet_text,
            ft.Row([
                ozel_buton("📄 PDF Oluştur ve Arşivle", pdf_olustur_tikla, "#1E40AF", 12),
                ozel_buton("💬 WhatsApp'tan Gönder", whatsapp_gonder, "#16A34A", 12),
                ozel_buton("📒 İşi Onayla (Cariye Kaydet)", cariye_aktar, "#D97706", 12),
            ], wrap=True, spacing=10)
        ])
        page.update()

    arama_kutusu = ft.TextField(label="🔍 Müşteri Adına Göre Ara...", width=320)

    def goster_gecmis_teklifler(e=None):
        icerik_alani.controls.clear()
        aranan = (arama_kutusu.value or "").strip().lower()

        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT id, musteri, tel, toplam, tarih, dosya_yolu, kalem_ozeti FROM gecmis_teklifler ORDER BY id DESC")
        tum_teklifler = c.fetchall()
        conn.close()

        filtreli = [t for t in tum_teklifler if aranan in (t[1] or "").lower()]
        toplam_teklif_tutari = sum(t[3] for t in filtreli)
        arama_kutusu.on_change = lambda ev: goster_gecmis_teklifler()

        icerik_alani.controls.extend([
            ft.Row([
                ft.Text(f"📂 Geçmiş Teklifler ({len(filtreli)} Adet)", size=18, weight="bold", color="#1E3A8A"),
                ft.Text(f"Toplam Hacim: {toplam_teklif_tutari:,.2f} TL", size=15, weight="bold", color="#047857"),
            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN, wrap=True),
            arama_kutusu,
        ])

        for tid, mus, tel, top, tar, yol, ozet in filtreli:
            def pdf_ac(dosya=yol):
                def _ac(ev):
                    if dosya and os.path.exists(dosya) and os.name == "nt":
                        os.startfile(dosya)
                return _ac

            def arsivden_wp(m=mus, t=tel, tutar=top):
                def _wp(ev):
                    ayar = get_ayarlar()
                    no = "".join(filter(str.isdigit, t or ""))
                    if no.startswith("0"):
                        no = "9" + no
                    msj = f"Sayın *{m}*,\n*{ayar['firma_adi']}* olarak hazırladığımız *{tutar:,.2f} TL* tutarındaki fiyat teklifimizi bilgilerinize sunarız."
                    webbrowser.open(f"https://wa.me/{no}?text={urllib.parse.quote(msj)}")
                return _wp

            def arsivden_cariye(m=mus, t=tel, tutar=top):
                def _aktar(ev):
                    conn2 = sqlite3.connect(DB_FILE)
                    conn2.execute(
                        "INSERT INTO cariler (musteri, tel, toplam_borc, odenen, tarih) VALUES (?, ?, ?, 0, ?)",
                        (m, t, tutar, datetime.now().strftime("%d.%m.%Y"))
                    )
                    conn2.commit()
                    conn2.close()
                    durum_mesaji.value = f"✅ '{m}' ({tutar:,.2f} TL) Cari Hesaplara aktarıldı!"
                    page.update()
                return _aktar

            def arsiv_sil(kayit_id=tid):
                def _sil(ev):
                    conn2 = sqlite3.connect(DB_FILE)
                    conn2.execute("DELETE FROM gecmis_teklifler WHERE id=?", (kayit_id,))
                    conn2.commit()
                    conn2.close()
                    goster_gecmis_teklifler()
                return _sil

            icerik_alani.controls.append(
                ft.Container(
                    content=ft.Row([
                        ft.Column([
                            ft.Text(f"📄 {mus} ({tel or 'Tel Yok'}) | 🕒 {tar}", weight="bold", size=14, color="#1E3A8A"),
                            ft.Text(f"Kalemler: {ozet}", size=12, color="#475569"),
                            ft.Text(f"Tutar: {top:,.2f} TL", weight="bold", size=14, color="#047857"),
                        ], expand=True, spacing=3),
                        ft.Row([
                            ozel_buton("📄 Aç", pdf_ac(), "#1E40AF", 8),
                            ozel_buton("💬 WP", arsivden_wp(), "#16A34A", 8),
                            ozel_buton("📒 Cariye At", arsivden_cariye(), "#D97706", 8),
                            ozel_buton("🗑️", arsiv_sil(), "#DC2626", 8),
                        ], wrap=True, spacing=6)
                    ], wrap=True),
                    padding=10, bgcolor="#F1F5F9", border_radius=8
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
            ft.Text(f"💰 Toplam Bekleyen Alacak: {toplam_kalan:,.2f} TL", size=20, weight="bold", color="#B91C1C")
        )

        for r in kayitlar:
            cid, mus, tel, borc, odenen, tar = r
            kalan = borc - odenen
            tahsilat_kutusu = ft.TextField(label="Tahsilat (TL)", width=120)

            def odeme_al(kayit_id=cid, kutu=tahsilat_kutusu):
                def _ode(ev):
                    try:
                        tutar = float(kutu.value.replace(",", "."))
                        conn2 = sqlite3.connect(DB_FILE)
                        conn2.execute("UPDATE cariler SET odenen = odenen + ? WHERE id=?", (tutar, kayit_id))
                        conn2.commit()
                        conn2.close()
                        durum_mesaji.value = f"✅ {tutar:,.2f} TL tahsilat düşüldü!"
                        goster_cari_ekrani()
                    except ValueError:
                        pass
                return _ode

            def wp_hatirlat(m=mus, t=tel, k=kalan):
                def _wp(ev):
                    ayar = get_ayarlar()
                    if ayar["pro_mu"] == 0:
                        durum_mesaji.value = "🔒 WhatsApp Hatırlatma PRO özelliğidir! Ayarlardan Pro'yu açın."
                        page.update()
                        return
                    no = "".join(filter(str.isdigit, t))
                    if no.startswith("0"):
                        no = "9" + no
                    msj = f"Sayın *{m}*, *{ayar['firma_adi']}* hesabınızda *{k:,.2f} TL* kalan bakiyeniz bulunmaktadır. IBAN: {ayar['firma_iban']}"
                    webbrowser.open(f"https://wa.me/{no}?text={urllib.parse.quote(msj)}")
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
                    content=ft.Row([
                        ft.Column([
                            ft.Text(f"👤 {mus} ({tel}) - {tar}", weight="bold", size=14),
                            ft.Text(f"Toplam: {borc:,.2f} TL | Ödenen: {odenen:,.2f} TL | KALAN: {kalan:,.2f} TL", color="#B91C1C", weight="bold"),
                        ], expand=True),
                        tahsilat_kutusu,
                        ozel_buton("💵 Düş", odeme_al(), "#15803D", 8),
                        ozel_buton("📲 WP Hatırlat", wp_hatirlat(), "#0D9488", 8),
                        ozel_buton("🗑️", cari_sil(), "#DC2626", 8),
                    ], wrap=True),
                    padding=10, bgcolor="#FEF3C7", border_radius=8
                )
            )
        page.update()

    def goster_fiyat_listesi(e=None):
        icerik_alani.controls.clear()
        yeni_ad = ft.TextField(label="Yeni Hizmet / Malzeme Adı", width=300)
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

        icerik_alani.controls.append(ft.Text("📦 Hazır Hizmet & Malzeme Listem", size=18, weight="bold"))
        icerik_alani.controls.append(ft.Row([yeni_ad, yeni_fiyat, ozel_buton("➕ Kaydet", yeni_kaydet, "#2563EB")], wrap=True))

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
                        ft.Text(f"• {ad}", expand=True, weight="bold"),
                        ft.Text(f"{fiy:,.2f} TL", weight="bold", color="#1E3A8A"),
                        ozel_buton("🗑️ Sil", sil_hazir(), "#DC2626", 6)
                    ]),
                    padding=8, bgcolor="#F1F5F9", border_radius=6
                )
            )
        conn.close()
        page.update()

    def goster_ayarlar(e=None):
        icerik_alani.controls.clear()
        ayar = get_ayarlar()

        f_adi = ft.TextField(label="Kendi Firma / Şirket / Usta Adınız", value=ayar["firma_adi"], width=380)
        f_tel = ft.TextField(label="İletişim Telefonunuz", value=ayar["firma_tel"], width=280)
        f_iban = ft.TextField(label="IBAN Numaranız (PDF'te Görünür)", value=ayar["firma_iban"], width=380)

        def kaydet_ayar(ev):
            conn = sqlite3.connect(DB_FILE)
            conn.execute("UPDATE ayarlar SET firma_adi=?, firma_tel=?, firma_iban=? WHERE id=1",
                         (f_adi.value.strip(), f_tel.value.strip(), f_iban.value.strip()))
            conn.commit()
            conn.close()
            ust_bilgiyi_yenile()
            durum_mesaji.value = f"✅ '{f_adi.value.strip()}' olarak firma bilgileriniz kaydedildi!"
            goster_teklif_ekrani()

        def pro_degistir(ev):
            yeni_durum = 0 if ayar["pro_mu"] == 1 else 1
            conn = sqlite3.connect(DB_FILE)
            conn.execute("UPDATE ayarlar SET pro_mu=?, kalan_hak=5 WHERE id=1", (yeni_durum,))
            conn.commit()
            conn.close()
            durum_mesaji.value = "🎉 Paket durumu değiştirildi!"
            ust_bilgiyi_yenile()
            goster_ayarlar()

        icerik_alani.controls.extend([
            ft.Container(
                content=ft.Column([
                    ft.Text("⚙️ Firma Bilgilerini ve Logoyu Düzenle", size=18, weight="bold", color="#1E3A8A"),
                    f_adi,
                    f_tel,
                    f_iban,
                    ft.Row([
                        ozel_buton("🖼️ Cihazdan Logo Seç", hizli_logo_sec, "#0284C7", 12),
                        ozel_buton("💾 Bilgileri Kaydet", kaydet_ayar, "#15803D", 12),
                    ], wrap=True, spacing=10)
                ], spacing=10),
                padding=14, bgcolor="#F8FAFC", border_radius=10
            ),
            ft.Divider(),
            ft.Text("💎 Abonelik ve Para Kazanma Simülasyonu", size=16, weight="bold", color="#7C3AED"),
            ozel_buton(
                "🔄 Ücretsiz Sürüme Dön" if ayar["pro_mu"] == 1 else "💎 PRO SÜRÜME GEÇ (Sınırsız & Reklamsız)",
                pro_degistir, "#7C3AED", 12
            )
        ])
        page.update()

    # ÜST KURUMSAL BAR
    ust_bilgiyi_yenile()
    page.add(
        ft.Container(
            content=ft.Row([
                ft.Row([
                    ust_logo_kutusu,
                    ft.Column([
                        ust_firma_baslik,
                        ft.Row([
                            ozel_buton("🖼️ Logo Yükle", hizli_logo_sec, "#0284C7", 7),
                            ozel_buton("✏️ Firma Değiştir", goster_ayarlar, "#475569", 7),
                        ], wrap=True, spacing=6)
                    ], spacing=4)
                ], spacing=10),
                paket_etiketi
            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN, wrap=True),
            padding=10, bgcolor="#F8FAFC", border_radius=10
        ),
        ft.Row([
            ozel_buton("📝 1. Teklif Hazırla", goster_teklif_ekrani, "#1E3A8A", 10),
            ozel_buton("📂 2. Geçmiş Teklifler", goster_gecmis_teklifler, "#0284C7", 10),
            ozel_buton("📒 3. Cari & Tahsilat", goster_cari_ekrani, "#B45309", 10),
            ozel_buton("📦 4. Fiyat Listem", goster_fiyat_listesi, "#0F766E", 10),
            ozel_buton("⚙️ 5. Firma & Pro", goster_ayarlar, "#6D28D9", 10),
        ], wrap=True, spacing=6),
        durum_mesaji,
        ft.Divider(),
        icerik_alani
    )

    goster_teklif_ekrani()

if hasattr(ft, "run"):
    ft.run(main)
else:
    ft.app(target=main)