import os
import json
import sqlite3
import datetime # Necessário para definir a validade do token
from flask import Flask, request, jsonify, redirect
from flask_cors import CORS
from dotenv import load_dotenv
from groq import Groq
from werkzeug.security import generate_password_hash, check_password_hash
# Importa a biblioteca JWT
import jwt
from functools import wraps
from authlib.integrations.flask_client import OAuth

load_dotenv()

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*", "allow_headers": ["Content-Type", "Authorization"]}}, supports_credentials=True)

GROQ_KEY = os.environ.get("GROQ_API_KEY")
client = Groq(api_key=GROQ_KEY)

# Chave secreta para encriptar os tokens. Guarda uma senha segura no teu .env ou Render!
JWT_SECRET = os.environ.get("JWT_SECRET", "uma_chave_super_secreta_e_longa_123!")

GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET")
GOOGLE_REDIRECT_URI = os.environ.get("GOOGLE_REDIRECT_URI", "http://localhost:4000/auth/google/callback")
FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:5173")

oauth = OAuth(app)
oauth.register(
    name="google",
    client_id=GOOGLE_CLIENT_ID,
    client_secret=GOOGLE_CLIENT_SECRET,
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile"},
)

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
    # Add Google OAuth columns if missing (safe migration for existing DBs)
    for col in ["google_id TEXT UNIQUE", "email TEXT", "avatar TEXT"]:
        try:
            cursor.execute(f"ALTER TABLE users ADD COLUMN {col}")
        except sqlite3.OperationalError:
            pass
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
# GOOGLE OAUTH LOGIN
# ==========================================
@app.route('/auth/google/login')
def google_login():
    return oauth.google.authorize_redirect(GOOGLE_REDIRECT_URI)


@app.route('/auth/google/callback')
def google_callback():
    try:
        token = oauth.google.authorize_access_token()
        user_info = oauth.google.parse_id_token(token)

        google_id = user_info["sub"]
        email = user_info.get("email", "")
        name = user_info.get("name", "")
        avatar = user_info.get("picture", "")

        conn = sqlite3.connect(DB_PATH, timeout=10)
        cursor = conn.cursor()

        cursor.execute("SELECT username FROM users WHERE google_id = ?", (google_id,))
        user = cursor.fetchone()

        if user:
            username = user[0]
        else:
            base_username = name.replace(" ", "_").lower() or email.split("@")[0]
            username = base_username
            suffix = 1
            while True:
                cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
                if not cursor.fetchone():
                    break
                username = f"{base_username}_{suffix}"
                suffix += 1

            cursor.execute(
                "INSERT INTO users (username, password_hash, google_id, email, avatar) VALUES (?, ?, ?, ?, ?)",
                (username, "GOOGLE_AUTH", google_id, email, avatar),
            )
            conn.commit()

        conn.close()

        jwt_token = jwt.encode(
            {
                "username": username,
                "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=24),
            },
            JWT_SECRET,
            algorithm="HS256",
        )

        redirect_url = f"{FRONTEND_URL}/?token={jwt_token}&user={username}"
        return redirect(redirect_url)

    except Exception as e:
        return jsonify({"error": f"Google login failed: {str(e)}"}), 500


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
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=False, host='0.0.0.0', port=port)