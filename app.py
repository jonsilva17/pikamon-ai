import os
import json
import sqlite3  # Para a base de dados do login e histórico
from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
from google import genai
from google.genai import types
from pydantic import BaseModel
# MUDANÇA AQUI: Trocámos o passlib pela segurança nativa do Flask
from werkzeug.security import generate_password_hash, check_password_hash

# 1. Definição do molde estruturado para a IA seguir à risca
class PokemonSuggestion(BaseModel):
    pokemon: str
    reason: str

class TeamResponse(BaseModel):
    suggested_team: list[PokemonSuggestion]

# 2. Carrega as variáveis do arquivo .env
load_dotenv()

# 3. Inicializa o Flask e ativa o CORS oficial
app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}}, supports_credentials=True)

# 4. Inicializa o cliente oficial do Gemini
client = genai.Client()

# 5. CONFIGURAÇÃO DA BASE DE DADOS (Cria as tabelas se não existirem)
def init_db():
    conn = sqlite3.connect("utilizadores.db")
    cursor = conn.cursor()
    
    # Tabela de utilizadores
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL
        )
    """)
    
    # Tabela para guardar o histórico de equipas
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

init_db()  # Corre automaticamente ao ligar o servidor


# ==========================================
# ROTA: GERADOR DE EQUIPAS POKÉMON
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
        """

        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=TeamResponse,
            ),
        )

        if not response.text:
            raise ValueError("O Gemini retornou uma resposta vazia.")

        ai_data = json.loads(response.text)
        return jsonify(ai_data)

    except json.JSONDecodeError as je:
        print(f"[ERRO DE FORMATO] Falha ao ler o JSON da IA: {je}")
        return jsonify({"error": "A inteligência artificial gerou um formato inválido. Tente novamente."}), 502
    except Exception as e:
        print(f"\n[ERRO NO SERVIDOR] Detalhes: {e}\n")
        return jsonify({"error": "Ocorreu um erro temporário no processamento. Por favor, tente de novo."}), 500


# ==========================================
# ROTAS NOVAS: REGISTO, LOGIN E HISTÓRICO
# ==========================================

@app.route('/register', methods=['POST'])
def register():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "Dados não foram enviados corretamente."}), 400

        username = str(data.get('username', '')).strip()
        password = str(data.get('password', '')).strip()

        if not username or not password:
            return jsonify({"error": "Utilizador e password são obrigatórios."}), 400

        conn = sqlite3.connect("utilizadores.db")
        cursor = conn.cursor()
        
        # Verificar se o utilizador já existe
        cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
        if cursor.fetchone():
            conn.close()
            return jsonify({"error": "Este nome de utilizador já existe!"}), 400
        
        # MUDANÇA AQUI: Encriptação nova, limpa e segura (sem bug de bytes)
        hashed_password = generate_password_hash(password)
        
        cursor.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)", (username, hashed_password))
        conn.commit()
        conn.close()
        
        return jsonify({"message": "Utilizador registado com sucesso! 🎉"})
    except Exception as e:
        print(f"[ERRO NO REGISTO]: {e}")
        return jsonify({"error": f"Erro interno: {str(e)}"}), 500


@app.route('/login', methods=['POST'])
def login():
    try:
        data = request.get_json()
        username = str(data.get('username', '')).strip()
        password = str(data.get('password', '')).strip()

        conn = sqlite3.connect("utilizadores.db")
        cursor = conn.cursor()
        
        cursor.execute("SELECT password_hash FROM users WHERE username = ?", (username,))
        result = cursor.fetchone()
        conn.close()
        
        # MUDANÇA AQUI: Verificação com a nova biblioteca
        if not result or not check_password_hash(result[0], password):
            return jsonify({"error": "Utilizador ou password incorretos."}), 400
        
        return jsonify({
            "message": "Login efetuado com sucesso! Bem-vindo/a. 🚀",
            "user": username
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/guardar-equipa', methods=['POST'])
def guardar_equipa():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "Nenhuns dados foram recebidos no servidor."}), 400

        username = data.get('username')
        equipa = data.get('equipa')

        if not username or not equipa:
            return jsonify({"error": "Utilizador ou equipa em falta nos dados enviados."}), 400

        # Forçar a conversão para string para o SQLite não reclamar
        equipa_string = str(equipa)

        conn = sqlite3.connect("utilizadores.db")
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO equipas_guardadas (username, equipa_json) VALUES (?, ?)", 
            (username, equipa_string)
        )
        conn.commit()
        conn.close()
        
        return jsonify({"message": "Equipa guardada no teu perfil com sucesso! 💾"})
    except Exception as e:
        print(f"\n[ERRO AO GUARDAR EQUIPA]: {e}\n")
        return jsonify({"error": f"Erro interno do servidor: {str(e)}"}), 500


@app.route('/historico/<username>', methods=['GET'])
def obter_historico(username):
    try:
        conn = sqlite3.connect("utilizadores.db")
        cursor = conn.cursor()
        cursor.execute(
            "SELECT equipa_json, data_criacao FROM equipas_guardadas WHERE username = ? ORDER BY data_criacao DESC",
            (username,)
        )
        rows = cursor.fetchall()
        conn.close()
        
        historico = [{"equipa": row[0], "data": row[1]} for row in rows]
        return jsonify({"historico": historico})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# Ligar o servidor Flask na porta 4000
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 4000))
    app.run(debug=False, host='0.0.0.0', port=port)