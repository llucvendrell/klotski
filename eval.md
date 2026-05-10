# Estratègia d'avaluació de puzzles (`eval.py`)

## Idea general

Per valorar si un puzzle és *interessant*, construïm el seu graf d'estats
i n'analitzem l'estructura amb **cinc mesures** i **dues penalitzacions**.
La puntuació final passa per una **corba quadràtica** que fa l'escala
estricta: només els puzzles genuïnament excel·lents assoleixen puntuacions
altes. Un puzzle mediocre que treia 2.5★ amb una escala lineal, amb aquesta
estratègia treu 1.25★.

---

## Les cinc mesures

### M1 · Longitud del camí mínim `(pes 30%)`

La mesura més directa: quants moviments mínims cal per resoldre el puzzle.

Usem una **escala logarítmica** perquè la percepció humana de dificultat
no és lineal: passar de 5 a 10 moviments és un salt enorme, però la
diferència entre 45 i 50 és gairebé imperceptible.

A més, apliquem una **penalització interna** si el camí és molt curt
(menys de 15 moviments): un puzzle trivial no pot treure bona nota per
M1 encara que el logaritme li donés un valor acceptable.

```
base = log(path_len + 1) / log(REF_PATH_LEN + 1)
M1   = base × (path_len / 15)   si path_len < 15
M1   = base                      en cas contrari
```

---

### M2 · Entropia de Shannon dels graus `(pes 20%)`

Mesura com de **variada** és l'estructura de connexions del graf. Un graf
on tots els nodes tenen el mateix grau (graella regular) té entropia 0:
és previsible. Un graf amb nodes molt connectats barrejats amb callejons
sense sortida té entropia alta: és ric i enganyós.

```
M2 = H(distribució de graus) / log₂(n_nodes)   ∈ [0, 1]
```

---

### M3 · Modularitat de comunitats `(pes 20%)`

Detecta si el graf es divideix en **zones densament connectades internament**
però poc connectades entre elles: la sensació de "fases" en un puzzle.
L'algorisme de Louvain troba automàticament la millor divisió en comunitats.

```
Q ~ 0.0 → graf homogeni (puzzle caòtic, sense fases)
Q ~ 0.3 → comunitats significatives (puzzle amb estructura clara)
Q ~ 1.0 → comunitats perfectament separades
```

> **Per què no el clustering?** El coeficient de clustering mesura
> l'existència de triangles en el graf. En grafs de puzzles lliscants
> el clustering és sempre exactament **0.0** per construcció matemàtica:
> dos estats que difereixen en un moviment quasi mai estan connectats
> directament per un altre moviment. La modularitat no té aquesta limitació.

---

### M4 · Excentricitat mostrejada de l'inici `(pes 15%)`

L'excentricitat d'un node és la distància màxima a qualsevol altre node.
Un inici al **centre** del graf dona molta llibertat al jugador (puzzle
fàcil); un inici a la **perifèria** limita les opcions (puzzle difícil).

```
M4 = excentricitat(inici) / diàmetre(graf)   ∈ [0, 1]
```

> **Millora respecte la versió anterior:** en comptes d'aproximar el
> diàmetre amb l'excentricitat de l'inici (que sempre donava M4 = 1.0),
> ara **estimem el diàmetre real per mostreig**: fem BFS des de
> `DIAM_SAMPLE_SIZE = 200` nodes aleatoris i ens quedem el màxim.
> Això dona una estimació robusta a cost controlat, evitant el BFS
> des de tots els nodes (massa lent per a grafs grans).

---

### M5 · Dificultat ponderada dels goals `(pes 15%)`

Combina dos factors que penalitzen simultàniament:

**a) Distància mitjana:** cada goal contribueix proporcionalment a la
seva distància respecte el camí mínim. Un goal proper contribueix poc
(el jugador hi arriba per accident); un goal llunyà contribueix gairebé
el màxim.

**b) Factor d'escassetat:** molts goals indiquen que quasi qualsevol
configuració és vàlida, cosa que fa el puzzle fàcil. El factor decau
logarítmicament amb el nombre de goals:

```
factor_escassetat = 1 / log₂(n_goals + 1)

  1 goal    → factor 1.00   (molt difícil d'encertar)
  10 goals  → factor 0.29
  100 goals → factor 0.15
  2412 goals → factor 0.09  (gairebé qualsevol camí acaba bé)
```

```
M5 = mitjana(dist_goal_i / path_len) × factor_escassetat
```

> **Millora respecte la versió anterior:** la versió anterior donava
> sempre M5 = 1.0 perquè no tenia en compte l'abundància de goals.
> Ara un puzzle amb 2412 goals automàticament té M5 molt baix, reflectint
> que és fàcil acabar-lo per casualitat.

Per eficiència, si hi ha més de `GOAL_SAMPLE_SIZE = 100` goals, es
mostreja aleatòriament.

---

## Les dues penalitzacions

### P2 · Linealitat del camí `(màxim -0.25)`

Compara el **grau mitjà dels nodes del camí òptim** amb el grau mitjà
global del graf. Si els nodes de la solució tenen molts menys veïns que
la mitjana, la solució passa per zones on el jugador no té alternatives
reals: el puzzle és quasi un laberint recte.

Un bon puzzle hauria de tenir moments de decisió genuïna: el jugador té
opcions però ha de triar la correcta.

```
ratio = grau_mitjà(nodes_camí) / grau_mitjà(tot_el_graf)
P2    = 0.25 × max(0, 1 - ratio)
```

---

### P3 · Goal massa proper a l'inici `(màxim -0.30)`

Si existeix un goal accessible en molt pocs moviments, el jugador pot
resoldre el puzzle **per accident**. La penalització és proporcional a
quant per sota del llindar (`NEAR_GOAL_THRESHOLD = 5`) cau la distància
mínima:

```
si min_dist < 5:
    P3 = 0.30 × (1 - min_dist / 5)

Exemples:
  goal a distància 0 → P3 = 0.30 (màxim, ja resolt!)
  goal a distància 2 → P3 = 0.18
  goal a distància 4 → P3 = 0.06
  goal a distància ≥ 5 → P3 = 0.00
```

---

## Escala estricta (corba quadràtica)

Un cop aplicades les penalitzacions, la puntuació passa per una **corba
quadràtica** abans de convertir-se en estrelles:

```
stars = score² × 5.0
```

Això comprimeix els valors intermedis cap avall i fa que només els puzzles
genuïnament excel·lents assoleixin puntuacions altes:

| Puntuació bruta | Estrelles lineals | Estrelles amb corba |
|:-:|:-:|:-:|
| 0.3 | 1.50 ★ | 0.45 ★ |
| 0.5 | 2.50 ★ | 1.25 ★ |
| 0.7 | 3.50 ★ | 2.45 ★ |
| 0.8 | 4.00 ★ | 3.20 ★ |
| 0.9 | 4.50 ★ | 4.05 ★ |
| 1.0 | 5.00 ★ | 5.00 ★ |

---

## Fórmula completa

```
score_brut      = 0.30×M1 + 0.20×M2 + 0.20×M3 + 0.15×M4 + 0.15×M5
score_penalitzat = max(0, score_brut - P2 - P3)
★ final          = score_penalitzat² × 5.0
```

---

## Ús

```bash
# Puntuació ràpida
python src/eval.py puzzles/sample1.json

# Informe detallat de totes les mesures
python src/eval.py puzzles/sample1.json --verbose
```

Exemple de sortida amb `--verbose`:

```
Avaluant 'sample1'...
────────────────────────────────────────────────────
  Nodes del graf        : 35976
  Arestes               : 78216
  Estats finals (goals) : 2412
  Longitud camí mínim   : 28 moviments
────────────────────────────────────────────────────
  M1 longitud camí      : 0.856  (pes 30%)
  M2 entropia graus     : 0.158  (pes 20%)
  M3 modularitat        : 0.169  (pes 20%)
  M4 excentricitat inici: 0.743  (pes 15%)
  M5 dificultat goals   : 0.083  (pes 15%)
────────────────────────────────────────────────────
  Puntuació bruta       : 0.432
  P2 linealitat camí    : -0.041  (solució massa única)
  P3 goal massa proper  : -0.000
  Puntuació penalitzada : 0.391
  Escala estricta (²)   : 0.153
────────────────────────────────────────────────────
  ★ Puntuació final     : 1.53 / 5.00
────────────────────────────────────────────────────
```

Estructura clara en tres capes: cada mesura és una funció independent (measure_path_length, measure_ratio, etc.), les penalitzacions estan separades, i evaluate() ho combina tot. Això fa que sigui fàcil ajustar un pes o una mesura sense tocar la resta.
measure_bridges usa label_biconnected_components de graph-tool, que és la forma correcta i eficient de trobar ponts en C++. Retorna una propietat d'arestes on True significa que és un pont.
--verbose mostra totes les mesures intermèdies, cosa molt útil per calibrar els pesos quan provis puzzles reals. Si veus que M2 sempre surt 0.95 i no diferencia res, hauràs d'ajustar REF_N_NODES.
Els paràmetres estan tots al capdamunt (W_PATH, REF_PATH_LEN, GOAL_THRESHOLD...) per facilitar l'ajust sense haver de llegir el cos de les funcions. Quan provis amb puzzles reals, probablement hauràs de tocar REF_PATH_LEN (ara calibrat per a 40 moviments màxim) i NODE_THRESHOLD.
Per provar-ho:
bashpython src/eval.py puzzles/f15847df.json --verbose





Categoria 1: Dificultat de la solució
Aquestes mesures parlen de com de "dur" és el puzzle:

Longitud del camí mínim — quants moviments mínims cal per resoldre'l. Un puzzle de 3 moviments és trivial, un de 50 és interessant.
Amplada del graf — quants estats existeixen en total. Molts estats = moltes possibilitats = més confús per al jugador.
Ratio camí/estats — longitud del camí dividida pel total d'estats. Un camí curt en un graf gran significa que la solució és difícil de trobar.


Categoria 2: Estructura del graf
Aquestes mesures parlen de la "forma" del puzzle:

Nombre de ponts — arestes que si s'eliminen desconnecten el graf. Els ponts indiquen que el jugador ha de passar per un moviment concret sense alternativa. Molts ponts = puzzle lineal i avorrit. Cap pont = massa llibertat.
Nombre de components connexes — normalment hauria de ser 1. Si n'hi ha més, hi ha zones del taulell inaccessibles.
Diàmetre del graf — la distància màxima entre qualsevol parell de nodes. Un diàmetre gran indica que el puzzle té molts estats "llunyans" entre si.
Nombre d'estats finals — si n'hi ha molts, el puzzle és fàcil perquè hi ha moltes solucions. Si n'hi ha pocs, és més difícil.


Categoria 3: "Engany" del puzzle
Aquestes mesures capturen si el puzzle té trampes:

Distància mínima vs distància màxima fins a un estat final — si la diferència és gran, hi ha molts camins "falsos" que semblen correctes però allunyen de la solució.
Nombre de "dead ends" — nodes amb un sol veí (fulles del graf). Molts dead ends = molts calaixos sense sortida = frustració interessant.
Centralitat de l'estat inicial — si l'estat inicial és molt "central" al graf, el jugador té molta llibertat però pot perdre's. Si és perifèric, el camí és més directe.


Possibles fórmules de combinació
Aquí és on has de decidir tu subjectivament. Tres enfocaments possibles:
Opció A — Suma ponderada simple:
estreles = (w1 * longitud_camí + w2 * ratio_camí_estats + w3 * ponts) / normalitzador
Fàcil d'ajustar però poc sofisticada.
Opció B — Penalitzacions i bonificacions:
puntuació = longitud_camí
           + bonus si hi ha ponts (estructura interessant)
           - penalització si hi ha massa estats finals (massa fàcil)
           - penalització si el camí és > 80% del diàmetre (massa lineal)
Opció C — Normalització per percentils:
Calcules cada mesura per a tots els puzzles del repositori, i valores cada puzzle segons on cau en la distribució. El 20% superior en dificultat obté 5 estrelles, etc. Té l'avantatge que les puntuacions s'adapten soles quan arriben puzzles nous.

La meva recomanació
Combinaria tres mesures principals amb l'Opció B:

Longitud del camí mínim — pes alt, és la més intuïtiva
Ratio camí/estats totals — captura si la solució és difícil de trobar
Nombre de ponts — captura si el puzzle té estructura interessant

I afegiria dues penalitzacions:

Si hi ha massa estats finals (puzzle massa fàcil)
Si el graf és massa petit (puzzle trivial)