document.getElementById('suggest-btn').addEventListener('click', async () => {
    const inputField = document.getElementById('opponent-input');
    const loadingDiv = document.getElementById('loading');
    const errorDiv = document.getElementById('error-message');
    const resultSection = document.getElementById('result-section');
    const teamContainer = document.getElementById('team-container');

    // Separa os nomes por vírgula e limpa espaços extras
    const opponentTeam = inputField.value.split(',').map(name => name.trim()).filter(name => name.length > 0);

    if (opponentTeam.length === 0) {
        alert("Por favor, digite pelo menos um Pokémon do oponente!");
        return;
    }

    // Reseta o estado visual dos resultados
    loadingDiv.classList.remove('hidden');
    errorDiv.classList.add('hidden');
    resultSection.classList.add('hidden');
    teamContainer.innerHTML = '';

    try {
        // Envia a lista para o seu servidor Python Flask na porta 5000
        const response = await fetch('http://127.0.0.1:5000/suggest-team', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ opponent_team: opponentTeam })
        });

        if (!response.ok) {
            throw new Error("Falha ao carregar o time. O seu servidor Flask está ligado?");
        }

        const data = await response.json();
        
        // Monta os cards na tela para cada Pokémon retornado pelo Gemini
        data.suggested_team.forEach(item => {
            const card = document.createElement('div');
            card.className = 'pokemon-card';
            
            // Padroniza o nome para buscar a imagem na API
            const formattedName = item.pokemon.toLowerCase().trim().replace(/\s+/g, '-');
            const imageUrl = `https://img.pokemondb.net/sprites/home/normal/${formattedName}.png`;

            card.innerHTML = `
                <div class="pokemon-header">
                    <img src="${imageUrl}" alt="${item.pokemon}" class="pokemon-sprite" onerror="this.src='https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/0.png'">
                    <div class="pokemon-name">${item.pokemon}</div>
                </div>
                <div class="pokemon-reason">${item.reason}</div>
            `;
            teamContainer.appendChild(card);
        });

        // Exibe a seção de resultados na tela
        resultSection.classList.remove('hidden');

    } catch (error) {
        errorDiv.textContent = error.message;
        errorDiv.classList.remove('hidden');
    } finally {
        loadingDiv.classList.add('hidden');
    }
});