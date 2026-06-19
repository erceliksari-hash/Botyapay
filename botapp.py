with st.expander("📦 Sahip Olunan Varlıklar", expanded=True):
        aktif_varlik_var_mi = False
        for varlik, miktar in list(bot.cuzdan["VARLIKLAR"].items()):
            if miktar > 0:
                fiyat = bot.fiyat_al(varlik)
                if fiyat == 0:
                    continue
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
