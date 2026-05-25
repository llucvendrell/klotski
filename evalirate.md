# Avaluació i valoració de puzzles (`eval.py` i `rate.py`)

---

## `eval.py` — Avaluació d'un puzzle

### Idea general

Per valorar si un puzzle és interessant, analitzem el seu graf d'estats amb **quatre mesures** i **tres penalitzacions**. La puntuació final és un enter de **1 a 5 estrelles**, calibrat perquè els puzzles del repositori rebin notes coherents amb la seva dificultat real.

### Principis de disseny

**1. Un camí llarg sempre puntua alt**, independentment de la mida del graf. Un puzzle de 52 moviments és difícil tant si el graf té 100 nodes com si en té 1.000.000.

**2. Un graf gran és un indicador positiu.** Molts estats possibles indiquen un espai de joc ric i complex. Les mesures premien la complexitat en comptes de penalitzar-la.

**3. Zero BFS globals addicionals.** Per a grafs de 500k–1M nodes, un BFS triga desenes de segons. Totes les mesures s'obtenen de l'array de graus (O(V) numpy) i del camí que ja calcula `solve()`. No es fa cap BFS addicional sobre tot el graf.

---

### Les quatre mesures

#### M1 · Longitud absoluta del camí `(pes 45%)`

La mesura més important. Quantifica directament la dificultat: quants moviments mínims cal per resoldre el puzzle.

Usem una **funció sigmoidea** amb referència fixa, independent de la mida del graf:

```
M1 = 1 / (1 + exp(-0.10 × (path_len - 15)))
```

| Moviments | M1   | Interpretació       |
|:---------:|:----:|---------------------|
| 5         | 0.27 | puzzle trivial      |
| 10        | 0.38 | puzzle fàcil        |
| 15        | 0.50 | puzzle mitjà        |
| 30        | 0.82 | puzzle difícil      |
| 52        | 0.97 | puzzle molt difícil |

**Per què sigmoide i no escala lineal?** La percepció humana de dificultat no és lineal: passar de 5 a 10 moviments és un salt enorme, però la diferència entre 50 i 55 és gairebé imperceptible. La sigmoide captura aquest comportament. A més, la referència és fixa (no depèn del diàmetre del graf, que requeriria un BFS addicional).

---

#### M2 · Complexitat del graf `(pes 25%)`

Combina la **mida** i la **densitat** del graf en una sola mesura O(1):

```
M2 = log₂(n_nodes) × (n_edges / n_nodes) / 75
```

Un graf gran amb bona densitat d'arestes indica un espai d'estats ric i difícil d'explorar per a un jugador.

| Graf                         | M2   |
|------------------------------|:----:|
| 16 nodes, 24 arestes         | 0.08 |
| 35k nodes, 78k arestes       | 0.44 |
| 1.1M nodes, 3.3M arestes     | 0.77 |

**Per què no normalitzar per la mida del graf directament?** Dividir per `n_nodes` donaria sempre el mateix valor per grafs de densitat similar independentment de la mida. El logaritme fa que grafs més grans puntuin progressivament millor, reflectint que un espai d'estats gran és genuïnament més difícil d'explorar.

---

#### M3 · Varietat de graus al llarg del camí `(pes 20%)`

Mesura si el camí òptim passa per estats de connectivitat molt diferent: alguns amb moltes opcions disponibles (interseccions) i d'altres amb poques (callejons sense sortida). Un camí monòton és previsible i avorrit; un camí variat és enganyós i interessant.

Usa el **coeficient de variació** (desviació estàndard / mitjana) dels graus dels nodes del camí:

```
M3 = min(std(graus_camí) / mean(graus_camí), 1.0)
```

Es calcula en O(path_len) sobre l'array de graus numpy, sense cap BFS addicional.

**Per què els graus del camí i no del graf sencer?** Els graus de tot el graf mesuren l'estructura global, però el que importa per a la dificultat és si el jugador es troba amb decisions complicades al llarg del camí que ha de fer. Dos puzzles amb el mateix graf però camins òptims molt diferents poden tenir dificultats molt diverses.

---

#### M4 · Escassetat dels goals `(pes 10%)`

Pocs goals relatius al total de nodes significa que és difícil arribar a la solució per casualitat. Usa un **decaïment exponencial** del ratio goals/nodes:

```
M4 = exp(-5 × n_goals / n_nodes)
```

| Ratio goals/nodes | M4   | Interpretació              |
|:-----------------:|:----:|----------------------------|
| 0.1%              | 0.99 | molt difícil d'encertar    |
| 1%                | 0.95 | difícil                    |
| 5%                | 0.78 | moderat                    |
| 15%               | 0.47 | relativament fàcil         |
| 50%               | 0.08 | quasi impossible no trobar |

**Per què exponencial i no lineal?** El decaïment exponencial reflecteix que la probabilitat d'arribar a un goal per atzar creix de forma no lineal amb la proporció de goals. Un 50% de nodes finals és cualitativamente diferent d'un 5%.

---

### Les tres penalitzacions

#### P1 · Camí massa curt `(màxim -0.25)`

Un puzzle que es resol en menys de 10 moviments no és interessant independentment de la resta de mesures. La penalització és proporcional a quant per sota del llindar:

```
P1 = 0.25 × (1 - path_len / 10)   si path_len < 10
```

#### P2 · Graf massa petit `(màxim -0.20)`

Menys de 100 nodes indica un puzzle amb poques configuracions possibles, trivial per definició:

```
P2 = 0.20 × (1 - n_nodes / 100)   si n_nodes < 100
```

#### P3 · Massa goals `(màxim -0.15)`

Si més del 30% dels nodes del graf són estats finals, el jugador pot arribar a la solució per accident molt fàcilment:

```
P3 = 0.15 × excess   si n_goals / n_nodes > 0.30
```

---

### Fórmula completa

```
score_brut       = 0.45×M1 + 0.25×M2 + 0.20×M3 + 0.10×M4
score_penalitzat = max(0, score_brut - P1 - P2 - P3)
raw              = score_penalitzat × 5.0
★ final          = max(1, min(5, round(raw)))   ∈ {1, 2, 3, 4, 5}
```

La puntuació és sempre un **enter de 1 a 5**. El valor decimal es mostra amb `--verbose` per transparència.

---

### Calibratge

| Puzzle                          | path_len | n_nodes   | ★ final |
|---------------------------------|:--------:|:---------:|:-------:|
| f15847df (trivial)              | 4        | 16        | 1★      |
| sample1 (mitjà)                 | 28       | 35.976    | 3★      |
| a6552eee (difícil)              | 52       | 1.138.276 | 4★      |

---

### Ús

```bash
# A partir del JSON (construeix el graf internament)
python src/eval.py puzzles/sample1.json

# A partir del graphml (molt més ràpid, recomanat per a grafs grans)
python src/eval.py puzzles/sample1.graphml

# Informe detallat de totes les mesures
python src/eval.py puzzles/sample1.json --verbose
```

Exemple de sortida amb `--verbose`:

```
Avaluant 'a6552eee'...
────────────────────────────────────────────────────────
  Nodes del graf        : 1138276
  Arestes               : 3339482
  Estats finals (goals) : 177930
  Longitud camí mínim   : 52 moviments
────────────────────────────────────────────────────────
  M1 longitud camí      : 0.974  (pes 45%)
  M2 complexitat graf   : 0.770  (pes 25%)
  M3 varietat al camí   : 0.412  (pes 20%)
  M4 escassetat goals   : 0.414  (pes 10%)
────────────────────────────────────────────────────────
  Puntuació bruta       : 0.797
  Puntuació penalitzada : 0.797
  Puntuació escalada    : 0.797
────────────────────────────────────────────────────────
  ★ Puntuació final     : 4 / 5  (3.99 abans d'arrodonir)
────────────────────────────────────────────────────────
```

---

### Dificultats trobades

#### D1: Totes les mesures donaven el mateix valor per a puzzles de mides molt diferents

**Problema:** les mesures estaven normalitzades per constants fixes (ex: `REF_PATH_LEN = 50`) que no s'adaptaven a la mida real del graf. Un puzzle petit de 4 moviments i un de gran de 52 podien tenir M1 similars. Amb `sample1` (28 moviments), la versió inicial donava M2 = 0.999 i M5 = 1.000 sempre, independentment del puzzle.

**Causa:** normalitzar `path_len / path_len` (on el denominador era el propi camí) donava sempre 1.0. I normalitzar per una constant fixa gran feia que la mesura fos sempre propera a 0 o 1 sense discriminar.

**Solució:** adoptar mesures que siguin naturalment independents de la mida. La sigmoide per a M1 té una referència semàntica fixa (15 moviments = 0.5 de dificultat), i M2 usa `log₂(nodes) × densitat` que creix de forma natural amb la complexitat sense requerir normalització externa.

---

#### D2: El clustering de graf era sempre 0.0

**Problema:** la versió inicial usava el coeficient de clustering global com a mesura de "zones" del puzzle. Sempre donava exactament 0.0.

**Causa:** el clustering mesura l'existència de triangles en el graf (A-B, B-C, A-C connectats). En un graf de puzzles lliscants, dos estats que difereixen en un moviment quasi mai estan connectats directament per un altre moviment, de manera que no es formen triangles per construcció matemàtica.

**Solució:** substituir per M3 (varietat de graus al camí), que és una mesura semànticament millor (captura si el camí és enganyós) i no pateix d'aquest problema estructural.

---

#### D3: La modularitat de Louvain trigava >20 minuts en grafs grans

**Problema:** una versió anterior usava `minimize_blockmodel_dl` (algorisme de Louvain) com a M3. Per a grafs de 500k nodes trigava més de 20 minuts i de vegades no acabava mai.

**Causa:** l'algorisme de Louvain és O(V²) en el pitjor cas. Per a 500k nodes, 500.000² = 250 bilions d'operacions.

**Solució:** eliminar completament qualsevol algorisme quadràtic. M3 ara usa el coeficient de variació dels graus del camí òptim, que és O(path_len) sobre un array numpy ja disponible. Temps: <1ms.

---

#### D4: `apply_move` fallava en reconstruir el camí per a M3

**Problema:** per calcular M3 calia saber quins nodes del graf formen el camí òptim. La versió anterior reconstruïa el camí aplicant `apply_move` pas a pas, però fallava amb `ValueError: Moviment invàlid` perquè alguns moviments tenien distància > 1.

**Causa:** `apply_move` valida físicament cada pas. Si la peça ha de lliscar 2 caselles, el moviment `(peça, "S", 2)` falla perquè intenta aplicar-lo com un sol salt en comptes de dos passos.

**Solució:** reconstruir el camí directament des del graf amb `gt.shortest_path`, que retorna la seqüència de vèrtexs sense validar moviments. Els índexs dels vèrtexs s'usen per accedir als graus via numpy.

---

#### D5: La puntuació era la mateixa per a puzzles molt diferents

**Problema:** `sample1` (28 moviments, 2.412 goals, 35k nodes) treïa 3.11★. Un puzzle de 4 moviments i 16 nodes treïa 0.16★. Però altres puzzles molt grans i difícils també treïen ~1★.

**Causa:** les penalitzacions eren binàries (o s'aplicaven o no) i massa fortes, i la corba quadràtica comprimia massa els valors intermedis. A més, la mesura de goals no tenia en compte la proporció relativa.

**Solució:** canviar a penalitzacions proporcionals i graduals, eliminar la corba quadràtica (la sigmoide de M1 ja és prou discriminadora), i calibrar els paràmetres comparant la puntuació calculada amb les valoracions reals del repositori (a6552eee tenia una mitjana de 4★ al repositori i el nostre eval li donava 4★).

---

## `rate.py` — Enviament de valoracions al repositori

### Idea general

`rate.py` avalua un puzzle amb `eval.py` i envia la puntuació (enter 1-5) al repositori compartit del professor. Les valoracions s'acumulen i donen lloc a una mitjana col·lectiva. Quan el mateix usuari envia una nova valoració, sobreescriu l'anterior, cosa que permet anar millorant l'algorisme d'avaluació.

### Token d'autenticació

El token es distribueix individualment per correu de la UPC. Cal guardar-lo en un lloc segur i **mai posar-lo al codi font** per evitar filtrar-lo accidentalment al repositori git.

```bash
# Opció 1 (recomanada): fitxer .token a l'arrel del projecte
echo "el-teu-token-aqui" > .token

# Afegir al .gitignore per no pujar-lo accidentalment
echo ".token" >> .gitignore

# Opció 2: variable d'entorn (es perd quan es tanca el terminal)
export KLOTSKI_TOKEN=el-teu-token-aqui
```

`rate.py` llegeix el token automàticament en aquest ordre: primer la variable d'entorn `KLOTSKI_TOKEN`, i si no existeix, el fitxer `.token`.

### Prioritat de fitxers

`rate.py` busca el fitxer del puzzle en aquest ordre, prioritzant el `.graphml` perquè evita reconstruir el graf:

```
puzzles/<id[:8]>.graphml  ← prioritat màxima (graf ja construït, molt més ràpid)
puzzles/<id>.graphml
puzzles/<id[:8]>.json     ← construeix el graf internament (~30s per a grafs grans)
puzzles/<id>.json
```

### Ús

```bash
# Veure la puntuació sense enviar (recomanat per comprovar primer)
python src/rate.py f15847df --dry-run

# Informe detallat de les mesures
python src/rate.py f15847df --verbose

# Valorar i enviar un puzzle concret
python src/rate.py f15847df

# Valorar tots els puzzles descarregats en dry-run primer
python src/rate.py --all --dry-run

# Enviar tots
python src/rate.py --all
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
python src/download.py

# 2. Generar els grafs una sola vegada (la part lenta)
for f in puzzles/*.json; do
    python src/graph.py "$f"
done

# 3. Revisar les puntuacions sense enviar
python src/rate.py --all --dry-run

# 4. Enviar
python src/rate.py --all
```

### Dificultats trobades

#### D1: `evaluate() got multiple values for argument 'verbose'`

**Problema:** cridar `evaluate(puzzle, g, verbose=verbose)` donava error de Python.

**Causa:** `verbose` és el tercer argument posicional de `evaluate(puzzle, g, verbose)`. Passar-lo com a keyword argument (`verbose=verbose`) quan ja s'havia passat posicionalment causava el conflicte.

**Solució:** cridar sempre com a posicional: `evaluate(puzzle, g, verbose)`.

---

#### D2: `evaluate() takes from 1 to 2 positional arguments but 3 were given`

**Problema:** `rate.py` cridava `evaluate(puzzle, g, verbose)` però `eval.py` tenia una versió antiga amb signatura `evaluate(puzzle, verbose)`.

**Causa:** desincronització entre versions de `eval.py` i `rate.py` durant el desenvolupament. El `rate.py` esperava la nova signatura amb el graf com a paràmetre, però `eval.py` no s'havia actualitzat.

**Solució:** assegurar que `evaluate` té la signatura `evaluate(puzzle, g=None, verbose=False)` amb `g` opcional. Així tant `rate.py` com el CLI poden cridar-la de formes diferents.

---

#### D3: La puntuació enviada era un float però el servidor espera un enter

**Problema:** la versió inicial de `rate.py` mostrava i enviava `stars:.2f / 5.00` (float), però el sistema de valoració del repositori usa enters de 1 a 5.

**Solució:** `evaluate()` retorna directament `max(1, min(5, round(raw)))`, un enter sempre dins del rang [1, 5]. `rate.py` mostra `{stars} / 5` (sense decimals) i envia l'enter al servidor.