// Aponta para a porta correta do teu Python Local
const API_URL = "https://pikamon-ai.onrender.com";

document.getElementById("suggest-btn").addEventListener("click", async () => {
    const input = document.getElementById("opponent-input").value;
    const loading = document.getElementById("loading");
    const errorMsg = document.getElementById("error-message");
    const resultSection = document.getElementById("result-section");
    const teamContainer = document.getElementById("team-container");

    // Limpar estados anteriores
    errorMsg.classList.add("hidden");
    resultSection.classList.add("hidden");
    teamContainer.innerHTML = "";

    // Criar a lista de Pokémons separados por vírgula
    const opponentTeam = input.split(",").map(p => p.trim()).filter(p => p.length > 0);

    if (opponentTeam.length === 0) {
        errorMsg.innerText = "Por favor, introduz pelo menos um Pokémon adversário.";
        errorMsg.classList.remove("hidden");
        return;
    }

    loading.classList.remove("hidden");

    try {
        const response = await fetch(`${API_URL}/suggest-team`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ opponent_team: opponentTeam })
        });

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.error || "Erro ao gerar equipa.");
        }

        // Mostrar os resultados da IA na tela
        loading.classList.add("hidden");
        resultSection.classList.remove("hidden");

        // Guardar a equipa atual numa variável global para podermos salvar depois
        window.equipaGeradaAtual = data.suggested_team;

        data.suggested_team.forEach(item => {
            // Transformar o nome num formato limpo para a API de imagens
            const pokemonNomeLimpo = item.pokemon.toLowerCase().trim().replace(" ", "-");
            
            // Link oficial da imagem
            const imagemUrl = `https://img.pokemondb.net/sprites/home/normal/${pokemonNomeLimpo}.png`;

            const card = document.createElement("div");
            card.className = "pokemon-card";
            card.innerHTML = `
                <img src="${imagemUrl}" alt="${item.pokemon}" style="width: 120px; height: 120px; object-fit: contain; display: block; margin: 0 auto 10px;" onerror="this.src='https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/0.png';">
                <h3>🦖 ${item.pokemon}</h3>
                <p>${item.reason}</p>
            `;
            teamContainer.appendChild(card);
        });

        // Adicionar o Botão de Guardar se o utilizador estiver logado
        const logado = localStorage.getItem("utilizadorLogado");
        if (logado) {
            // Remove botão antigo se existir para não duplicar
            const botaoAntigo = document.getElementById("save-team-btn");
            if (botaoAntigo) botaoAntigo.remove();

            const saveBtn = document.createElement("button");
            saveBtn.id = "save-team-btn";
            saveBtn.innerText = "💾 Guardar esta Equipa no meu Perfil";
            saveBtn.style.marginTop = "20px";
            saveBtn.style.backgroundColor = "#28a745";
            saveBtn.style.color = "white";
            saveBtn.style.padding = "10px 20px";
            saveBtn.style.border = "none";
            saveBtn.style.borderRadius = "5px";
            saveBtn.style.cursor = "pointer";
            
            saveBtn.addEventListener("click", async () => {
                try {
                    // MELHORIA: Juntamos os oponentes pesquisados e os counters num único pacote JSON
                    const dadosParaGuardar = {
                        oponentes: input, // Guarda o texto original que pesquisaste (ex: "Charizard, Pikachu")
                        counters: window.equipaGeradaAtual
                    };

                    const res = await fetch(`${API_URL}/guardar-equipa`, {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({
                            username: logado,
                            equipa: JSON.stringify(dadosParaGuardar) // Envia o pacote completo estruturado
                        })
                    });
                    
                    const resData = await res.json();
                    if (res.ok) {
                        alert(resData.message); // Mensagem de sucesso do Python
                    } else {
                        alert("Erro do Servidor: " + resData.error);
                    }
                } catch (err) {
                    alert("Erro de Rede: Não foi possível contactar o backend.");
                }
            });
            resultSection.appendChild(saveBtn);
        }

    } catch (error) {
        loading.classList.add("hidden");
        errorMsg.innerText = error.message;
        errorMsg.classList.remove("hidden");
    } // <-- Fecha o bloco catch principal de forma correta
}); // <-- Fecha a função do addEventListener do botão suggest-btn