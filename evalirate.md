# Avaluació i valoració de puzzles (`eval.py` i `rate.py`)

---

## `eval.py` — Avaluació d'un puzzle

### Idea general

Per valorar si un puzzle és interessant, analitzem el seu graf d'estats
amb **quatre mesures** i **tres penalitzacions**. La puntuació final és
un enter de **1 a 5 estrelles**, calibrat perquè un puzzle mitjà del
repositori rebi 3★ i un puzzle difícil rebi 4-5★.

### Principis de disseny

**1. Un camí llarg sempre puntua alt**, independentment de la mida del
graf. Un puzzle de 52 moviments és difícil tant si el graf té 1.000 com
si en té 1.000.000 nodes.

**2. Un graf gran és positiu.** Molts estats possibles indiquen un espai
de joc ric i complex. Les mesures premien la complexitat en comptes de
penalitzar-la.

**3. Zero BFS globals.** Per a grafs de 500k–1M nodes, un BFS triga
desenes de segons. Totes les mesures s'obtenen de l'array de graus
(O(V) numpy) i del camí que ja calcula `solve()`. No es fa cap BFS
addicional sobre tot el graf.

---

### Les quatre mesures

#### M1 · Longitud absoluta del camí `(pes 45%)`

La mesura més important. Usa una **funció sigmoidea** amb referència
fixa, independent de la mida del graf:

```
M1 = 1 / (1 + exp(-0.10 × (path_len - 15)))
```

Escala orientativa:

| Moviments | M1   | Interpretació         |
|:---------:|:----:|----------------------|
| 5         | 0.27 | puzzle trivial        |
| 10        | 0.38 | puzzle fàcil          |
| 20        | 0.62 | puzzle mitjà          |
| 30        | 0.82 | puzzle difícil        |
| 52        | 0.97 | puzzle molt difícil   |

La sigmoide és millor que una escala lineal o logarítmica perquè
reflecteix la percepció humana: la diferència entre 5 i 10 moviments
és enorme, però entre 50 i 55 és gairebé imperceptible.

---

#### M2 · Complexitat del graf `(pes 25%)`

Combina la **mida** i la **densitat** del graf en una sola mesura:

```
M2 = log₂(n_nodes) × (n_edges / n_nodes) / 75
```

Un graf gran amb bona densitat d'arestes indica un espai d'estats ric.
Valors típics:

| Graf                        | M2   |
|-----------------------------|:----:|
| 16 nodes, 24 arestes        | 0.08 |
| 35k nodes, 78k arestes      | 0.44 |
| 1.1M nodes, 3.3M arestes    | 0.77 |

---

#### M3 · Varietat de graus al camí `(pes 20%)`

Mesura si el camí òptim passa per estats de connectivitat molt diferent:
alguns amb moltes opcions (interseccions) i d'altres amb poques
(callejons sense sortida). Un camí monòton és avorrit; un camí variat
és interessant.

Usa el **coeficient de variació** (desviació estàndard / mitjana) dels
graus dels nodes del camí, normalitzat a [0, 1]:

```
M3 = min(std(graus_camí) / mean(graus_camí), 1.0)
```

Es calcula en O(path_len) sobre l'array de graus numpy, sense cap BFS.

---

#### M4 · Escassetat dels goals `(pes 10%)`

Pocs goals relatius al total de nodes significa que és difícil arribar
a la solució per casualitat. Usa un **decaïment exponencial** del ratio:

```
M4 = exp(-5 × n_goals / n_nodes)
```

| Ratio goals/nodes | M4   |
|:-----------------:|:----:|
| 0.1%              | 0.99 |
| 1%                | 0.95 |
| 5%                | 0.78 |
| 15%               | 0.47 |
| 50%               | 0.08 |

---

### Les tres penalitzacions

#### P1 · Camí massa curt `(màxim -0.25)`

Si el camí mínim té menys de 10 moviments, el puzzle és massa fàcil
independentment de la resta de mesures:

```
P1 = 0.25 × (1 - path_len / 10)   si path_len < 10
```

#### P2 · Graf massa petit `(màxim -0.20)`

Menys de 100 nodes indica un puzzle trivial amb poques configuracions
possibles:

```
P2 = 0.20 × (1 - n_nodes / 100)   si n_nodes < 100
```

#### P3 · Massa goals `(màxim -0.15)`

Si més del 30% dels nodes del graf són estats finals, el jugador pot
arribar a la solució per accident molt fàcilment:

```
P3 = 0.15 × excess   si n_goals / n_nodes > 0.30
```

---

### Fórmula completa

```
score_brut      = 0.45×M1 + 0.25×M2 + 0.20×M3 + 0.10×M4
score_penalitzat = max(0, score_brut - P1 - P2 - P3)
raw              = score_penalitzat × 5.0
★ final          = max(1, min(5, round(raw)))   ∈ {1, 2, 3, 4, 5}
```

La puntuació és sempre un **enter de 1 a 5**. El valor decimal es mostra
amb `--verbose` per transparència.

---

### Calibratge

| Puzzle                              | ★ final |
|-------------------------------------|:-------:|
| f15847df (4 mov, 16 nodes)          | 1★      |
| sample1 (28 mov, 35k nodes)         | 3★      |
| a6552eee (52 mov, 1.1M nodes)       | 4★      |

---

### Ús

```bash
# Avaluació ràpida
python src/eval.py puzzles/sample1.json

# Carrega el graf ja construït (molt més ràpid per a grafs grans)
python src/eval.py puzzles/sample1.graphml

# Informe detallat de totes les mesures
python src/eval.py puzzles/sample1.json --verbose
```

Exemple de sortida amb `--verbose`:

```
Avaluant 'a6552eee'...
────────────────────────────────────────────────────
  Nodes del graf        : 1138276
  Arestes               : 3339482
  Estats finals (goals) : 177930
  Longitud camí mínim   : 52 moviments
────────────────────────────────────────────────────
  M1 longitud camí      : 0.974  (pes 45%)
  M2 complexitat graf   : 0.770  (pes 25%)
  M3 varietat al camí   : 0.412  (pes 20%)
  M4 escassetat goals   : 0.414  (pes 10%)
────────────────────────────────────────────────────
  Puntuació bruta       : 0.797
  Puntuació penalitzada : 0.797
  Puntuació escalada    : 0.797
────────────────────────────────────────────────────
  ★ Puntuació final     : 4 / 5  (3.99 abans d'arrodonir)
────────────────────────────────────────────────────
```

---

## `rate.py` — Enviament de valoracions al repositori

### Idea general

`rate.py` avalua un puzzle amb `eval.py` i envia la puntuació al
repositori compartit del professor. Les valoracions s'acumulen i donen
lloc a una mitjana col·lectiva. Quan un mateix usuari envia una nova
valoració, sobreescriu l'anterior.

### Token d'autenticació

El token es llegeix automàticament de:
1. La variable d'entorn `KLOTSKI_TOKEN`
2. El fitxer `.token` al directori arrel del projecte

```bash
# Opció recomanada: fitxer .token (afegir al .gitignore!)
echo "el_teu_token" > .token

# Alternativa: variable d'entorn
export KLOTSKI_TOKEN=el_teu_token
```

### Prioritat de fitxers

`rate.py` busca el fitxer del puzzle en aquest ordre:

```
puzzles/<id[:8]>.graphml   ← prioritat màxima (graf ja construït, molt ràpid)
puzzles/<id>.graphml
puzzles/<id[:8]>.json      ← construeix el graf internament
puzzles/<id>.json
```

Si existeix el `.graphml`, l'avaluació és molt més ràpida perquè
evita reconstruir el graf des de zero.

### Ús

```bash
# Valorar un puzzle concret
python src/rate.py abc12345

# Veure la puntuació sense enviar
python src/rate.py abc12345 --dry-run

# Informe detallat de les mesures
python src/rate.py abc12345 --verbose

# Valorar tots els puzzles descarregats
python src/rate.py --all

# Valorar tots en dry-run primer per revisar
python src/rate.py --all --dry-run
```

Exemple de sortida:

```
Avaluant 'a6552eee'...
  Carregant graf 'a6552eee.graphml'...
  [★] a6552eee: 4 / 5  → enviat
```

### Flux recomanat

```bash
# 1. Descarregar puzzles
python src/download.py --all

# 2. Generar els grafs (una sola vegada, és la part lenta)
for f in puzzles/*.json; do
    python src/graph.py "$f"
done

# 3. Revisar les puntuacions sense enviar
python src/rate.py --all --dry-run

# 4. Enviar
python src/rate.py --all
```