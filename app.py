import os
import json
from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
from google import genai
from google.genai import types
from pydantic import BaseModel

# 1. Definição do molde estruturado para a IA seguir à risca
class PokemonSuggestion(BaseModel):
    pokemon: str
    reason: str

class TeamResponse(BaseModel):
    suggested_team: list[PokemonSuggestion]

# 2. Carrega as variáveis do arquivo .env
load_dotenv()

# 3. Inicializa o Flask e ativa o CORS para permitir que o index.html converse com o servidor
app = Flask(__name__)
CORS(app)

# 4. Inicializa o cliente oficial do Gemini
client = genai.Client()

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

        # Valida se a IA realmente retornou texto
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

# ADICIONADO: O bloco final para o Flask ligar corretamente e escutar a rede
if __name__ == '__main__':
    # O Render define a porta automaticamente através da variável PORT
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=False, host='0.0.0.0', port=port)