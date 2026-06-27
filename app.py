import os
import json
import sqlite3
import datetime # Necessário para definir a validade do token
from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
from groq import Groq
from werkzeug.security import generate_password_hash, check_password_hash
# Importa a biblioteca JWT
import jwt
from functools import wraps

load_dotenv()

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*", "allow_headers": ["Content-Type", "Authorization"]}}, supports_credentials=True)

GROQ_KEY = os.environ.get("GROQ_API_KEY")
client = Groq(api_key=GROQ_KEY)

# Chave secreta para encriptar os tokens. Guarda uma senha segura no teu .env ou Render!
JWT_SECRET = os.environ.get("JWT_SECRET", "uma_chave_super_secreta_e_longa_123!")

DB_PATH = "/tmp/utilizadores.db"

# ==========================================
# FUNÇÃO (DECORATOR) PARA PROTEGER ROTAS
# ==========================================
def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        # O token será enviado no Header 'Authorization' do Frontend
        if 'Authorization' in request.headers:
            auth_header = request.headers['Authorization']
            if auth_header.startswith("Bearer "):
                token = auth_header.split(" ")[1]

        if not token:
            return jsonify({"error": "Token em falta! Inicie sessão novamente."}), 401

        try:
            # Desencripta e valida o token
            data = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
            current_user = data["username"]
        except jwt.ExpiredSignatureError:
            return jsonify({"error": "O seu passe expirou. Faça login de novo."}), 401
        except jwt.InvalidTokenError:
            return jsonify({"error": "Token inválido!"}), 401

        return f(current_user, *args, **kwargs)
    return decorated


def init_db():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS equipas_guardadas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            equipa_json TEXT NOT NULL,
            data_criacao TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

init_db()

# Rota do Groq mantém-se livre para qualquer um usar (ou podes pôr @token_required se quiseres)
@app.route('/suggest-team', methods=['POST'])
def suggest_team():
    try:
        data = request.get_json()
        opponent_team = data.get('opponent_team', [])
        if not opponent_team:
            return jsonify({"error": "Nenhum Pokémon adversário foi enviado."}), 400

        opponent_list_str = ", ".join(opponent_team)
        prompt = f"""
        O oponente está usando o seguinte time de Pokémon: {opponent_list_str}.
        Crie um time de contra-ataque perfeito com até 6 Pokémon para vencê-los.
        Responda APENAS no formato JSON abaixo:
        {{
            "suggested_team": [
                {{"pokemon": "Nome", "reason": "Explicação"}}
            ]
        }}
        """
        completion = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.5
        )
        return jsonify(json.loads(completion.choices[0].message.content.strip()))
    except Exception as e:
        return jsonify({"error": "Erro no processamento."}), 500


# ==========================================
# ROTA DE LOGIN (GERA O TOKEN JWT)
# ==========================================
@app.route('/login', methods=['POST'])
@app.route('/entrar', methods=['POST'])
def login():
    try:
        data = request.get_json()
        username = str(data.get('username', '')).strip()
        password = str(data.get('password', '')).strip()

        conn = sqlite3.connect(DB_PATH, timeout=10)
        cursor = conn.cursor()
        cursor.execute("SELECT password_hash FROM users WHERE username = ?", (username,))
        result = cursor.fetchone()
        conn.close()
        
        if not result or not check_password_hash(result[0], password):
            return jsonify({"error": "Utilizador ou password incorretos."}), 400
        
        # LOGIN CORRETO -> GERAR TOKEN JWT (Válido por 24 horas)
        token = jwt.encode({
            "username": username,
            "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=24)
        }, JWT_SECRET, algorithm="HS256")
        
        # Devolvemos o token para o Frontend guardar
        return jsonify({
            "message": "Login efetuado com sucesso! 🚀",
            "token": token,
            "user": username
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ==========================================
# ROTAS PROTEGIDAS COM JWT
# ==========================================

@app.route('/guardar-equipa', methods=['POST'])
@token_required
def guardar_equipa(current_user): # Recebe o utilizador vindo do Token
    try:
        data = request.get_json()
        equipa = data.get('equipa')

        conn = sqlite3.connect(DB_PATH, timeout=10)
        cursor = conn.cursor()
        # Usamos o 'current_user' extraído do Token por segurança!
        cursor.execute("INSERT INTO equipas_guardadas (username, equipa_json) VALUES (?, ?)", (current_user, str(equipa)))
        conn.commit()
        conn.close()
        return jsonify({"message": "Equipa guardada com sucesso! 💾"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/historico', methods=['GET']) # Removemos o <username> da URL por segurança
@token_required
def obter_historico(current_user):
    try:
        conn = sqlite3.connect(DB_PATH, timeout=10)
        cursor = conn.cursor()
        # O utilizador só consegue ver o SEU próprio histórico
        cursor.execute("SELECT equipa_json, data_criacao FROM equipas_guardadas WHERE username = ? ORDER BY data_criacao DESC", (current_user,))
        rows = cursor.fetchall()
        conn.close()
        return jsonify({"historico": [{"equipa": row[0], "data": row[1]} for row in rows]})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/register', methods=['POST'])
@app.route('/criar-conta', methods=['POST'])
def register():
    try:
        data = request.get_json()
        username = str(data.get('username', '')).strip()
        password = str(data.get('password', '')).strip()
        if not username or not password: return jsonify({"error": "Campos obrigatórios."}), 400

        conn = sqlite3.connect(DB_PATH, timeout=10)
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
        if cursor.fetchone():
            conn.close()
            return jsonify({"error": "Utilizador já existe!"}), 400
        
        hashed_password = generate_password_hash(password)
        cursor.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)", (username, hashed_password))
        conn.commit()
        conn.close()
        return jsonify({"message": "Utilizador registado! 🎉"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 4000))
    app.run(debug=False, host='0.0.0.0', port=port)