# app.py
import streamlit as st
import pandas as pd
import ccxt
import joblib
import json
import db # Veritabanı scriptimizi import ediyoruz
from datetime import datetime

# --- Sayfa Konfigürasyonu ---
st.set_page_config(layout="wide", page_title="AI Paper Trader")

# --- Model ve Yardımcı Fonksiyonlar ---

# Modeli ve konfigürasyonu sadece bir kez yükle
@st.cache_resource
def load_model_and_config():
    model = joblib.load('data/trading_model.joblib')
    with open('data/model_config.json', 'r') as f:
        config = json.load(f)
    return model, config

# Özellik hesaplama fonksiyonu (kripto için uyarlanmış)
def calculate_crypto_features(df, btc_df, features_list):
    # Bu fonksiyon, daha önceki kripto modelimizdekiyle aynı olmalı
    # Buraya BIST yerine kripto modelini eğitirken kullandığınız 
    # calculate_features fonksiyonunu yapıştırın.
    # Örnek olarak temel bir versiyon ekliyorum:
    if df is None or btc_df is None or df.empty or btc_df.empty: return None
    common_index = df.index.intersection(btc_df.index)
    df = df.loc[common_index]; btc_df = btc_df.loc[common_index]
    if df.empty or len(df) < 50: return None
    if 'relative_strength' in features_list: df['relative_strength'] = df['close'] / btc_df['close']
    if 'rolling_corr_btc' in features_list: df['rolling_corr_btc'] = df['close'].pct_change().rolling(window=50).corr(btc_df['close'].pct_change())
    # ... Diğer özellikler (RSI, MACD vb.) buraya eklenmeli ...
    df.ffill(inplace=True)
    df.dropna(inplace=True)
    return df

# Canlı veri çeken fonksiyon
@st.cache_data(ttl=60) # Veriyi 60 saniye boyunca cache'le
def fetch_live_data(symbol, btc_symbol='BTC/USDT', timeframe='4h', limit=100):
    exchange = ccxt.binance()
    btc_ohlcv = exchange.fetch_ohlcv(btc_symbol, timeframe, limit=limit)
    coin_ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
    
    btc_df = pd.DataFrame(btc_ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    btc_df['timestamp'] = pd.to_datetime(btc_df['timestamp'], unit='ms')
    btc_df.set_index('timestamp', inplace=True)
    
    coin_df = pd.DataFrame(coin_ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    coin_df['timestamp'] = pd.to_datetime(coin_df['timestamp'], unit='ms')
    coin_df.set_index('timestamp', inplace=True)
    return coin_df, btc_df

# --- UYGULAMA BAŞLANGICI ---

# Modeli ve DB'yi yükle/kur
model, config = load_model_and_config()
db.setup_database()

# Başlık
st.title("Gemini AI Paper Trader 🤖")

# Takip edilecek popüler coin'ler
COIN_LIST = ['ETH/USDT', 'BNB/USDT', 'SOL/USDT', 'XRP/USDT', 'DOGE/USDT', 'ADA/USDT', 'AVAX/USDT', 'SHIB/USDT', 'DOT/USDT', 'MATIC/USDT']

# --- Dashboard Alanı ---
balance = db.get_wallet_balance()
open_positions = db.get_positions(is_open=True)

open_positions_value = 0
if not open_positions.empty:
    # Anlık fiyatları çekip pozisyon değerini hesapla (basitleştirilmiş)
    # Gerçek bir uygulamada bu da periyodik olarak güncellenmeli
    open_positions_value = (open_positions['amount'] * open_positions['entry_price']).sum()

col1, col2, col3 = st.columns(3)
col1.metric("Sanal Cüzdan (USDT)", f"{balance:.2f}")
col2.metric("Açık Pozisyon Değeri", f"{open_positions_value:.2f}")
col3.metric("Toplam Varlık", f"{balance + open_positions_value:.2f}")

st.markdown("---")

# --- Ana İşlem Alanı ---
col_main1, col_main2 = st.columns([1, 2])

with col_main1:
    st.subheader("İşlem Paneli")
    selected_coin = st.selectbox("İşlem Yapılacak Coin:", COIN_LIST)
    
    amount_to_invest = st.number_input("Yatırım Miktarı (USDT):", min_value=10.0, value=100.0, step=10.0)

    if st.button("📈 POZİSYON AÇ (AL)", use_container_width=True):
        if amount_to_invest > balance:
            st.error("Yetersiz bakiye!")
        else:
            try:
                coin_df, _ = fetch_live_data(selected_coin)
                current_price = coin_df['close'].iloc[-1]
                db.open_new_position(selected_coin, amount_to_invest, current_price)
                st.success(f"{selected_coin} için {amount_to_invest:.2f} USDT'lik pozisyon açıldı!")
                st.rerun() # Sayfayı yenileyerek cüzdanı ve pozisyonları güncelle
            except Exception as e:
                st.error(f"İşlem sırasında hata: {e}")

    # Canlı Veri ve Tahmin Alanı
    if selected_coin:
        st.markdown("---")
        st.subheader(f"{selected_coin} Analizi")
        try:
            coin_df, btc_df = fetch_live_data(selected_coin)
            current_price = coin_df['close'].iloc[-1]
            st.metric("Mevcut Fiyat", f"{current_price:.4f}")

            processed_df = calculate_crypto_features(coin_df.copy(), btc_df.copy(), config['features'])
            if processed_df is not None and not processed_df.empty:
                latest_features = processed_df[config['features']].iloc[-1:]
                probability = model.predict_proba(latest_features)[0, 1]
                
                st.write("AI Model Tahmini:")
                st.progress(probability, text=f"Al Sinyali Olasılığı: {probability:.2%}")
                if probability < config['chosen_threshold']:
                    st.info("Model şu an için alım önermiyor.", icon="ℹ️")
                else:
                    st.warning("Model bu coin için potansiyel bir alım sinyali tespit etti!", icon="🔥")

        except Exception as e:
            st.error(f"Veri çekilirken veya tahmin yapılırken hata oluştu: {e}")


with col_main2:
    st.subheader("Açık Pozisyonlar")
    if open_positions.empty:
        st.info("Şu anda açık pozisyonunuz bulunmamaktadır.")
    else:
        for index, pos in open_positions.iterrows():
            with st.expander(f"{pos['symbol']} - {pos['amount']:.4f} adet"):
                entry_price = pos['entry_price']
                
                # Anlık fiyatı çekmek için basit bir API çağrısı
                try:
                    ticker_info = ccxt.binance().fetch_ticker(pos['symbol'])
                    current_price = ticker_info['last']
                    pnl_pct = (current_price - entry_price) / entry_price
                except:
                    current_price = entry_price
                    pnl_pct = 0

                st.metric("Anlık Fiyat", f"{current_price:.4f}", f"{pnl_pct:+.2%}")
                st.write(f"Giriş Fiyatı: {entry_price:.4f}")
                st.write(f"Açılış Tarihi: {pos['open_date'].strftime('%Y-%m-%d %H:%M')}")
                
                if st.button("🔻 POZİSYONU KAPAT", key=f"close_{pos['id']}", use_container_width=True):
                    db.close_position(pos['id'], current_price)
                    st.success(f"{pos['symbol']} pozisyonu kapatıldı!")
                    st.rerun()

    st.subheader("İşlem Geçmişi (Kapalı Pozisyonlar)")
    closed_positions = db.get_positions(is_open=False)
    st.dataframe(closed_positions)