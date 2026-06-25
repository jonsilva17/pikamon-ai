import os
import json
import sqlite3
from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
# Mudámos para a biblioteca do Groq (Sem bloqueios no Render!)
from groq import Groq
from werkzeug.security import generate_password_hash, check_password_hash

load_dotenv()

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}}, supports_credentials=True)

# Inicializa o cliente do Groq
GROQ_KEY = os.environ.get("GROQ_API_KEY")
client = Groq(api_key=GROQ_KEY)

DB_PATH = "/tmp/utilizadores.db"

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

# ==========================================
# ROTA: GERADOR DE EQUIPAS COM GROQ (LLAMA 3)
# ==========================================
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
        Crie um time de contra-ataque (counter-team) perfeito com até 6 Pokémon para vencê-los.
        Para cada Pokémon sugerido, explique brevemente a estratégia/motivo da escolha.
        
        Responda APENAS no formato JSON abaixo, sem qualquer texto, saudação ou aspas de bloco extra antes ou depois:
        {{
            "suggested_team": [
                {{"pokemon": "Nome do Pokemon", "reason": "Explicação em português"}}
            ]
        }}
        """

        # Usamos o modelo Llama 3 que é ultra rápido e livre de bloqueios 403
        completion = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "user", "content": prompt}
            ],
            temperature=0.5
        )

        response_text = completion.choices[0].message.content.strip()

        if not response_text:
            raise ValueError("O modelo retornou uma resposta vazia.")

        ai_data = json.loads(response_text)
        return jsonify(ai_data)

    except Exception as e:
        print(f"\n[ERRO NO SERVIDOR] Detalhes: {e}\n")
        return jsonify({"error": "Ocorreu um erro temporário no processamento. Por favor, tente de novo."}), 500


# ==========================================
# ROTAS: REGISTO, LOGIN E HISTÓRICO
# ==========================================
@app.route('/register', methods=['POST'])
@app.route('/criar-conta', methods=['POST'])
def register():
    try:
        data = request.get_json()
        if not data: return jsonify({"error": "Dados inválidos."}), 400

        username = str(data.get('username', '')).strip()
        password = str(data.get('password', '')).strip()

        if not username or not password:
            return jsonify({"error": "Utilizador e password são obrigatórios."}), 400

        conn = sqlite3.connect(DB_PATH, timeout=10)
        cursor = conn.cursor()
        
        cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
        if cursor.fetchone():
            conn.close()
            return jsonify({"error": "Este nome de utilizador já existe!"}), 400
        
        hashed_password = generate_password_hash(password)
        cursor.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)", (username, hashed_password))
        conn.commit()
        conn.close()
        
        return jsonify({"message": "Utilizador registado com sucesso! 🎉"})
    except Exception as e:
        print(f"[ERRO NO REGISTO]: {e}")
        return jsonify({"error": f"Erro interno: {str(e)}"}), 500

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
        
        return jsonify({"message": "Login efetuado com sucesso! 🚀", "user": username})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/guardar-equipa', methods=['POST'])
def guardar_equipa():
    try:
        data = request.get_json()
        username = data.get('username')
        equipa = data.get('equipa')

        conn = sqlite3.connect(DB_PATH, timeout=10)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO equipas_guardadas (username, equipa_json) VALUES (?, ?)", (username, str(equipa)))
        conn.commit()
        conn.close()
        return jsonify({"message": "Equipa guardada com sucesso! 💾"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/historico/<username>', methods=['GET'])
def obter_historico(username):
    try:
        conn = sqlite3.connect(DB_PATH, timeout=10)
        cursor = conn.cursor()
        cursor.execute("SELECT equipa_json, data_criacao FROM equipas_guardadas WHERE username = ? ORDER BY data_criacao DESC", (username,))
        rows = cursor.fetchall()
        conn.close()
        return jsonify({"historico": [{"equipa": row[0], "data": row[1]} for row in rows]})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 4000))
    app.run(debug=False, host='0.0.0.0', port=port)