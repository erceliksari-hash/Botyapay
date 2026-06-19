import streamlit as st
import ccxt
import pandas as pd
import yfinance as yf
import threading
import time

# Sayfa Genişlik ve Tema Ayarı
st.set_page_config(layout="wide", page_title="Borsa Ajanı Pro v2", page_icon="📊")

# =================================================================
# 🧠 KÜRESEL HAFIZA (Botun Durumunu ve Cüzdanı Korumak İçin)
# =================================================================
@st.cache_resource
class BotMerkezi:
    def __init__(self):
        self.cuzdan = {"USDT": 500000.0, "VARLIKLAR": {}}
        self.loglar = ["🚀 Otomatik Bot Sistemi Başlatıldı!"]
        self.takip_listesi = ["BTC/USDT", "ETH/USDT", "TSLA", "GC=F"]
        # Sunucu Amerika'da olduğu için engelsiz Kraken borsasını kullanıyoruz
        self.binance = ccxt.kraken()

    def rsi_hesapla(self, seri, periyot=14):
        delta = seri.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=periyot).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=periyot).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs))

    def analiz_et(self, sembol):
        try:
            if "/" in sembol:
                df = pd.DataFrame(self.binance.fetch_ohlcv(sembol, '1h', limit=50), columns=['t','o','h','l','c','v'])
            else:
                df = yf.Ticker(sembol).history(period="5d", interval="1h").rename(columns={"Close":"c"})
            rsi = self.rsi_hesapla(df['c']).iloc[-1]
            if rsi < 35: return "🟢 GÜÇLÜ AL"
            elif rsi > 65: return "🔴 GÜÇLÜ SAT"
            else: return "⚪ BEKLE"
        except: return "❔ VERİ YOK"

    # 🎯 5 Dakikalık Zaman Diliminde Hızlı Scalp İndikatörü (5/13 EMA)
    def scalp_analiz_et(self, sembol):
        try:
            if "/" in sembol:
                df = pd.DataFrame(self.binance.fetch_ohlcv(sembol, '5m', limit=30), columns=['t','o','h','l','c','v'])
            else:
                df = yf.Ticker(sembol).history(period="1d", interval="5m").rename(columns={"Close":"c"})
            
            # EMA Hesaplamaları
            df['ema5'] = df['c'].ewm(span=5, adjust=False).mean()
            df['ema13'] = df['c'].ewm(span=13, adjust=False).mean()
            
            if df['ema5'].iloc[-1] > df['ema13'].iloc[-1]:
                return "🎯 SCALP AL"
            else:
                return "📉 SCALP SAT"
        except:
            return "❔ VERİ YOK"

    # 🔥 KENDİ İNDİKATÖRÜNÜ GRAFİĞE EKLEME ALANI
    # Bu fonksiyon grafik ekranına basılacak olan veri tablosunu hazırlar.
    def grafik_verisi_al(self, sembol):
        try:
            if "/" in sembol:
                df = pd.DataFrame(self.binance.fetch_ohlcv(sembol, '5m', limit=50), columns=['t','o','h','l','c','v'])
                df['Zaman'] = pd.to_datetime(df['t'], unit='ms')
                df = df.set_index('Zaman')
                df['Fiyat'] = df['c']
            else:
                df = yf.Ticker(sembol).history(period="1d", interval="5m").rename(columns={"Close":"Fiyat"})
            
            # Kendi indikatör seviyelerini burada hesaplayıp tabloya ekliyoruz:
            df['Scalp EMA 5'] = df['Fiyat'].ewm(span=5, adjust=False).mean()
            df['Scalp EMA 13'] = df['Fiyat'].ewm(span=13, adjust=False).mean()
            
            # 💡 İleride buraya df['BenimIndikatorum'] = ... yazarak grafiğe yeni çizgiler ekleyebilirsin!
            return df[['Fiyat', 'Scalp EMA 5', 'Scalp EMA 13']]
        except:
            return None

    def fiyat_al(self, sembol):
        try:
            if "/" in sembol: return self.binance.fetch_ticker(sembol)['last']
            return yf.Ticker(sembol).history(period="1d")['Close'].iloc[-1]
        except: return 0

# Hafıza Nesnesini Çağır
bot = BotMerkezi()

# =================================================================
# 🤖 7/24 ARKA PLAN MOTORU (Thread Kontrolü)
# =================================================================
def arka_plan_motoru(bot_nesnesi):
    while True:
        time.sleep(15)  # 15 saniyede bir piyasayı tara
        for sembol in list(bot_nesnesi.takip_listesi):
            karar = bot_nesnesi.analiz_et(sembol)
            fiyat = bot_nesnesi.fiyat_al(sembol)
            if fiyat == 0: continue

            # Otomatik Alım Stratejisi
            if "GÜÇLÜ AL" in karar:
                islem_tutari = 5000.0
                if bot_nesnesi.cuzdan["USDT"] >= islem_tutari:
                    miktar = islem_tutari / fiyat
                    bot_nesnesi.cuzdan["USDT"] -= islem_tutari
                    bot_nesnesi.cuzdan["VARLIKLAR"][sembol] = bot_nesnesi.cuzdan["VARLIKLAR"].get(sembol, 0) + miktar
                    bot_nesnesi.loglar.append(f"✅ [OTOMATİK AL]: {round(miktar,4)} adet {sembol} alındı. Fiyat: {fiyat} USDT")

            # Otomatik Satım Stratejisi
            elif "GÜÇLÜ SAT" in karar and bot_nesnesi.cuzdan["VARLIKLAR"].get(sembol, 0) > 0:
                miktar = bot_nesnesi.cuzdan["VARLIKLAR"][sembol]
                toplam_gelir = miktar * fiyat
                bot_nesnesi.cuzdan["USDT"] += toplam_gelir
                bot_nesnesi.cuzdan["VARLIKLAR"][sembol] = 0
                bot_nesnesi.loglar.append(f"🚨 [OTOMATİK SAT]: Elindeki tüm {sembol} varlıkları satıldı. Gelir: {round(toplam_gelir,2)} USDT")

if "motor_calisiyor" not in st.session_state:
    st.session_state.motor_calisiyor = True
    t = threading.Thread(target=arka_plan_motoru, args=(bot,), daemon=True)
    t.start()

# =================================================================
# 📊 STREAMLIT KULLANICI ARAYÜZÜ (UI)
# =================================================================
st.subheader("🤖 BORSA AJANI PRO — Gelişmiş Algoritmik İşlem Paneli")

# Düzen: Sol Panel (Cüzdan ve Kontroller) | Sağ Panel (Görsel Sekmeler)
col1, col2 = st.columns([1, 3], gap="large")

with col1:
    st.markdown("### 💰 Portföy Durumu")
    st.metric(label="Kullanılabilir Nakit", value=f"{round(bot.cuzdan['USDT'], 2)} USDT", delta="Simülasyon Aktif")
    
    with st.expander("📦 Sahip Olunan Varlıklar", expanded=True):
        aktif_varlik_var_mi = False
        for varlik, miktar in bot.cuzdan["VARLIKLAR"].items():
            if miktar > 0:
                st.write(f"**{varlik}:** `{round(miktar, 4)}` adet")
                aktif_varlik_var_mi = True
        if not aktif_varlik_var_mi:
            st.caption("Henüz alım yapılmış bir varlık bulunmuyor.")

    st.write("---")
    st.markdown("### ➕ İzleme Listesine Ekle")
    yeni_sembol = st.text_input("Örn: AAPL, TSLA veya SOL/USDT", placeholder="Sembol girin...").upper()
    if st.button("📌 Listeye Sabitle", use_container_width=True) and yeni_sembol:
        if yeni_sembol not in bot.takip_listesi:
            bot.takip_listesi.append(yeni_sembol)
            st.success(f"{yeni_sembol} listeye eklendi!")
            st.rerun()

with col2:
    # 👑 PREMIUM TAB TASARIMI
    tab1, tab2, tab3 = st.tabs(["📈 Canlı Sinyal Masası", "🔍 Gelişmiş Grafik Paneli", "📜 İşlem Günlüğü (Logs)"])

    with tab1:
        st.markdown("### ⚡ Anlık Piyasa Taraması")
        if st.button("🔄 Verileri Şimdi Güncelle", use_container_width=True):
            st.rerun()

        piyasa_verileri = []
        for s in bot.takip_listesi:
            ana_sinyal = bot.analiz_et(s)
            scalp_sinyal = bot.scalp_analiz_et(s)
            fiyat = bot.fiyat_al(s)
            
            tv_id = s.replace("/USDT", "USDT")
            tv_link = f"https://www.tradingview.com/symbols/{tv_id}/"
            
            piyasa_verileri.append({
                "Sembol": s, 
                "Anlık Fiyat (USDT)": round(fiyat, 2), 
                "Ana Trend (1h)": ana_sinyal,
                "Scalp Durumu (5m)": scalp_sinyal,
                "Grafik Linki": tv_link
            })
        
        df_goster = pd.DataFrame(piyasa_verileri)
        st.dataframe(
            df_goster, 
            use_container_width=True,
            hide_index=True,
            column_config={
                "Grafik Linki": st.column_config.LinkColumn("🔗 Analiz", display_text="TradingView Grafiği")
            }
        )

    with tab2:
        st.markdown("### 📊 İndikatörlü Canlı Çizgi Grafik")
        secilen_grafik = st.selectbox("İncelemek istediğiniz finansal varlığı seçin:", bot.takip_listesi)
        
        if secilen_grafik:
            with st.spinner("Piyasa ve indikatör verileri işleniyor..."):
                g_data = bot.grafik_verisi_al(secilen_grafik)
                if g_data is not None and not g_data.empty:
                    # 💡 Burası hem fiyatı hem de EMA 5 ve EMA 13 indikatör çizgilerini aynı grafikte üst üste çizer!
                    st.line_chart(g_data, use_container_width=True)
                    st.caption("💡 *Grafikteki çizgiler: Ham Fiyat seviyenizi ve hesaplanan Scalp İndikatörlerinizin (EMA5 / EMA13) çakışma bölgelerini temsil eder.*")
                else:
                    st.error("Grafik verisi alınamadı. Sembolün doğruluğunu veya internet bağlantısını kontrol edin.")

    with tab3:
        st.markdown("### 📜 Robotun Son Karar Mekanizmaları")
        for log in reversed(bot.loglar[-20:]):
            if "AL" in log:
                st.success(log)
            elif "SAT" in log:
                st.error(log)
            else:
                st.info(log)
