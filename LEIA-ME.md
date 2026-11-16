# DOG-IA V2 — AC-4

O programa principal é `dog_ia_v2.py`. Mantém as funções de desenho do código
original e organiza as melhorias em classes simples, com comentários em português.

## Executar nesta pasta

O ambiente local já foi preparado com Python 3.12 e Pygame 2.6.1:

```powershell
.\.venv\Scripts\python.exe .\dog_ia_v2.py
```

Em outro computador com Python instalado:

```powershell
python -m pip install -r requirements.txt
python dog_ia_v2.py
```

O programa começa indo ao Mercado. Use `1` Mercado, `2` Farmácia, `3` Padaria e
`4` Casa. Para voltar após uma ida, pressione `4`. Espaço alterna manual/IA;
as setas esquerda/direita giram e a seta para cima avança. O controle manual
também respeita a barreira e o freio de emergência. Clique esquerdo escolhe
um destino livre; clique direito insere um obstáculo. `R` reinicia e `Esc` sai.
Use `--sem-audio` para desativar os sons.

## Requisitos implementados

- Semáforo com cinco fases e tempo simulado, veículos nos dois sentidos,
  aceleração, frenagem, distância de seguimento e 12% de infratores.
- Barreira no meio-fio para robô e tutor; início da travessia condicionado
  ao sinal, ao tempo restante e à faixa livre.
- A* em grade de 10 px, heurística octile, inflação de 30/22/38 px,
  custo 0,45 no piso tátil e replanejamento após 3,5 s sem progresso.
- LiDAR por `Rect.clipline`, ruído gaussiano de 1,5 px, dropout de 2%
  e mediana temporal de três leituras por raio.
- Projeção dos veículos por um segundo para freio de emergência,
  tutor independente seguindo o rastro, redução de velocidade pela
  tensão da guia e alertas sintéticos em estéreo.
- Telemetria e benchmark sem janela, sem inicializar vídeo ou áudio.

O toldo inferior foi deslocado de x=520 para x=470 para liberar a saída
da faixa após aplicar a margem de segurança dos obstáculos suspensos.

## Benchmark e verificações

```powershell
.\.venv\Scripts\python.exe dog_ia_v2.py --benchmark 20 --seed 1 --saida benchmark_seed_1.json
.\.venv\Scripts\python.exe dog_ia_v2.py --benchmark 20 --seed 7 --saida benchmark_seed_7.json
.\.venv\Scripts\python.exe validar_dog_ia.py
```

Resultados obtidos nesta versão:

| Seed | Viagens | Sucesso | Tempo médio | Colisões | Quase-colisões | Freios |
|---|---:|---:|---:|---:|---:|---:|
| 1 | 20 | 100% | 13,530 s | 0 | 0 | 1 |
| 7 | 20 | 100% | 13,470 s | 0 | 0 | 0 |

O benchmark alterna idas a Mercado/Farmácia/Padaria e voltas para Casa.
Cada viagem começa com uma simulação nova; a sequência aleatória é mantida
ao longo do experimento. Há limite de 120 s simulados por viagem, ajustável
por `--tempo-limite`. Sucesso significa chegada sem colisão. O tempo médio
considera apenas os sucessos. Quase-colisão significa folga inferior a
12 px sem contato; colisões e aproximações contam episódios por entidade
e obstáculo, em vez de contar todos os quadros do mesmo episódio.

As 11 verificações cobrem sinal, barreira, frenagem nos dois sentidos,
seguimento, infratores, saída de um obstáculo em U, uso da faixa, filtro
do sensor, freio preditivo, tensão da guia e ida/volta na mesma simulação.
Uma renderização de conferência está em `preview_dog_ia.png`.

Os resultados descrevem estes cenários didáticos e não garantem segurança
em todos os cenários possíveis.
