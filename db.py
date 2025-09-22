# db.py
import streamlit as st
import sqlalchemy
import pandas as pd

# Veritabanı bağlantısını yöneten fonksiyon
def get_db_connection():
    # Vercel'de çalışırken ortam değişkenini, yerelde çalışırken secrets.toml'u kullanır
    if "postgres" in st.secrets:
        # Yerel geliştirme (secrets.toml okur)
        db_url = st.secrets["postgres"]["url"]
    elif "POSTGRES_URL" in st.secrets:
        # Vercel'e deploy edildiğinde (Environment Variable okur)
        db_url = st.secrets["POSTGRES_URL"]
    else:
        raise ValueError("Veritabanı bağlantı bilgisi bulunamadı. Lütfen secrets.toml veya ortam değişkenlerini kontrol edin.")
    
    engine = sqlalchemy.create_engine(db_url)
    return engine

# Veritabanı tablolarını ilk çalıştırmada oluşturan fonksiyon
def setup_database():
    engine = get_db_connection()
    with engine.connect() as conn:
        conn.execute(sqlalchemy.text("""
            CREATE TABLE IF NOT EXISTS wallet (
                id SERIAL PRIMARY KEY,
                usdt_balance NUMERIC(15, 2) NOT NULL
            );
        """))
        conn.execute(sqlalchemy.text("""
            CREATE TABLE IF NOT EXISTS positions (
                id SERIAL PRIMARY KEY,
                symbol TEXT NOT NULL,
                amount NUMERIC(20, 8) NOT NULL,
                entry_price NUMERIC(15, 4) NOT NULL,
                is_open BOOLEAN DEFAULT TRUE,
                open_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                close_date TIMESTAMP,
                close_price NUMERIC(15, 4),
                pnl_pct NUMERIC(8, 4)
            );
        """))
        # Başlangıç cüzdanını ekle (eğer yoksa)
        result = conn.execute(sqlalchemy.text("SELECT COUNT(*) FROM wallet;")).scalar()
        if result == 0:
            conn.execute(sqlalchemy.text("INSERT INTO wallet (usdt_balance) VALUES (10000);"))
        conn.commit()

# Cüzdan bakiyesini getiren fonksiyon
def get_wallet_balance():
    engine = get_db_connection()
    with engine.connect() as conn:
        balance = conn.execute(sqlalchemy.text("SELECT usdt_balance FROM wallet WHERE id = 1;")).scalar()
        return balance if balance is not None else 10000.0

# Pozisyonları getiren fonksiyon
def get_positions(is_open=True):
    engine = get_db_connection()
    with engine.connect() as conn:
        query = sqlalchemy.text(f"SELECT * FROM positions WHERE is_open = {is_open} ORDER BY open_date DESC;")
        df = pd.read_sql(query, conn)
        return df

# Yeni bir alım işlemi ekleyen fonksiyon
def open_new_position(symbol, amount_usdt, price):
    engine = get_db_connection()
    amount_coin = amount_usdt / price
    with engine.connect() as conn:
        # Bakiyeyi güncelle
        conn.execute(sqlalchemy.text(f"UPDATE wallet SET usdt_balance = usdt_balance - {amount_usdt} WHERE id = 1;"))
        # Yeni pozisyonu ekle
        conn.execute(sqlalchemy.text(f"""
            INSERT INTO positions (symbol, amount, entry_price) 
            VALUES ('{symbol}', {amount_coin}, {price});
        """))
        conn.commit()

# Açık bir pozisyonu kapatan fonksiyon
def close_position(position_id, price):
    engine = get_db_connection()
    with engine.connect() as conn:
        # Pozisyon bilgilerini al
        pos = conn.execute(sqlalchemy.text(f"SELECT amount, entry_price FROM positions WHERE id = {position_id};")).first()
        if not pos: return
        amount_coin, entry_price = pos
        
        # Cüzdana geri dönecek USDT miktarını hesapla
        return_usdt = amount_coin * price
        
        # PNL (Kâr/Zarar) yüzdesini hesapla
        pnl_pct = (price - entry_price) / entry_price
        
        # Cüzdanı ve pozisyonu güncelle
        conn.execute(sqlalchemy.text(f"UPDATE wallet SET usdt_balance = usdt_balance + {return_usdt} WHERE id = 1;"))
        conn.execute(sqlalchemy.text(f"""
            UPDATE positions SET
            is_open = FALSE,
            close_date = CURRENT_TIMESTAMP,
            close_price = {price},
            pnl_pct = {pnl_pct}
            WHERE id = {position_id};
        """))
        conn.commit()