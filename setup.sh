#!/bin/bash

# Streamlit'in Vercel üzerinde doğru çalışabilmesi için 
# gerekli yapılandırma klasörünü ve dosyasını oluşturur.
mkdir -p ~/.streamlit/
echo "\
[server]\n\
headless = true\n\
port = $PORT\n\
enableCORS = false\n\
\n\
" > ~/.streamlit/config.toml