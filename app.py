import streamlit as st
import requests
import json
import os
from datetime import datetime, timedelta
from streamlit_autorefresh import st_autorefresh



# --- CONFIGURAÇÕES ---
API_KEY = st.secrets["WONCA_API_KEY"]
TELEGRAM_TOKEN = st.secrets["TELEGRAM_TOKEN"]
CHAT_ID = st.secrets["TELEGRAM_CHAT_ID"]
DB_FILE = "rastreios.json"
API_URL = 'https://api-labs.wonca.com.br/wonca.labs.v1.LabsService/Track'
COTA_DIARIA = 33 # 1000 / 30 dias

# MODO DE TESTE: True força 1 minuto. False usa a cota de 1000/mês.
DEBUG_MODE = True 

# --- 2. FUNÇÕES DE TESTE (SEM COMANDOS ST) ---
def testar_wonca():
    db = manipular_dados("ler")
    # Tenta usar um código real da sua lista para o teste, se não houver, usa um padrão
    codigo_teste = list(db.keys())[0] if db else "AA361812099BR" 
    
    url = 'https://api-labs.wonca.com.br/wonca.labs.v1.LabsService/Track'
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Apikey {API_KEY}',
        'User-Agent': 'Mozilla/5.0' # Algumas APIs exigem um User-Agent para não bloquear
    }
    payload = {"code": codigo_teste}
    
    try:
        res = requests.post(url, json=payload, headers=headers, timeout=10)
        if res.status_code == 200:
            return (True, "Conectado!")
        else:
            # Retorna o erro e o que a API respondeu no corpo (JSON)
            detalhe = res.text[:50] # Pega os primeiros 50 caracteres do erro
            return (False, f"Erro {res.status_code}: {detalhe}")
    except Exception as e:
        return (False, f"Falha de conexão: {str(e)}")

def testar_telegram():
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getMe"
    try:
        res = requests.get(url, timeout=5)
        return (True, "Conectado") if res.status_code == 200 else (False, "Token Inválido")
    except: return (False, "Erro de Rede")

# --- 3. LOGICA DE DADOS ---
def manipular_dados(acao="ler", dados=None):
    if acao == "ler":
        if os.path.exists(DB_FILE):
            with open(DB_FILE, "r", encoding="utf-8") as f: return json.load(f)
        return {}
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(dados, f, indent=4, ensure_ascii=False)

def enviar_telegram(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"})

# --- 4. INTERFACE E EXECUÇÃO ---
def main():
    # REGRA #1: O PRIMEIRO COMANDO DEVE SER ESTE:
    st.set_page_config(page_title="Rastreador Pro", page_icon="🚚", layout="wide")
    
    # REGRA #2: O REFRESH VEM LOGO DEPOIS
    st_autorefresh(interval=60000, key="bot_refresh") # 1 minuto

    st.title("🚚 Monitor de Rastreio (Modo Teste)")
    st.markdown('<a href="" target="_blank">Rastreamento</a>', unsafe_allow_html=True)

    # --- VALIDAÇÃO DE CHAVES NA TELA ---
    with st.expander("🔍 Status das Chaves (Clique para ver)", expanded=True):
        col1, col2 = st.columns(2)
        w_ok, w_msg = testar_wonca()
        t_ok, t_msg = testar_telegram()
        
        col1.metric("API Wonca", "Ativa" if w_ok else "Falha", delta=w_msg)
        col2.metric("Bot Telegram", "Ativo" if t_ok else "Falha", delta=t_msg)
        
        if not w_ok or not t_ok:
            st.warning("Verifique suas chaves nas configurações do código.")

    # --- PROCESSAMENTO ---
    db = manipular_dados("ler")
    agora = datetime.now()
    
    # Se DEBUG_MODE for True, intervalo é 1 min. Se False, calcula pela cota.
    if DEBUG_MODE:
        intervalo_minutos = 1
    else:
        ativos = [c for c, v in db.items() if not v.get('entregue', False)]
        intervalo_minutos = int(1440 / (32 / max(len(ativos), 1)))

    st.write(f"⏱️ Próxima checagem permitida em: **{intervalo_minutos} min**")

    # Loop de consulta
    houve_mudanca = False
    for cod, info in list(db.items()):
        if info.get('entregue'): continue
        
        last_check = info.get('last_check')
        pode_ir = not last_check or agora > datetime.fromisoformat(last_check) + timedelta(minutes=intervalo_minutos)
        
        if pode_ir:
            st.toast(f"Consultando {info['apelido']}...")
            # API WONCA REAL
            url_w = 'https://api-labs.wonca.com.br/wonca.labs.v1.LabsService/Track'
            h_w = {'Content-Type': 'application/json', 'Authorization': f'Apikey {API_KEY}'}
            try:
                r = requests.post(url_w, json={"code": cod}, headers=h_w, timeout=10)
                if r.status_code == 200:
                    evento = r.json().get('events', [{}])[0]
                    novo_status = evento.get('description', 'Sem status')
                    
                    if novo_status != info.get('status'):
                        info['status'] = novo_status
                        enviar_telegram(f"🔔 *Mudança:* {info['apelido']}\n📝 {novo_status}")
                        if "entregue" in novo_status.lower(): info['entregue'] = True
                    
                    info['last_check'] = agora.isoformat()
                    houve_mudanca = True
            except: pass

    if houve_mudanca: manipular_dados("salvar", db)

    # --- EXIBIÇÃO ---
    for cod, info in db.items():
        with st.container(border=True):
            c1, c2, c3 = st.columns([3, 5, 1])
            c1.markdown(f"### {info['apelido']}\n`{cod}`")
            c2.markdown(f"**Status:** {info.get('status')}\n\nÚltima verificação: {info.get('last_check', 'Nunca')}")
            if c3.button("🗑️", key=cod):
                del db[cod]
                manipular_dados("salvar", db)
                st.rerun()

    # Sidebar para cadastro
    with st.sidebar:
        st.header("Novo Item")
        ncod = st.text_input("Código").upper()
        nape = st.text_input("Apelido")
        if st.button("Adicionar"):
            db[ncod] = {"apelido": nape, "status": "Aguardando", "entregue": False, "last_check": None}
            manipular_dados("salvar", db)
            st.rerun()

if __name__ == "__main__":

    main()
