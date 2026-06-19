import streamlit as st
import ccxt
import pandas as pd
import yfinance as yf
import threading
import time
import pandas_ta as ta  
import plotly.graph_objects as go  
from streamlit_autorefresh import st_autorefresh

# Sayfa Genişlik ve Tema Ayarı
st.set_page_config(layout="wide", page_title="Borsa Ajanı Pro v2", page_icon="📊")

# 🔄 EKRANI HER 30 SANİYEDE BİR OTOMATİK YENİLE
st_autorefresh(interval=30000, key="bot_refresh")

# =================================================================
# 🧠 KÜRESEL HAFIZA (Botun Durumunu ve Cüzdanı Korumak İçin)
# =================================================================
@st.cache_resource
class BotMerkezi:
    def __init__(self):
        self.cuzdan = {"USDT": 500000.0, "VARLIKLAR": {}}
        self.maliyetler = {}  
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

    # 🎯 5 Dakikalık Zaman Diliminde Gelişmiş Pine Script Scalp İndikatörü (EMA 50 + Stochastic)
    def scalp_analiz_et(self, sembol):
        try:
            if "/" in sembol:
                df = pd.DataFrame(self.binance.fetch_ohlcv(sembol, '5m', limit=100), columns=['t','o','h','l','c','v'])
            else:
                df = yf.Ticker(sembol).history(period="5d", interval="5m").rename(columns={"Open":"o","High":"h","Low":"l","Close":"c","Volume":"v"})
            
            # 📈 Pine Script Matematik Hesaplamaları
            df['ema50'] = ta.ema(df['c'], length=50)
            stoch = ta.stoch(df['h'], df['l'], df['c'], k=14, d=3, smooth_k=3)
            stoch_k_col = [col for col in stoch.columns if 'STOCHk' in col][0]
            df['stoch_k'] = stoch[stoch_k_col]
            
            son_mum = df.iloc[-1]
            onceki_mum = df.iloc[-2]
            
            # Sinyal Koşulları
            trend_up = son_mum['c'] > son_mum['ema50']
            trend_down = son_mum['c'] < son_mum['ema50']
            
            long_condition = trend_up and (onceki_mum['stoch_k'] < 20) and (son_mum['stoch_k'] >= 20)
            short_condition = trend_down and (onceki_mum['stoch_k'] > 80) and (son_mum['stoch_k'] <= 80)
            
            if long_condition:
                return "🎯 SCALP AL"
            elif short_condition:
                return "📉 SCALP SAT"
            else:
                return "⚪ SİNYAL YOK"
        except:
            return "❔ VERİ YOK"

    # 🖼️ Grafik Çizimi İçin Geçmiş Veriyi Çeken Fonksiyon (Mum Çubukları ve Sinyaller Dahil)
    def grafik_verisi_al(self, sembol):
        try:
            if "/" in sembol:
                df = pd.DataFrame(self.binance.fetch_ohlcv(sembol, '5m', limit=100), columns=['t','o','h','l','c','v'])
                df['Zaman'] = pd.to_datetime(df['t'], unit='ms')
                df = df.set_index('Zaman')
                df = df.rename(columns={"o":"Open", "h":"High", "l":"Low", "c":"Close", "v":"Volume"})
            else:
                df = yf.Ticker(sembol).history(period="5d", interval="5m")
            
            # İndikatörleri dataframe'e ekliyoruz
            df['EMA 50'] = ta.ema(df['Close'], length=50)
            stoch = ta.stoch(df['High'], df['Low'], df['Close'], k=14, d=3, smooth_k=3)
            stoch_k_col = [col for col in stoch.columns if 'STOCHk' in col][0]
            df['Stoch K'] = stoch[stoch_k_col]
            
            # Grafik üzerinde ok işaretleri göstermek için sinyal sütunlarını hesapla
            df['Buy_Signal'] = (df['Close'] > df['EMA 50']) & (df['Stoch K'].shift(1) < 20) & (df['Stoch K'] >= 20)
            df['Sell_Signal'] = (df['Close'] < df['EMA 50']) & (df['Stoch K'].shift(1) > 80) & (df['Stoch K'] <= 80)
            
            return df
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
        time.sleep(15)  
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
                    bot_nesnesi.maliyetler[sembol] = bot_nesnesi.maliyetler.get(sembol, 0.0) + islem_tutari  
                    bot_nesnesi.loglar.append(f"✅ [OTOMATİK AL]: {round(miktar,4)} adet {sembol} alındı. Fiyat: {fiyat} USDT")

            # Otomatik Satım Stratejisi
            elif "GÜÇLÜ SAT" in karar and bot_nesnesi.cuzdan["VARLIKLAR"].get(sembol, 0) > 0:
                miktar = bot_nesnesi.cuzdan["VARLIKLAR"][sembol]
                toplam_gelir = miktar * fiyat
                bot_nesnesi.cuzdan["USDT"] += toplam_gelir
                bot_nesnesi.cuzdan["VARLIKLAR"][sembol] = 0
                bot_nesnesi.maliyetler[sembol] = 0.0  
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
    
    # 🔥 TOPLAM PORTFÖY DEĞERİ VE ANLIK K/Z HESAPLAMA SEGMENTİ
    toplam_varlik_degeri = 0.0
    toplam_portfoy_maliyeti = 0.0
    
    for varlik, miktar in bot.cuzdan["VARLIKLAR"].items():
        if miktar > 0:
            fiyat = bot.fiyat_al(varlik)
            toplam_varlik_degeri += miktar * fiyat
            toplam_portfoy_maliyeti += bot.maliyetler.get(varlik, 0.0)
            
    # Toplam Cüzdan Bakiyesi = Boştaki Nakit (USDT) + Açık Pozisyonların Anlık Değeri
    toplam_bakiye = bot.cuzdan["USDT"] + toplam_varlik_degeri
    # Toplam Kâr/Zarar = Anlık Açık Pozisyon Değeri - O Pozisyonların Alış Maliyeti
    toplam_net_kar_zarar = toplam_varlik_degeri - toplam_portfoy_maliyeti
    
    # Göstergeler için metin formatlama
    kar_zarar_oku = "🟢 +" if toplam_net_kar_zarar >= 0 else "🔴 "
    delta_metni = f"{kar_zarar_oku}{round(toplam_net_kar_zarar, 2)} USDT (Anlık Pozisyonlar)"
    
    # Ana Bakiye ve Boştaki Nakit Bilgisi
    st.metric(label="Toplam Portföy Değeri (Bakiye)", value=f"{round(toplam_bakiye, 2)} USDT", delta=delta_metni)
    st.metric(label="Kullanılabilir Nakit (Boşta)", value=f"{round(bot.cuzdan['USDT'], 2)} USDT", delta="Simülasyon Aktif", delta_color="off")
    
    with st.expander("📦 Sahip Olunan Varlıklar", expanded=True):
        aktif_varlik_var_mi = False
        for varlik, miktar in bot.cuzdan["VARLIKLAR"].items():
            if miktar > 0:
                fiyat = bot.fiyat_al(varlik)
                guncel_deger = miktar * fiyat
                toplam_maliyet = bot.maliyetler.get(varlik, 0.0)
                
                if toplam_maliyet == 0.0:
                    toplam_maliyet = guncel_deger
                
                kar_zarar = guncel_deger - toplam_maliyet
                kar_zarar_yuzde = (kar_zarar / toplam_maliyet) * 100 if toplam_maliyet > 0 else 0
                
                renk = "#00cc66" if kar_zarar >= 0 else "#ff3333"
                ok = "🔺" if kar_zarar >= 0 else "🔻"
                
                st.markdown(f"**{varlik}**")
                st.write(f"Adet: `{round(miktar, 4)}` | Değer: `{round(guncel_deger, 2)} USDT`")
                st.markdown(f"<span style='color:{renk}; font-weight:bold;'>{ok} K/Z: {round(kar_zarar, 2)} USDT ({round(kar_zarar_yuzde, 2)}%)</span>", unsafe_allow_html=True)
                st.markdown("<hr style='margin:10px 0; border:0; border-top:1px solid #444;'/>", unsafe_allow_html=True)
                aktif_varlik_var_mi = True
        if not aktif_varlik_var_mi:
            st.caption("Henüz alım yapılmış bir varlık bulunmuyor.")

    st.write("---")
    st.markdown("### ➕ İzleme Listesine Ekle")
    yeni_sembol = st.text_input("Örn: AAPL, TSLA eller SOL/USDT", placeholder="Sembol girin...").upper()
    if st.button("📌 Listeye Sabitle", use_container_width=True) and yeni_sembol:
        if yeni_sembol not in bot.takip_listesi:
            bot.takip_listesi.append(yeni_sembol)
            st.success(f"{yeni_sembol} listeye eklendi!")
            st.rerun()

with col2:
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
        st.markdown("### 📊 İndikatörlü Canlı Mum Grafiği")
        secilen_grafik = st.selectbox("İncelemek istediğiniz finansal varlığı seçin:", bot.takip_listesi)
        
        if secilen_grafik:
            with st.spinner("Piyasa, Mum çubukları ve indikatörler işleniyor..."):
                g_data = bot.grafik_verisi_al(secilen_grafik)
                if g_data is not None and not g_data.empty:
                    
                    fig = go.Figure()
                    
                    # 1. Mum Çubukları (Candlesticks)
                    fig.add_trace(go.Candlestick(
                        x=g_data.index, open=g_data['Open'], high=g_data['High'],
                        low=g_data['Low'], close=g_data['Close'], name="Fiyat"
                    ))
                    
                    # 2. Pine Script Trend Filtresi (EMA 50)
                    fig.add_trace(go.Scatter(
                        x=g_data.index, y=g_data['EMA 50'], 
                        line=dict(color='orange', width=1.5), name="50 EMA"
                    ))
                    
                    # 3. AL Sinyali İşaretçileri (Yeşil Oklar)
                    buys = g_data[g_data['Buy_Signal']]
                    fig.add_trace(go.Scatter(
                        x=buys.index, y=buys['Close'] * 0.995, 
                        mode='markers', marker=dict(symbol='triangle-up', size=12, color='#00cc66'),
                        name="Ajan AL"
                    ))
                    
                    # 4. SAT Sinyali İşaretçileri (Kırmızı Oklar)
                    sells = g_data[g_data['Sell_Signal']]
                    fig.add_trace(go.Scatter(
                        x=sells.index, y=sells['Close'] * 1.005, 
                        mode='markers', marker=dict(symbol='triangle-down', size=12, color='#ff3333'),
                        name="Ajan SAT"
                    ))
                    
                    fig.update_layout(
                        xaxis_rangeslider_visible=False,
                        template="plotly_dark",
                        height=500,
                        margin=dict(l=20, r=20, t=20, b=20)
                    )
                    
                    st.plotly_chart(fig, use_container_width=True)
                    st.caption("💡 *Grafikteki üçgenler: Gönderdiğiniz Pine Script kodunun (50 EMA ve Stochastic 14,3,3) ürettiği gerçek scalp kesişim noktalarıdır.*")
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
