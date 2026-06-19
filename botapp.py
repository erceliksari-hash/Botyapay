import streamlit as st
import ccxt
import pandas as pd
import yfinance as yf
import threading
import time
import traceback
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh

# Sayfa Genişlik ve Tema Ayarı
st.set_page_config(layout="wide", page_title="Borsa Ajanı Pro v2", page_icon="📊")

# 🔄 EKRANI HER 30 SANİYEDE BİR OTOMATİK YENİLE
st_autorefresh(interval=30000, key="bot_refresh")

# =================================================================
# 📐 İNDİKATÖR FONKSİYONLARI (pandas_ta yerine elle hesaplama)
# -----------------------------------------------------------------
# DÜZELTME: pandas_ta kütüphanesi güncel numpy sürümleriyle
# (numpy >= 1.24) uyumsuz olduğu için ImportError ile uygulamayı
# tamamen çökertiyordu (numpy.NaN artık mevcut değil).
# Bu yüzden EMA ve Stochastic indikatörleri sade pandas ile
# elle hesaplanıyor; harici bağımlılık riski ortadan kalkıyor.
# =================================================================
def ema_hesapla(seri, periyot):
    return seri.ewm(span=periyot, adjust=False).mean()


def stochastic_k_hesapla(high, low, close, k=14, smooth_k=3):
    en_dusuk = low.rolling(window=k).min()
    en_yuksek = high.rolling(window=k).max()
    aralik = (en_yuksek - en_dusuk).replace(0, pd.NA)  # 0'a bölme hatasını engelle
    ham_k = 100 * (close - en_dusuk) / aralik
    return ham_k.rolling(window=smooth_k).mean()


def rsi_hesapla(seri, periyot=14):
    delta = seri.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=periyot).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=periyot).mean()
    rs = gain / loss.replace(0, pd.NA)
    return 100 - (100 / (1 + rs))


# =================================================================
# 🧠 KÜRESEL HAFIZA (Botun Durumunu ve Cüzdanı Korumak İçin)
# =================================================================
@st.cache_resource
class BotMerkezi:
    def __init__(self):
        self.cuzdan = {"USDT": 500000.0, "VARLIKLAR": {}}
        self.maliyetler = {}  # Alış maliyetlerini izlemek için havuz
        self.loglar = ["🚀 Otomatik Bot Sistemi Başlatıldı!"]
        self.takip_listesi = ["BTC/USDT", "ETH/USDT", "TSLA", "GC=F"]
        # Sunucu Amerika'da olduğu için engelsiz Kraken borsasını kullanıyoruz
        # DÜZELTME: enableRateLimit eklendi -> API hız sınırı / ban riski azaltıldı
        self.binance = ccxt.kraken({"enableRateLimit": True})

        # DÜZELTME: Arka plan motorunun sadece BİR KEZ başlatılmasını
        # garanti etmek için bot nesnesinin kendi üzerinde durum ve kilit tutuluyor.
        # (Önceden st.session_state kullanılıyordu; bu, her yeni sekme/oturum
        # için ayrı bir thread başlatıp aynı paylaşılan cüzdanı eşzamanlı
        # değiştirme riski oluşturuyordu.)
        self.motor_baslatildi = False
        self.kilit = threading.Lock()

    def log_ekle(self, mesaj):
        with self.kilit:
            self.loglar.append(mesaj)

    def analiz_et(self, sembol):
        try:
            if "/" in sembol:
                df = pd.DataFrame(
                    self.binance.fetch_ohlcv(sembol, "1h", limit=50),
                    columns=["t", "o", "h", "l", "c", "v"],
                )
            else:
                df = yf.Ticker(sembol).history(period="5d", interval="1h").rename(columns={"Close": "c"})

            if df is None or df.empty or len(df) < 16:
                return "❔ VERİ YOK"

            rsi = rsi_hesapla(df["c"]).iloc[-1]
            if pd.isna(rsi):
                return "❔ VERİ YOK"
            if rsi < 35:
                return "🟢 GÜÇLÜ AL"
            elif rsi > 65:
                return "🔴 GÜÇLÜ SAT"
            else:
                return "⚪ BEKLE"
        except Exception as e:
            # DÜZELTME: Sessiz "except:" yerine hata loglara yazılıyor
            self.log_ekle(f"⚠️ [analiz_et hata] {sembol}: {e}")
            return "❔ VERİ YOK"

    # 🎯 5 Dakikalık Zaman Diliminde Gelişmiş Scalp İndikatörü (EMA 50 + Stochastic)
    def scalp_analiz_et(self, sembol):
        try:
            if "/" in sembol:
                df = pd.DataFrame(
                    self.binance.fetch_ohlcv(sembol, "5m", limit=100),
                    columns=["t", "o", "h", "l", "c", "v"],
                )
            else:
                df = (
                    yf.Ticker(sembol)
                    .history(period="5d", interval="5m")
                    .rename(columns={"Open": "o", "High": "h", "Low": "l", "Close": "c", "Volume": "v"})
                )

            if df is None or df.empty or len(df) < 20:
                return "❔ VERİ YOK"

            df["ema50"] = ema_hesapla(df["c"], 50)
            df["stoch_k"] = stochastic_k_hesapla(df["h"], df["l"], df["c"], k=14, smooth_k=3)

            son_mum = df.iloc[-1]
            onceki_mum = df.iloc[-2]

            if pd.isna(son_mum["stoch_k"]) or pd.isna(onceki_mum["stoch_k"]) or pd.isna(son_mum["ema50"]):
                return "❔ VERİ YOK"

            trend_up = son_mum["c"] > son_mum["ema50"]
            trend_down = son_mum["c"] < son_mum["ema50"]

            long_condition = trend_up and (onceki_mum["stoch_k"] < 20) and (son_mum["stoch_k"] >= 20)
            short_condition = trend_down and (onceki_mum["stoch_k"] > 80) and (son_mum["stoch_k"] <= 80)

            if long_condition:
                return "🎯 SCALP AL"
            elif short_condition:
                return "📉 SCALP SAT"
            else:
                return "⚪ SİNYAL YOK"
        except Exception as e:
            self.log_ekle(f"⚠️ [scalp_analiz_et hata] {sembol}: {e}")
            return "❔ VERİ YOK"

    # 🖼️ Grafik Çizimi İçin Geçmiş Veriyi Çeken Fonksiyon
    def grafik_verisi_al(self, sembol):
        try:
            if "/" in sembol:
                df = pd.DataFrame(
                    self.binance.fetch_ohlcv(sembol, "5m", limit=100),
                    columns=["t", "o", "h", "l", "c", "v"],
                )
                df["Zaman"] = pd.to_datetime(df["t"], unit="ms")
                df = df.set_index("Zaman")
                df = df.rename(columns={"o": "Open", "h": "High", "l": "Low", "c": "Close", "v": "Volume"})
            else:
                df = yf.Ticker(sembol).history(period="5d", interval="5m")

            if df is None or df.empty or len(df) < 20:
                return None

            df["EMA 50"] = ema_hesapla(df["Close"], 50)
            df["Stoch K"] = stochastic_k_hesapla(df["High"], df["Low"], df["Close"], k=14, smooth_k=3)

            df["Buy_Signal"] = (
                (df["Close"] > df["EMA 50"])
                & (df["Stoch K"].shift(1) < 20)
                & (df["Stoch K"] >= 20)
            )
            df["Sell_Signal"] = (
                (df["Close"] < df["EMA 50"])
                & (df["Stoch K"].shift(1) > 80)
                & (df["Stoch K"] <= 80)
            )

            return df
        except Exception as e:
            self.log_ekle(f"⚠️ [grafik_verisi_al hata] {sembol}: {e}")
            return None

    def fiyat_al(self, sembol):
        try:
            if "/" in sembol:
                return self.binance.fetch_ticker(sembol)["last"]
            return yf.Ticker(sembol).history(period="1d")["Close"].iloc[-1]
        except Exception as e:
            self.log_ekle(f"⚠️ [fiyat_al hata] {sembol}: {e}")
            return 0


# Hafıza Nesnesini Çağır
bot = BotMerkezi()

# =================================================================
# 🤖 7/24 ARKA PLAN MOTORU (Thread Kontrolü)
# =================================================================
def arka_plan_motoru(bot_nesnesi):
    while True:
        time.sleep(15)  # 15 saniyede bir piyasayı tara
        for sembol in list(bot_nesnesi.takip_listesi):
            try:
                karar = bot_nesnesi.analiz_et(sembol)
                fiyat = bot_nesnesi.fiyat_al(sembol)
                if fiyat == 0:
                    continue

                with bot_nesnesi.kilit:
                    sahip_olunan = bot_nesnesi.cuzdan["VARLIKLAR"].get(sembol, 0)

                    # Otomatik Alım Stratejisi
                    # DÜZELTME: Sinyal "GÜÇLÜ AL" olarak kaldığı her 15 saniyede
                    # tekrar tekrar 5000 USDT'lik alım yapılıyordu (nakit bitene kadar).
                    # Artık zaten pozisyon varsa yeni alım yapılmıyor.
                    if "GÜÇLÜ AL" in karar and sahip_olunan == 0:
                        islem_tutari = 5000.0
                        if bot_nesnesi.cuzdan["USDT"] >= islem_tutari:
                            miktar = islem_tutari / fiyat
                            bot_nesnesi.cuzdan["USDT"] -= islem_tutari
                            bot_nesnesi.cuzdan["VARLIKLAR"][sembol] = (
                                bot_nesnesi.cuzdan["VARLIKLAR"].get(sembol, 0) + miktar
                            )
                            bot_nesnesi.maliyetler[sembol] = (
                                bot_nesnesi.maliyetler.get(sembol, 0.0) + islem_tutari
                            )
                            bot_nesnesi.loglar.append(
                                f"✅ [OTOMATİK AL]: {round(miktar, 4)} adet {sembol} alındı. Fiyat: {fiyat} USDT"
                            )

                    # Otomatik Satım Stratejisi
                    elif "GÜÇLÜ SAT" in karar and sahip_olunan > 0:
                        miktar = sahip_olunan
                        toplam_gelir = miktar * fiyat
                        bot_nesnesi.cuzdan["USDT"] += toplam_gelir
                        bot_nesnesi.cuzdan["VARLIKLAR"][sembol] = 0
                        bot_nesnesi.maliyetler[sembol] = 0.0
                        bot_nesnesi.loglar.append(
                            f"🚨 [OTOMATİK SAT]: Elindeki tüm {sembol} varlıkları satıldı. Gelir: {round(toplam_gelir, 2)} USDT"
                        )
            except Exception as e:
                # DÜZELTME: Arka plan motorunda yakalanmayan bir hata
                # tüm thread'i sessizce öldürebiliyordu. Artık loglanıp devam ediliyor.
                bot_nesnesi.log_ekle(f"⚠️ [arka_plan_motoru hata] {sembol}: {e}\n{traceback.format_exc()}")


# DÜZELTME: Thread başlatma artık st.session_state üzerinden değil,
# bot nesnesinin kendi kilidi ve bayrağı üzerinden kontrol ediliyor.
# Böylece kaç tane sekme/oturum açılırsa açılsın motor sadece BİR KEZ başlar.
with bot.kilit:
    if not bot.motor_baslatildi:
        bot.motor_baslatildi = True
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
                st.markdown(
                    f"<span style='color:{renk}; font-weight:bold;'>{ok} K/Z: {round(kar_zarar, 2)} USDT ({round(kar_zarar_yuzde, 2)}%)</span>",
                    unsafe_allow_html=True,
                )
                st.markdown("<hr style='margin:10px 0; border:0; border-top:1px solid #444;'/>", unsafe_allow_html=True)
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

            piyasa_verileri.append(
                {
                    "Sembol": s,
                    "Anlık Fiyat (USDT)": round(fiyat, 2),
                    "Ana Trend (1h)": ana_sinyal,
                    "Scalp Durumu (5m)": scalp_sinyal,
                    "Grafik Linki": tv_link,
                }
            )

        df_goster = pd.DataFrame(piyasa_verileri)
        st.dataframe(
            df_goster,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Grafik Linki": st.column_config.LinkColumn("🔗 Analiz", display_text="TradingView Grafiği")
            },
        )

    with tab2:
        st.markdown("### 📊 İndikatörlü Canlı Mum Grafiği")
        secilen_grafik = st.selectbox("İncelemek istediğiniz finansal varlığı seçin:", bot.takip_listesi)

        if secilen_grafik:
            with st.spinner("Piyasa, Mum çubukları ve indikatörler işleniyor..."):
                g_data = bot.grafik_verisi_al(secilen_grafik)
                if g_data is not None and not g_data.empty:
                    fig = go.Figure()

                    fig.add_trace(
                        go.Candlestick(
                            x=g_data.index,
                            open=g_data["Open"],
                            high=g_data["High"],
                            low=g_data["Low"],
                            close=g_data["Close"],
                            name="Fiyat",
                        )
                    )

                    fig.add_trace(
                        go.Scatter(
                            x=g_data.index,
                            y=g_data["EMA 50"],
                            line=dict(color="orange", width=1.5),
                            name="50 EMA",
                        )
                    )

                    buys = g_data[g_data["Buy_Signal"]]
                    fig.add_trace(
                        go.Scatter(
                            x=buys.index,
                            y=buys["Close"] * 0.995,
                            mode="markers",
                            marker=dict(symbol="triangle-up", size=12, color="#00cc66"),
                            name="Ajan AL",
                        )
                    )

                    sells = g_data[g_data["Sell_Signal"]]
                    fig.add_trace(
                        go.Scatter(
                            x=sells.index,
                            y=sells["Close"] * 1.005,
                            mode="markers",
                            marker=dict(symbol="triangle-down", size=12, color="#ff3333"),
                            name="Ajan SAT",
                        )
                    )

                    fig.update_layout(
                        xaxis_rangeslider_visible=False,
                        template="plotly_dark",
                        height=500,
                        margin=dict(l=20, r=20, t=20, b=20),
                    )

                    st.plotly_chart(fig, use_container_width=True)
                    st.caption(
                        "💡 *Grafikteki üçgenler: 50 EMA ve Stochastic (14,3,3) kesişiminden üretilen scalp sinyal noktalarıdır.*"
                    )
                else:
                    st.error("Grafik verisi alınamadı. Sembolün doğruluğunu veya internet bağlantısını kontrol edin.")

    with tab3:
        st.markdown("### 📜 Robotun Son Karar Mekanizmaları")
        for log in reversed(bot.loglar[-30:]):
            if "hata" in log.lower() or "⚠️" in log:
                st.warning(log)
            elif "AL" in log:
                st.success(log)
            elif "SAT" in log:
                st.error(log)
            else:
                st.info(log)
