"""DOG-IA V2 - evolução do código da aula AC-4.

Instalação: python -m pip install pygame
Executar:   python dog_ia_v2.py
Experimento: python dog_ia_v2.py --benchmark 20 --seed 1

Os tempos e velocidades usam segundos e pixels por segundo.
É uma simulação didática, sem uso para guiar pessoas no trânsito real.
"""

import os
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import argparse
import heapq
import json
import math
import random
from array import array
from collections import deque
from statistics import median

try:
    import pygame
except ImportError:
    raise SystemExit("Instale a dependência: python -m pip install pygame")

# ==================== CONFIGURAÇÕES GERAIS ====================
LARGURA, ALTURA = 1050, 680
FPS = 60
AREA_MAPA_LARGURA = LARGURA - 260
RUA_Y, RUA_ALTURA = 250, 170
FAIXA_X, FAIXA_LARGURA = 580, 95
CELULA = 10
GUIA = 42
VELOCIDADE = 156.0
ACEL, DESACEL = 80.0, 180.0
INFLACAO = {"solo": 30, "edificacao": 22, "suspenso": 38}
DESTINOS = {
    1: ("Mercado", (710, 543)),
    2: ("Farmácia", (320, 600)),
    3: ("Padaria", (710, 127)),
    4: ("Casa", (95, 127)),
}

BRANCO = (245, 245, 245)
PRETO = (20, 22, 28)
ASFALTO = (42, 45, 52)
CALÇADA_CLARA = (130, 134, 142)
MEIO_FIO = (175, 180, 188)
PISO_TATIL = (235, 190, 20)
GRAMA = (46, 115, 65)
CORPO_ROBO = (30, 136, 229)
DETALHE_ROBO = (15, 76, 129)
CABECA_ROBO = (230, 236, 245)
ARNES_GUIA = (255, 215, 0)
VERDE_LIVRE = (46, 204, 113)
LARANJA_ALERTA = (255, 140, 0)
VERMELHO_PERIGO = (225, 55, 55)
ROXO_SUSPENSO = (155, 89, 182)
PISOS = [pygame.Rect(40, 120, 595, 14), pygame.Rect(621, 120, 14, 130),
         pygame.Rect(621, 420, 14, 130), pygame.Rect(150, 536, 485, 14)]


def rotacionar_ponto(cx, cy, px, py, angulo):
    s, c = math.sin(angulo), math.cos(angulo)
    dx, dy = px - cx, py - cy
    return int(cx + dx * c - dy * s), int(cy + dx * s + dy * c)


def distancia(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def distancia_retangulo(x, y, rect):
    dx = max(rect.left - x, 0, x - rect.right)
    dy = max(rect.top - y, 0, y - rect.bottom)
    return math.hypot(dx, dy)


def aplicar_barreira(anterior, proposta, raio, autorizado):
    """Bloqueia a entrada na rua sem autorização e fora da faixa.

    Quem já está atravessando pode terminar mesmo se o sinal mudar.
    A mesma barreira vale para o controle manual e para o tutor.
    """
    x, y = proposta
    x = max(raio + 5, min(AREA_MAPA_LARGURA - raio - 5, x))
    y = max(raio + 5, min(ALTURA - raio - 5, y))
    topo, fundo = RUA_Y - raio, RUA_Y + RUA_ALTURA + raio
    toca_rua = topo < y < fundo
    dentro_faixa = FAIXA_X + raio <= x <= FAIXA_X + FAIXA_LARGURA - raio
    if toca_rua and not dentro_faixa:
        return anterior
    ja_na_rua = topo < anterior[1] < fundo
    if toca_rua and not ja_na_rua and not autorizado:
        return anterior
    return x, y


# ==================== SEMÁFORO E VEÍCULOS ====================
class Semaforo:
    FASES = [("VERDE", 7.0), ("AMARELO", 2.0), ("TODOS_VERM_1", 1.5),
             ("PEDESTRE", 10.0), ("TODOS_VERM_2", 1.5)]

    def __init__(self):
        self.indice = 0
        self.tempo = 0.0

    @property
    def fase(self):
        return self.FASES[self.indice][0]

    @property
    def restante(self):
        return self.FASES[self.indice][1] - self.tempo

    def atualizar(self, dt):
        self.tempo += dt
        while self.tempo >= self.FASES[self.indice][1]:
            self.tempo -= self.FASES[self.indice][1]
            self.indice = (self.indice + 1) % len(self.FASES)

    def pode_atravessar(self, velocidade):
        limite = (RUA_ALTURA + 24 + GUIA) / max(velocidade, 1) * 1.35 + 0.4
        return self.fase == "PEDESTRE" and self.restante > limite


class Veiculo:
    def __init__(self, sentido, rng, numero):
        self.sentido = sentido
        self.numero = numero
        self.x = -70.0 if sentido == 1 else AREA_MAPA_LARGURA + 70.0
        self.y = 292 if sentido == 1 else 378
        self.velocidade_max = rng.uniform(115, 150)
        self.velocidade = self.velocidade_max
        self.infrator = rng.random() < 0.12
        self.comprometido = False
        self.ultima_fase = None
        self.cor = rng.choice([(65, 155, 200), (210, 150, 55), (180, 185, 195)])

    @property
    def rect(self):
        return pygame.Rect(round(self.x - 25), self.y - 13, 50, 26)

    def zona_varrida(self, segundos=1.0):
        futuro = self.rect.move(round(self.sentido * self.velocidade * segundos), 0)
        return self.rect.union(futuro)

    def atualizar(self, dt, semaforo, lider):
        frente = self.x + self.sentido * 25
        linha = FAIXA_X - 18 if self.sentido == 1 else FAIXA_X + FAIXA_LARGURA + 18
        ate_linha = (linha - frente) * self.sentido
        if ate_linha < 0:
            self.comprometido = True

        # No amarelo, só para se ainda houver distância de frenagem.
        parar = semaforo.fase != "VERDE"
        if semaforo.fase == "AMARELO" and self.ultima_fase != "AMARELO" and self.velocidade > 1:
            if ate_linha < self.velocidade ** 2 / (2 * DESACEL) + 8:
                self.comprometido = True
        self.ultima_fase = semaforo.fase
        limite_movimento = float("inf")
        if parar and not self.infrator and not self.comprometido:
            limite_movimento = max(0, ate_linha - 6)
        if lider is not None:
            espaco = (lider.x - self.x) * self.sentido - 50 - 24
            limite_movimento = min(limite_movimento, max(0, espaco))

        desejada = min(self.velocidade_max, math.sqrt(2 * DESACEL * limite_movimento))
        if self.velocidade < desejada:
            self.velocidade = min(desejada, self.velocidade + ACEL * dt)
        else:
            self.velocidade = max(desejada, self.velocidade - DESACEL * dt)
        movimento = min(self.velocidade * dt, limite_movimento)
        self.x += self.sentido * movimento
        if movimento == 0:
            self.velocidade = 0

    def desenhar(self, tela):
        pygame.draw.rect(tela, self.cor, self.rect, border_radius=5)
        janela = self.rect.inflate(-25, -6)
        pygame.draw.rect(tela, DETALHE_ROBO, janela, border_radius=3)
        if self.infrator:
            pygame.draw.rect(tela, VERMELHO_PERIGO, self.rect, 3, border_radius=5)


class Transito:
    def __init__(self, rng):
        self.rng = rng
        self.veiculos = []
        self.tempos = {1: 0.0, -1: 1.0}
        self.numero = 0

    def atualizar(self, dt, semaforo):
        for sentido in (1, -1):
            self.tempos[sentido] -= dt
            fila = sorted([v for v in self.veiculos if v.sentido == sentido],
                          key=lambda v: v.x * sentido, reverse=True)
            lider = None
            for carro in fila:
                carro.atualizar(dt, semaforo, lider)
                lider = carro
            entrada = -70 if sentido == 1 else AREA_MAPA_LARGURA + 70
            if self.tempos[sentido] <= 0 and all(abs(v.x - entrada) > 110 for v in fila):
                self.numero += 1
                self.veiculos.append(Veiculo(sentido, self.rng, self.numero))
                self.tempos[sentido] = self.rng.uniform(2.4, 3.8)
        self.veiculos = [v for v in self.veiculos if -160 < v.x < AREA_MAPA_LARGURA + 160]


# ==================== PLANEJAMENTO GLOBAL A* ====================
class Planejador:
    def __init__(self, obstaculos):
        self.obstaculos = obstaculos
        self.inflados = [o["rect"].inflate(2 * INFLACAO[o["tipo"]],
                                         2 * INFLACAO[o["tipo"]]) for o in obstaculos]
        self.colunas = AREA_MAPA_LARGURA // CELULA
        self.linhas = ALTURA // CELULA
        self.livres = set()
        for linha in range(self.linhas):
            for coluna in range(self.colunas):
                no = (coluna, linha)
                if self.posicao_livre(*self.ponto(no)):
                    self.livres.add(no)

    def posicao_livre(self, x, y):
        if not (30 <= x <= AREA_MAPA_LARGURA - 30 and 30 <= y <= ALTURA - 30):
            return False
        if RUA_Y - 20 < y < RUA_Y + RUA_ALTURA + 20:
            if not FAIXA_X + 20 <= x <= FAIXA_X + FAIXA_LARGURA - 20:
                return False
        return not any(rect.collidepoint(x, y) for rect in self.inflados)

    def ponto(self, no):
        return no[0] * CELULA + CELULA / 2, no[1] * CELULA + CELULA / 2

    def no(self, ponto):
        return int(ponto[0] // CELULA), int(ponto[1] // CELULA)

    def custo(self, no):
        return 0.45 if any(p.collidepoint(self.ponto(no)) for p in PISOS) else 1.0

    def heuristica(self, a, b):
        dx, dy = abs(a[0] - b[0]), abs(a[1] - b[1])
        # A menor tarifa (0.45) mantém a heurística admissível.
        return 0.45 * (max(dx, dy) + (math.sqrt(2) - 1) * min(dx, dy))

    def buscar(self, inicio, destino):
        origem, fim = self.no(inicio), self.no(destino)
        if origem not in self.livres or fim not in self.livres:
            return []
        abertos = [(self.heuristica(origem, fim), 0.0, origem)]
        custos, anterior = {origem: 0.0}, {}
        while abertos:
            _, custo_atual, atual = heapq.heappop(abertos)
            if custo_atual > custos.get(atual, float("inf")):
                continue
            if atual == fim:
                caminho = [atual]
                while atual in anterior:
                    atual = anterior[atual]
                    caminho.append(atual)
                caminho.reverse()
                pontos = [self.ponto(n) for n in caminho]
                # Conecta a posição real ao centro da sua célula.
                return pontos + [destino]
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1),
                           (1, 1), (1, -1), (-1, 1), (-1, -1)):
                vizinho = atual[0] + dx, atual[1] + dy
                if vizinho not in self.livres:
                    continue
                # A diagonal não pode cortar a quina de um obstáculo.
                if dx and dy and ((atual[0] + dx, atual[1]) not in self.livres or
                                  (atual[0], atual[1] + dy) not in self.livres):
                    continue
                novo = custo_atual + math.hypot(dx, dy) * self.custo(vizinho)
                if novo < custos.get(vizinho, float("inf")):
                    custos[vizinho] = novo
                    anterior[vizinho] = atual
                    heapq.heappush(abertos, (novo + self.heuristica(vizinho, fim), novo, vizinho))
        return []


# ==================== TUTOR, ÁUDIO E CÃO-ROBÔ ====================
class Tutor:
    def __init__(self, x, y):
        self.x, self.y = float(x), float(y)
        self.raio = 12
        self.rastro = deque()

    def atualizar(self, robo, dt, obstaculos):
        # O tutor percorre o rastro, evitando cortar as esquinas do robô.
        ponto = (robo.x, robo.y)
        if not self.rastro or distancia(self.rastro[-1], ponto) > 1:
            self.rastro.append(ponto)
        percurso = distancia((self.x, self.y), self.rastro[0])
        percurso += sum(distancia(a, b) for a, b in zip(self.rastro, list(self.rastro)[1:]))
        restante = min(170 * dt, max(0.0, percurso - GUIA))
        while restante > 0.001 and self.rastro:
            tx, ty = self.rastro[0]
            d = distancia((self.x, self.y), (tx, ty))
            if d < 0.01:
                self.rastro.popleft()
                continue
            passo = min(d, restante)
            proposta = self.x + (tx - self.x) / d * passo, self.y + (ty - self.y) / d * passo
            nova = aplicar_barreira((self.x, self.y), proposta, self.raio, robo.travessia_autorizada)
            if any(distancia_retangulo(*nova, o["rect"]) < self.raio for o in obstaculos):
                break
            if distancia((self.x, self.y), nova) < 0.001:
                break
            self.x, self.y = nova
            restante -= passo
            if passo >= d:
                self.rastro.popleft()


class AudioAssistivo:
    def __init__(self, ativo=True):
        self.ativo = False
        self.espera = 0.0
        if ativo:
            try:
                pygame.mixer.init(frequency=22050, size=-16, channels=2)
                dados = array("h")
                for i in range(2205):
                    amostra = int(6500 * math.sin(2 * math.pi * 880 * i / 22050) * (1 - i / 2205))
                    dados.extend((amostra, amostra))
                self.som = pygame.mixer.Sound(buffer=dados.tobytes())
                self.canal = pygame.mixer.Channel(0)
                self.ativo = True
            except pygame.error:
                print("Áudio indisponível. A simulação continuará com alertas visuais.")

    def atualizar(self, dt, robo):
        self.espera = max(0, self.espera - dt)
        if not self.ativo or self.espera > 0 or robo.cor_alerta == VERDE_LIVRE:
            return
        leitura = min(robo.leituras_lidar, key=lambda r: r["distancia"], default=None)
        pan = 0.0
        if leitura and leitura["tipo"]:
            # Na tela, ângulo negativo é o lado esquerdo do robô.
            diferenca = (leitura["angulo"] - robo.angulo + math.pi) % (2 * math.pi) - math.pi
            pan = max(-1, min(1, diferenca / (robo.fov / 2)))
        self.canal.play(self.som)
        self.canal.set_volume((1 - pan) / 2, (1 + pan) / 2)
        self.espera = 0.55


class RoboCaoGuia:
    def __init__(self, x, y, rng=None):
        self.x, self.y = float(x), float(y)
        self.angulo = 0.0
        self.raio = 20
        self.velocidade_base = VELOCIDADE
        self.alcance_lidar = 165
        self.num_raios = 19
        self.fov = math.radians(150)
        self.rng = rng if rng is not None else random.Random()
        self.historico_lidar = [deque(maxlen=3) for _ in range(self.num_raios)]
        self.leituras_lidar = []
        self.status_assistivo = "Selecione um destino: 1, 2, 3 ou 4."
        self.estado = "PARADO"
        self.cor_alerta = VERDE_LIVRE
        self.passo_animacao = 0.0
        self.tutor = Tutor(x - GUIA, y)
        self.caminho = []
        self.indice_caminho = 0
        self.travessia_autorizada = False
        self.tempo_desvio = 0.0
        self.tempo_sem_progresso = 0.0
        self.ultimo_progresso = (x, y)

    def ler_lidar(self, obstaculos):
        """Interseção analítica, ruído, dropout e mediana temporal de 3 quadros."""
        self.leituras_lidar = []
        limites = [pygame.Rect(0, 0, 5, ALTURA), pygame.Rect(0, 0, AREA_MAPA_LARGURA, 5),
                   pygame.Rect(AREA_MAPA_LARGURA - 5, 0, 5, ALTURA),
                   pygame.Rect(0, ALTURA - 5, AREA_MAPA_LARGURA, 5)]
        objetos = obstaculos + [{"rect": r, "tipo": "parede"} for r in limites]
        for i in range(self.num_raios):
            ang = self.angulo - self.fov / 2 + i * self.fov / (self.num_raios - 1)
            fim = self.x + math.cos(ang) * self.alcance_lidar, self.y + math.sin(ang) * self.alcance_lidar
            encontrada, tipo = float(self.alcance_lidar), None
            for obs in objetos:
                corte = obs["rect"].clipline((self.x, self.y), fim)
                if corte:
                    d = min(distancia((self.x, self.y), p) for p in corte)
                    if d < encontrada:
                        encontrada, tipo = d, obs["tipo"]
            if self.rng.random() < 0.02:
                encontrada, tipo = float(self.alcance_lidar), None
            elif tipo is not None:
                encontrada = max(0, min(self.alcance_lidar, encontrada + self.rng.gauss(0, 1.5)))
            historico = self.historico_lidar[i]
            historico.append((encontrada, tipo))
            filtrada = median(item[0] for item in historico)
            # Tipo vem da amostra mais próxima da mediana, não da última falha.
            tipo_filtrado = min(historico, key=lambda item: abs(item[0] - filtrada))[1]
            self.leituras_lidar.append({"angulo": ang, "distancia": filtrada, "tipo": tipo_filtrado})

    def planejar(self, planejador, alvo):
        self.caminho = planejador.buscar((self.x, self.y), alvo)
        self.indice_caminho = 0
        self.tempo_desvio = self.tempo_sem_progresso = 0.0
        self.ultimo_progresso = (self.x, self.y)

    def mudar_estado(self, estado, mensagem, cor=VERDE_LIVRE):
        self.estado, self.status_assistivo, self.cor_alerta = estado, mensagem, cor

    def risco_veiculos(self, veiculos):
        for v in veiculos:
            zona = v.zona_varrida(1.0)
            for pessoa in (self, self.tutor):
                if distancia_retangulo(pessoa.x, pessoa.y, zona) < pessoa.raio + 8:
                    return True
        return False

    def decidir_navegacao(self, alvo, dt, planejador, semaforo, veiculos,
                          modo_autonomo=True, comando=(0, 0)):
        dentro_rua = RUA_Y - self.raio < self.y < RUA_Y + RUA_ALTURA + self.raio
        tutor_na_rua = RUA_Y - self.tutor.raio < self.tutor.y < RUA_Y + RUA_ALTURA + self.tutor.raio
        if self.travessia_autorizada and not dentro_rua and not tutor_na_rua:
            self.travessia_autorizada = False

        if self.risco_veiculos(veiculos):
            self.mudar_estado("FREIO_EMERGENCIA", "Veículo na zona prevista! Parada de segurança.", VERMELHO_PERIGO)
            return
        if modo_autonomo:
            if distancia((self.x, self.y), alvo) < 9:
                self.mudar_estado("DESTINO_ALCANCADO", "DESTINO ALCANÇADO COM SEGURANÇA!")
                return
            if not self.caminho:
                self.mudar_estado("SEM_ROTA", "Destino bloqueado. Escolha outro ponto.", LARANJA_ALERTA)
                return
            while self.indice_caminho < len(self.caminho) - 1 and distancia(
                    (self.x, self.y), self.caminho[self.indice_caminho]) < 0.4:
                self.indice_caminho += 1
            proximo = self.caminho[self.indice_caminho]
            angulo_alvo = math.atan2(proximo[1] - self.y, proximo[0] - self.x)
        else:
            self.angulo += comando[0] * 2.7 * dt
            angulo_alvo = self.angulo

        diferenca = (angulo_alvo - self.angulo + math.pi) % (2 * math.pi) - math.pi
        velocidade = self.velocidade_base
        estado, mensagem, cor = "SEGUINDO_ROTA", "Seguindo a rota A* e o piso tátil.", VERDE_LIVRE
        frente = [r for r in self.leituras_lidar if abs(
            (r["angulo"] - self.angulo + math.pi) % (2 * math.pi) - math.pi) < math.radians(35)]
        if frente and min(r["distancia"] for r in frente) < self.raio + 15 and not dentro_rua:
            esquerda = min(r["distancia"] for r in self.leituras_lidar[:9])
            direita = min(r["distancia"] for r in self.leituras_lidar[10:])
            diferenca += -0.7 if esquerda > direita else 0.7
            velocidade *= 0.4
            estado, mensagem, cor = "DESVIANDO", "Obstáculo próximo. Desvio local assistivo.", VERMELHO_PERIGO
        self.angulo += max(-2.8 * dt, min(2.8 * dt, diferenca))
        # Primeiro orienta o corpo; depois avança sem cortar a quina da grade.
        velocidade *= 1.0 if abs(diferenca) <= 2.8 * dt else 0.0
        # Folga do arnês: reduz proporcionalmente a velocidade após 10 px de tensão.
        tensao = max(0, distancia((self.x, self.y), (self.tutor.x, self.tutor.y)) - GUIA)
        if tensao > 10:
            velocidade *= 10 / tensao
        if not modo_autonomo:
            velocidade *= comando[1]
            estado, mensagem = "MANUAL", "Controle manual com barreira e freio ativos."
        else:
            velocidade = min(velocidade, distancia((self.x, self.y), proximo) / dt)

        proposta = self.x + math.cos(self.angulo) * velocidade * dt, self.y + math.sin(self.angulo) * velocidade * dt
        vai_entrar = RUA_Y - self.raio < proposta[1] < RUA_Y + RUA_ALTURA + self.raio
        if vai_entrar and not dentro_rua and not self.travessia_autorizada:
            corredor = pygame.Rect(FAIXA_X, RUA_Y, FAIXA_LARGURA, RUA_ALTURA)
            livre = not any(v.zona_varrida().colliderect(corredor) for v in veiculos)
            # A estimativa também leva em conta a velocidade reduzida pelo arnês.
            if semaforo.pode_atravessar(min(self.velocidade_base, max(1, velocidade))) and livre:
                self.travessia_autorizada = True
            else:
                self.mudar_estado("AGUARDANDO_SINAL", "Aguardando tempo seguro e faixa livre.", LARANJA_ALERTA)
                return
        nova = aplicar_barreira((self.x, self.y), proposta, self.raio, self.travessia_autorizada)
        if planejador.posicao_livre(*nova):
            self.passo_animacao += distancia((self.x, self.y), nova) * 0.25
            self.x, self.y = nova
        else:
            estado, mensagem, cor = "DESVIANDO", "C-Space bloqueado. Ajustando a rota.", LARANJA_ALERTA
        if self.travessia_autorizada:
            estado, mensagem = "ATRAVESSANDO", "Travessia autorizada. Monitorando veículos."
        self.mudar_estado(estado, mensagem, cor)

        if modo_autonomo:
            self.tempo_desvio = self.tempo_desvio + dt if estado == "DESVIANDO" else 0
            if distancia((self.x, self.y), self.ultimo_progresso) > 12:
                self.ultimo_progresso = (self.x, self.y)
                self.tempo_sem_progresso = 0
            else:
                self.tempo_sem_progresso += dt
            if self.tempo_desvio > 3.5 or self.tempo_sem_progresso > 3.5:
                self.planejar(planejador, alvo)
                self.mudar_estado("REPLANEJANDO", "Sem progresso por 3,5 s. Recalculando A*.", LARANJA_ALERTA)

    def desenhar(self, tela):
        # 1. Feixes do LiDAR
        for r in self.leituras_lidar:
            fim_x = self.x + math.cos(r["angulo"]) * r["distancia"]
            fim_y = self.y + math.sin(r["angulo"]) * r["distancia"]
            cor = VERDE_LIVRE if r["distancia"] >= self.alcance_lidar - 5 else VERMELHO_PERIGO
            pygame.draw.line(tela, cor, (self.x, self.y), (fim_x, fim_y), 1)
            if r["tipo"]:
                pygame.draw.circle(tela, BRANCO, (int(fim_x), int(fim_y)), 3)
        # 2. Arnês e tutor independente
        usu_x, usu_y = self.tutor.x, self.tutor.y
        pygame.draw.line(tela, ARNES_GUIA, (self.x, self.y), (usu_x, usu_y), 4)
        pygame.draw.circle(tela, (235, 235, 240), (int(usu_x), int(usu_y)), 12)
        pygame.draw.circle(tela, PRETO, (int(usu_x), int(usu_y)), 12, 2)
        # 3. Patas articuladas
        balanco = math.sin(self.passo_animacao) * 5
        offsets_patas = [(10 + balanco, -14), (10 - balanco, 14),
                         (-12 - balanco, -14), (-12 + balanco, 14)]
        for ox, oy in offsets_patas:
            ponto = rotacionar_ponto(self.x, self.y, self.x + ox, self.y + oy, self.angulo)
            pygame.draw.circle(tela, DETALHE_ROBO, ponto, 5)
        # 4. Tronco do cão-robô
        pontos_corpo = [rotacionar_ponto(self.x, self.y, self.x + ox, self.y + oy, self.angulo)
                        for ox, oy in [(16, -11), (16, 11), (-18, 11), (-18, -11)]]
        pygame.draw.polygon(tela, CORPO_ROBO, pontos_corpo)
        pygame.draw.polygon(tela, BRANCO, pontos_corpo, 2)
        # 5. Cabeça, orelhas e câmera
        cabeca = rotacionar_ponto(self.x, self.y, self.x + 21, self.y, self.angulo)
        pygame.draw.circle(tela, CABECA_ROBO, cabeca, 9)
        pygame.draw.circle(tela, DETALHE_ROBO, cabeca, 9, 2)
        for lado in (-10, 10):
            orelha = rotacionar_ponto(self.x, self.y, self.x + 19, self.y + lado, self.angulo)
            pygame.draw.circle(tela, DETALHE_ROBO, orelha, 4)
        # 6. Torre do LiDAR
        lidar = rotacionar_ponto(self.x, self.y, self.x + 3, self.y, self.angulo)
        pygame.draw.circle(tela, LARANJA_ALERTA, lidar, 5)


def criar_cenario():
    return [
        {"rect": pygame.Rect(230, 85, 45, 75), "tipo": "solo", "nome": "Banca / Hidrante"},
        {"rect": pygame.Rect(460, 160, 32, 32), "tipo": "solo", "nome": "Poste de Luz"},
        {"rect": pygame.Rect(380, 460, 40, 40), "tipo": "solo", "nome": "Lixeira Urbana"},
        {"rect": pygame.Rect(350, 75, 85, 65), "tipo": "suspenso", "nome": "Copa de Árvore"},
        # Toldo deslocado um pouco para liberar o desembarque da faixa no C-Space.
        {"rect": pygame.Rect(470, 490, 95, 65), "tipo": "suspenso", "nome": "Toldo de Loja"},
        {"rect": pygame.Rect(65, 35, 100, 40), "tipo": "edificacao", "nome": "Casa"},
        {"rect": pygame.Rect(680, 35, 85, 40), "tipo": "edificacao", "nome": "Padaria"},
        {"rect": pygame.Rect(680, 590, 85, 50), "tipo": "edificacao", "nome": "Mercado"},
        {"rect": pygame.Rect(260, 35, 60, 30), "tipo": "edificacao", "nome": "Prédio"},
    ]


# ==================== SIMULAÇÃO E TELEMETRIA ====================
class Simulacao:
    def __init__(self, seed=1, inicio=None, rng=None, audio=False):
        self.rng = rng if rng is not None else random.Random(seed)
        self.obstaculos = criar_cenario()
        self.planejador = Planejador(self.obstaculos)
        self.semaforo = Semaforo()
        self.transito = Transito(self.rng)
        self.robo = RoboCaoGuia(*(inicio or DESTINOS[4][1]), self.rng)
        self.audio = AudioAssistivo(audio)
        self.alvo = None
        self.nome_destino = "Selecione 1 a 4"
        self.modo_autonomo = True
        self.metricas = {"tempo": 0.0, "distancia": 0.0, "alertas_vermelhos": 0,
                         "freios_emergencia": 0, "viagens_concluidas": 0,
                         "colisoes": 0, "quase_colisoes": 0}
        self.estados = []
        self.contatos = set()
        self.proximidades = set()
        self.viagem_ativa = False
        self.chegou = False

    def selecionar_destino(self, ponto, nome):
        if not self.planejador.posicao_livre(*ponto):
            self.robo.mudar_estado("SEM_ROTA", "Ponto bloqueado no espaço de configuração.", LARANJA_ALERTA)
            return False
        self.alvo, self.nome_destino = tuple(ponto), nome
        self.chegou = False
        self.viagem_ativa = True
        self.robo.planejar(self.planejador, self.alvo)
        self.robo.mudar_estado("PLANEJANDO", "Calculando uma rota acessível com A*.")
        return True

    def adicionar_obstaculo(self, x, y):
        obs = {"rect": pygame.Rect(x - 22, y - 22, 44, 44),
               "tipo": self.rng.choice(["solo", "suspenso"]), "nome": "Obstáculo inserido"}
        margem = INFLACAO[obs["tipo"]]
        zona = obs["rect"].inflate(2 * margem, 2 * margem)
        # Mantém o corredor de travessia e não coloca objetos sobre entidades.
        faixa = pygame.Rect(FAIXA_X - 20, RUA_Y - 60, FAIXA_LARGURA + 40, RUA_ALTURA + 120)
        if zona.colliderect(faixa) or any(zona.collidepoint(p.x, p.y) for p in (self.robo, self.robo.tutor)):
            return
        self.obstaculos.append(obs)
        self.planejador = Planejador(self.obstaculos)
        if self.alvo:
            self.robo.planejar(self.planejador, self.alvo)

    def medir_seguranca(self):
        contatos, proximidades = set(), set()
        objetos = [("obs" + str(i), o["rect"]) for i, o in enumerate(self.obstaculos)]
        objetos += [("carro" + str(v.numero), v.rect) for v in self.transito.veiculos]
        for nome, pessoa in (("robo", self.robo), ("tutor", self.robo.tutor)):
            for identificador, rect in objetos:
                folga = distancia_retangulo(pessoa.x, pessoa.y, rect) - pessoa.raio
                chave = nome, identificador
                if folga < 0:
                    contatos.add(chave)
                elif folga < 12:
                    proximidades.add(chave)
        # Conta episódios de contato, não todos os quadros do mesmo contato.
        self.metricas["colisoes"] += len(contatos - self.contatos)
        self.metricas["quase_colisoes"] += len(proximidades - self.proximidades - self.contatos)
        self.contatos, self.proximidades = contatos, proximidades

    def atualizar(self, dt, comando=(0, 0)):
        self.semaforo.atualizar(dt)
        self.transito.atualizar(dt, self.semaforo)
        robo = self.robo
        sensores = self.obstaculos + [{"rect": v.rect, "tipo": "veiculo"} for v in self.transito.veiculos]
        robo.ler_lidar(sensores)
        anterior = (robo.x, robo.y)
        estado_anterior, cor_anterior = robo.estado, robo.cor_alerta
        if self.viagem_ativa:
            self.metricas["tempo"] += dt
            robo.decidir_navegacao(self.alvo, dt, self.planejador, self.semaforo,
                                   self.transito.veiculos, self.modo_autonomo, comando)
        elif not self.modo_autonomo:
            robo.decidir_navegacao((robo.x, robo.y), dt, self.planejador, self.semaforo,
                                   self.transito.veiculos, False, comando)
        if robo.estado != "FREIO_EMERGENCIA":
            robo.tutor.atualizar(robo, dt, self.obstaculos)
        self.metricas["distancia"] += distancia(anterior, (robo.x, robo.y))
        if robo.cor_alerta == VERMELHO_PERIGO and cor_anterior != VERMELHO_PERIGO:
            self.metricas["alertas_vermelhos"] += 1
        if robo.estado == "FREIO_EMERGENCIA" and estado_anterior != robo.estado:
            self.metricas["freios_emergencia"] += 1
        if not self.estados or self.estados[-1] != robo.estado:
            self.estados.append(robo.estado)
        if self.viagem_ativa and robo.estado == "DESTINO_ALCANCADO":
            self.metricas["viagens_concluidas"] += 1
            self.viagem_ativa, self.chegou = False, True
        self.medir_seguranca()
        self.audio.atualizar(dt, robo)


# ==================== RENDERIZAÇÃO ====================
def desenhar_ambiente_urbano(tela):
    tela.fill(CALÇADA_CLARA)
    pygame.draw.rect(tela, GRAMA, (0, 0, AREA_MAPA_LARGURA, 28))
    pygame.draw.rect(tela, GRAMA, (0, ALTURA - 28, AREA_MAPA_LARGURA, 28))
    pygame.draw.rect(tela, ASFALTO, (0, RUA_Y, AREA_MAPA_LARGURA, RUA_ALTURA))
    for y in (RUA_Y, RUA_Y + RUA_ALTURA):
        pygame.draw.line(tela, MEIO_FIO, (0, y), (AREA_MAPA_LARGURA, y), 4)
    for x in range(15, AREA_MAPA_LARGURA - 20, 45):
        if not 550 <= x <= 680:
            pygame.draw.line(tela, BRANCO, (x, 335), (x + 22, 335), 3)
    for y in range(RUA_Y + 12, RUA_Y + RUA_ALTURA - 12, 22):
        pygame.draw.rect(tela, BRANCO, (FAIXA_X, y, FAIXA_LARGURA, 12))
    pygame.draw.line(tela, BRANCO, (FAIXA_X - 18, 260), (FAIXA_X - 18, 323), 4)
    pygame.draw.line(tela, BRANCO, (FAIXA_X + FAIXA_LARGURA + 18, 345),
                     (FAIXA_X + FAIXA_LARGURA + 18, 410), 4)
    for piso in PISOS:
        pygame.draw.rect(tela, PISO_TATIL, piso)


def escrever_quebrado(tela, fonte, texto, x, y, largura, cor):
    linha = ""
    for palavra in texto.split():
        teste = (linha + " " + palavra).strip()
        if linha and fonte.size(teste)[0] > largura:
            tela.blit(fonte.render(linha, True, cor), (x, y))
            y += 18
            linha = palavra
        else:
            linha = teste
    tela.blit(fonte.render(linha, True, cor), (x, y))
    return y + 20


def desenhar_simulacao(tela, sim, fontes):
    titulo, fonte, pequena = fontes
    desenhar_ambiente_urbano(tela)
    robo = sim.robo
    if len(robo.caminho) > 1:
        pygame.draw.lines(tela, (65, 210, 235), False, robo.caminho, 2)
    for obs in sim.obstaculos:
        rect = obs["rect"]
        cor = ROXO_SUSPENSO if obs["tipo"] == "suspenso" else (70, 74, 82)
        if obs["tipo"] == "suspenso":
            pygame.draw.rect(tela, (90, 95, 102), rect.move(5, 5), border_radius=8)
        pygame.draw.rect(tela, cor, rect, border_radius=5)
        pygame.draw.rect(tela, BRANCO, rect, 2, border_radius=5)
        nome = "ALTO" if obs["tipo"] == "suspenso" else ("PRÉDIO" if obs["tipo"] == "edificacao" else "SOLO")
        texto = pequena.render(nome, True, BRANCO)
        tela.blit(texto, (rect.centerx - texto.get_width() // 2, rect.centery - 7))
    for tecla, (nome, ponto) in DESTINOS.items():
        pygame.draw.circle(tela, VERDE_LIVRE, ponto, 6)
        texto = pequena.render(f"{tecla}: {nome}", True, PRETO)
        tela.blit(texto, (ponto[0] - texto.get_width() // 2, ponto[1] + 17))
    if sim.alvo:
        pygame.draw.circle(tela, VERDE_LIVRE, sim.alvo, 20, 3)
    for v in sim.transito.veiculos:
        v.desenhar(tela)
    cor_carros = (VERDE_LIVRE if sim.semaforo.fase == "VERDE" else
                  LARANJA_ALERTA if sim.semaforo.fase == "AMARELO" else VERMELHO_PERIGO)
    pygame.draw.circle(tela, PRETO, (565, 222), 14)
    pygame.draw.circle(tela, cor_carros, (565, 222), 10)
    pygame.draw.circle(tela, PRETO, (693, 449), 14)
    pygame.draw.circle(tela, VERDE_LIVRE if sim.semaforo.fase == "PEDESTRE" else VERMELHO_PERIGO,
                       (693, 449), 10)
    robo.desenhar(tela)
    painel_x = AREA_MAPA_LARGURA
    pygame.draw.rect(tela, PRETO, (painel_x, 0, 260, ALTURA))
    pygame.draw.line(tela, BRANCO, (painel_x, 0), (painel_x, ALTURA), 2)
    x = painel_x + 12
    tela.blit(titulo.render("TELEMETRIA DOG-IA V2", True, CORPO_ROBO), (x, 15))
    textos = [f"Modo: {'AUTÔNOMO' if sim.modo_autonomo else 'MANUAL'}",
              f"Destino: {sim.nome_destino}", f"Estado: {robo.estado}",
              f"Sinal: {sim.semaforo.fase} ({sim.semaforo.restante:.1f}s)",
              f"LiDAR: {min(r['distancia'] for r in robo.leituras_lidar):.1f} px"]
    y = 47
    for texto in textos:
        tela.blit(fonte.render(texto, True, BRANCO), (x, y))
        y += 23
    pygame.draw.rect(tela, robo.cor_alerta, (x, 170, 236, 80), border_radius=8)
    escrever_quebrado(tela, fonte, robo.status_assistivo, x + 8, 179, 220, PRETO)
    m = sim.metricas
    linhas = [f"Tempo de viagem: {m['tempo']:.1f} s", f"Distância: {m['distancia']:.0f} px",
              f"Alertas vermelhos: {m['alertas_vermelhos']}", f"Freios de emergência: {m['freios_emergencia']}",
              f"Viagens concluídas: {m['viagens_concluidas']}", f"Colisões: {m['colisoes']}",
              f"Quase-colisões: {m['quase_colisoes']}", "", "CONTROLES:",
              "1 Mercado / 2 Farmácia", "3 Padaria / 4 Casa (voltar)", "Clique esq.: novo destino",
              "Clique dir.: criar obstáculo", "ESPAÇO: Manual / IA", "Setas: virar e avançar",
              "R: reiniciar / ESC: sair", "", "Ciano: rota A*", "Roxo: obstáculo suspenso",
              "Borda vermelha: carro infrator"]
    y = 265
    for texto in linhas:
        tela.blit(fonte.render(texto, True, BRANCO), (x, y))
        y += 20


# ==================== EXPERIMENTO SEM JANELA ====================
def executar_benchmark(quantidade, seed, tempo_limite):
    # O mesmo dt e as mesmas regras são usados na janela e no experimento.
    # As viagens alternam ida a um estabelecimento e volta para casa.
    rng = random.Random(seed)
    resultados = []
    ultimo_destino = DESTINOS[1]
    for i in range(quantidade):
        if i % 2 == 0:
            inicio = DESTINOS[4][1]
            ultimo_destino = DESTINOS[(i // 2) % 3 + 1]
            nome, ponto = ultimo_destino
        else:
            inicio = ultimo_destino[1]
            nome, ponto = DESTINOS[4]
        sim = Simulacao(inicio=inicio, rng=rng)
        sim.selecionar_destino(ponto, nome)
        for _ in range(math.ceil(tempo_limite * FPS)):
            sim.atualizar(1 / FPS)
            if sim.chegou or sim.robo.estado == "SEM_ROTA":
                break
        sucesso = sim.chegou and sim.metricas["colisoes"] == 0
        resultado = {"viagem": i + 1, "destino": nome, "sucesso": sucesso,
                     "chegou": sim.chegou, "estado_final": sim.robo.estado,
                     **{k: round(v, 3) if isinstance(v, float) else v for k, v in sim.metricas.items()},
                     "estados": sim.estados}
        resultados.append(resultado)
        print(f"Viagem {i + 1:02d} | {nome:8s} | {'OK' if sucesso else 'FALHA'} | "
              f"{sim.metricas['tempo']:.2f} s | colisões: {sim.metricas['colisoes']}")
    tempos = [r["tempo"] for r in resultados if r["sucesso"]]
    resumo = {"seed": seed, "viagens": quantidade, "sucessos": len(tempos),
              "taxa_sucesso": len(tempos) / quantidade,
              "tempo_medio_s": round(sum(tempos) / len(tempos), 3) if tempos else None,
              "colisoes": sum(r["colisoes"] for r in resultados),
              "quase_colisoes": sum(r["quase_colisoes"] for r in resultados),
              "freios_emergencia": sum(r["freios_emergencia"] for r in resultados)}
    print("\nResumo (sucesso = chegada sem colisão; tempo médio apenas dos sucessos):")
    print(json.dumps(resumo, indent=2, ensure_ascii=False))
    return {"resumo": resumo, "resultados": resultados}


def main():
    parser = argparse.ArgumentParser(description="Simulador assistivo DOG-IA V2")
    parser.add_argument("--benchmark", type=int, nargs="?", const=20, default=0, metavar="N")
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--tempo-limite", type=float, default=120.0, metavar="SEGUNDOS")
    parser.add_argument("--saida", help="Salva os resultados do benchmark em JSON")
    parser.add_argument("--sem-audio", action="store_true")
    args = parser.parse_args()
    if args.benchmark < 0 or not math.isfinite(args.tempo_limite) or args.tempo_limite <= 0:
        parser.error("A quantidade de viagens deve ser >= 0 e o tempo-limite deve ser positivo.")
    if args.benchmark:
        # Não inicializa display nem mixer: funciona sem monitor e placa de som.
        resultado = executar_benchmark(args.benchmark, args.seed, args.tempo_limite)
        if args.saida:
            with open(args.saida, "w", encoding="utf-8") as arquivo:
                json.dump(resultado, arquivo, indent=2, ensure_ascii=False)
        return

    pygame.display.init()
    pygame.font.init()
    tela = pygame.display.set_mode((LARGURA, ALTURA))
    pygame.display.set_caption("DOG-IA V2 — Cão-Guia Autônomo")
    clock = pygame.time.Clock()
    fontes = (pygame.font.SysFont("arial", 19, bold=True), pygame.font.SysFont("arial", 14),
              pygame.font.SysFont("arial", 12, bold=True))
    sim = Simulacao(seed=args.seed, audio=not args.sem_audio)
    sim.selecionar_destino(DESTINOS[1][1], DESTINOS[1][0])
    rodando = True
    acumulador = 0.0
    try:
        while rodando:
            # Passos fixos evitam saltos no meio-fio e mantêm o sensor em 60 Hz.
            # O relógio da simulação depende de dt, não do número de desenhos.
            acumulador += min(clock.tick(FPS) / 1000.0, 0.25)
            for evento in pygame.event.get():
                if evento.type == pygame.QUIT:
                    rodando = False
                elif evento.type == pygame.KEYDOWN:
                    if evento.key == pygame.K_ESCAPE:
                        rodando = False
                    elif evento.key == pygame.K_SPACE:
                        sim.modo_autonomo = not sim.modo_autonomo
                        if sim.modo_autonomo and sim.alvo:
                            sim.robo.planejar(sim.planejador, sim.alvo)
                    elif pygame.K_1 <= evento.key <= pygame.K_4:
                        nome, ponto = DESTINOS[evento.key - pygame.K_0]
                        sim.selecionar_destino(ponto, nome)
                    elif evento.key == pygame.K_r:
                        sim = Simulacao(seed=args.seed, audio=not args.sem_audio)
                        sim.selecionar_destino(DESTINOS[1][1], DESTINOS[1][0])
                elif evento.type == pygame.MOUSEBUTTONDOWN:
                    mx, my = evento.pos
                    if mx < AREA_MAPA_LARGURA:
                        if evento.button == 1:
                            sim.selecionar_destino((mx, my), "Ponto escolhido")
                        elif evento.button == 3:
                            sim.adicionar_obstaculo(mx, my)
            teclas = pygame.key.get_pressed()
            comando = (int(teclas[pygame.K_RIGHT]) - int(teclas[pygame.K_LEFT]),
                       int(teclas[pygame.K_UP]))
            while acumulador >= 1 / FPS:
                sim.atualizar(1 / FPS, comando)
                acumulador -= 1 / FPS
            if not sim.robo.leituras_lidar:
                sim.robo.ler_lidar(sim.obstaculos)
            desenhar_simulacao(tela, sim, fontes)
            pygame.display.flip()
    finally:
        pygame.quit()


if __name__ == "__main__":
    main()
