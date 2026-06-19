import streamlit as st
import ccxt
import pandas as pd
import yfinance as yf
import threading
import time

# Sayfa Genişlik Ayarı
st.set_page_config(layout="wide", page_title="Borsa Ajanı Pro")

# =================================================================
# 🧠 KÜRESEL HAFIZA (Botun Durumunu ve Cüzdanı Korumak İçin)
# =================================================================
@st.cache_resource
class BotMerkezi:
    def __init__(self):
        self.cuzdan = {"USDT": 500000.0, "VARLIKLAR": {}}
        self.loglar = ["🚀 Otomatik Bot Sistemi Başlatıldı!"]
        self.takip_listesi = ["BTC/USDT", "ETH/USDT", "TSLA", "GC=F"]
        # Sunucu Amerika'da olduğu için Binance yerine Kraken kullanıyoruz:
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
            if rsi < 35: return "GÜÇLÜ AL", "green"
            elif rsi > 65: return "GÜÇLÜ SAT", "red"
            else: return "BEKLE", "gray"
        except: return "VERİ YOK", "blue"

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
            karar, _ = bot_nesnesi.analiz_et(sembol)
            fiyat = bot_nesnesi.fiyat_al(sembol)
            if fiyat == 0: continue

            # Otomatik Alım Stratejisi
            if karar == "GÜÇLÜ AL":
                islem_tutari = 5000.0
                if bot_nesnesi.cuzdan["USDT"] >= islem_tutari:
                    miktar = islem_tutari / fiyat
                    bot_nesnesi.cuzdan["USDT"] -= islem_tutari
                    bot_nesnesi.cuzdan["VARLIKLAR"][sembol] = bot_nesnesi.cuzdan["VARLIKLAR"].get(sembol, 0) + miktar
                    bot_nesnesi.loglar.append(f"✅ [OTOMATİK AL]: {round(miktar,4)} adet {sembol} alındı. Fiyat: {fiyat} USDT")

            # Otomatik Satım Stratejisi
            elif karar == "GÜÇLÜ SAT" and bot_nesnesi.cuzdan["VARLIKLAR"].get(sembol, 0) > 0:
                miktar = bot_nesnesi.cuzdan["VARLIKLAR"][sembol]
                toplam_gelir = miktar * fiyat
                bot_nesnesi.cuzdan["USDT"] += toplam_gelir
                bot_nesnesi.cuzdan["VARLIKLAR"][sembol] = 0
                bot_nesnesi.loglar.append(f"🚨 [OTOMATİK SAT]: Elindeki tüm {sembol} varlıkları satıldı. Gelir: {round(toplam_gelir,2)} USDT")

# Motoru sadece bir kez başlatmak için kontrol
if "motor_calisiyor" not in st.session_state:
    st.session_state.motor_calisiyor = True
    t = threading.Thread(target=arka_plan_motoru, args=(bot,), daemon=True)
    t.start()

# =================================================================
# 📊 STREAMLIT KULLANICI ARAYÜZÜ (UI)
# =================================================================
st.title("📊 Borsa Ajanı Pro — Otomatik Ticaret Paneli")

# Sol Panel: Cüzdan ve Kontroller
col1, col2 = st.columns([1, 2])

with col1:
    st.header("💰 Cüzdan Durumu")
    st.metric(label="Nakit (USDT)", value=f"{round(bot.cuzdan['USDT'], 2)} $")
    
    st.subheader("📦 Sahip Olunan Varlıklar")
    for varlik, miktar in bot.cuzdan["VARLIKLAR"].items():
        if miktar > 0:
            st.write(f"**{varlik}:** {round(miktar, 4)} adet")

    st.write("---")
    st.subheader("➕ Yeni Varlık Ekle")
    yeni_sembol = st.text_input("Örn: AAPL veya SOL/USDT").upper()
    if st.button("Listeye Ekle") and yeni_sembol:
        if yeni_sembol not in bot.takip_listesi:
            bot.takip_listesi.append(yeni_sembol)
            st.success(f"{yeni_sembol} başarıyla eklendi!")
            st.rerun()

# Sağ Panel: Canlı Takip Listesi ve Loglar
with col2:
    st.header("📈 Canlı İzleme Listesi")
    
    # Otomatik Sayfa Yenileme Butonu (Streamlit için)
    if st.button("🔄 Verileri Yenile"):
        st.rerun()

    # Tablo Oluşturma
    piyasa_verileri = []
    for s in bot.takip_listesi:
        karar, renk = bot.analiz_et(s)
        fiyat = bot.fiyat_al(s)
        piyasa_verileri.append({"Sembol": s, "Fiyat (USDT)": round(fiyat, 2), "Sinyal": karar})
    
    df_goster = pd.DataFrame(piyasa_verileri)
    st.dataframe(df_goster, use_container_width=True)

    st.write("---")
    st.header("📜 Bot İşlem Günlüğü (Logs)")
    # En son işlemleri en üstte göstermek için listeyi ters çeviriyoruz
    for log in reversed(bot.loglar[-15:]):
        st.info(log)
