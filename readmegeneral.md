# Klotski — Pràctica 2 d'AP2

Projecte de resolució i generació de trencaclosques de peces lliscants (sliding block puzzles) basat en grafs d'estats.

---

## Índex

1. [Instal·lació i entorn](#instal·lació-i-entorn)
2. [Eines proporcionades](#eines-proporcionades)
3. [Eines implementades](#eines-implementades)
   - [download.py](#downloadpy)
   - [graph.py](#graphpy)
   - [solve.py](#solvepy)
   - [eval.py](#evalpy)
   - [rate.py](#ratepy)
   - [generate.py](#generatepy)
4. [Flux de treball complet](#flux-de-treball-complet)

---

## Instal·lació i entorn

```bash
# Clonar el repositori
git clone https://github.com/pauek/klotski.git
cd klotski

# Instal·lar dependències amb Pixi
pixi install

# Activar l'entorn (SEMPRE cal fer-ho abans d'executar qualsevol script)
pixi shell
```

Un cop actiu, el terminal mostra el prefix `(Klotski)`.

> **⚠️ Dificultat freqüent:** Si apareix `ModuleNotFoundError: No module named 'graph_tool'` o `No module named 'pygame'`, significa que s'està executant Python fora de l'entorn Pixi. Solució: activar `pixi shell` primer, o usar la forma alternativa `pixi run python src/...` que no requereix activar l'entorn manualment.

---

## Eines proporcionades

Aquests scripts vénen donats i no s'han modificat.

### `play.py` — Joc interactiu

```bash
python src/play.py puzzles/sample1.json
```

Obre una finestra gràfica per jugar al puzzle manualment arrossegant les peces amb el ratolí. Tecles: `R` reinicia, `Esc` surt.

---

### `image.py` — Imatge de l'estat inicial

```bash
python src/image.py puzzles/sample1.json
```

Genera un fitxer `.png` amb la representació visual de l'estat inicial del puzzle.

---

### `movie.py` — GIF animat de la solució

```bash
python src/movie.py puzzles/sample1.json puzzles/sample1.sol.json
```

Genera un GIF animat que mostra la seqüència de moviments de la solució. Requereix que `solve.py` hagi generat prèviament el fitxer `.sol.json`.

---

### `3D_view.py` — Visualitzador 3D del graf

```bash
# Sense solució
python src/3D_view.py puzzles/sample1.graphml

# Amb solució ressaltada en groc
python src/3D_view.py puzzles/sample1.graphml puzzles/sample1.sol.json
```

Obre el navegador amb una visualització 3D interactiva del graf d'estats.

---

## Eines implementades

### `download.py`

Descarrega puzzles del repositori compartit del professor (`https://klotski.pauek.dev`).

#### Com funciona

El repositori exposa dos endpoints:
- `GET /api/puzzles` → llista dels 100 puzzles amb millor valoració
- `GET /api/puzzles/<id>` → puzzle individual en format JSON

#### Ús

```bash
# Descarregar tots els puzzles del rànking
python src/download.py

# Descarregar un puzzle concret per ID
python src/download.py f15847df
```

Els puzzles es desen a `puzzles/<id[:8]>.json`.

#### Detalls tècnics

- Usa únicament `urllib` de la biblioteca estàndard (sense `requests`), consistent amb l'exemple de l'enunciat.
- Valida cada puzzle amb `Puzzle.from_json()` abans de desar-lo: si el servidor retorna quelcom malformat, no es desa i es mostra `[✗]`.
- Mostra el progrés amb `[✓]` o `[✗]` per cada puzzle.

---

### `graph.py`

Construeix el graf d'estats d'un puzzle i el desa en format `.graphml`.

#### Com funciona

Cada node del graf representa una disposició de les peces. Dues disposicions estan connectades per una aresta si es pot passar d'una a l'altra amb un sol moviment vàlid. L'exploració es fa amb DFS iteratiu des de l'estat inicial.

#### Ús

```bash
python src/graph.py puzzles/sample1.json
# genera: puzzles/sample1.graphml

python src/graph.py puzzles/sample1.json puzzles/output.graphml
# genera a una ruta específica
```

#### Dificultat: arestes duplicades causaven errors a `movie.py`

El `graph.py` original afegia sempre `g.add_edge(current_v, next_v)` sense comprovar si l'aresta ja existia. En un graf no dirigit, quan el DFS visita A i troba B afegeix A-B; però quan després visita B i troba A (ja visitat), torna a afegir A-B. Això dobla el nombre d'arestes i causava que `shortest_path` retornés camins no vàlids, provocant l'error `Moviment invàlid` a `movie.py`.

**Solució:** la guarda `if src_idx < dst_idx` garanteix que cada aresta s'afegeix exactament una vegada:

```python
# Versió original (bugada): afegeix duplicats
g.add_edge(current_v, next_v)

# Versió corregida: cada aresta s'afegeix una sola vegada
if src_idx < dst_idx:
    g.add_edge(src_idx, dst_idx)
```

#### Millora: canonicalització de peces iguals

Si hi ha dues peces amb la mateixa forma, intercanviar-les dona el mateix estat visual però un `State` diferent. Sense canonicalització, es creen dos nodes separats per al que és en realitat el mateix estat.

La funció `state_key()` agrupa peces de la mateixa forma i ordena les seves posicions dins del grup. Dos estats que difereixen només en l'intercanvi de peces iguals es representen amb el mateix node, reduint la mida del graf fins a un 50% quan hi ha peces repetides.

---

### `solve.py`

Resol un puzzle i desa la seqüència de moviments en format `.sol.json`.

#### Com funciona

Fa un BFS directament sobre els estats del joc. Un sol `shortest_distance` des de l'inici calcula les distàncies a tots els nodes en O(V+E). El goal més proper es troba amb `np.argmin` en O(n_goals). Finalment, `shortest_path` reconstrueix el camí en O(V+E).

#### Ús

```bash
python src/solve.py puzzles/sample1.graphml
# genera: puzzles/sample1.sol.json

# Verificar la solució visualment
python src/movie.py puzzles/sample1.json puzzles/sample1.sol.json
python src/3D_view.py puzzles/sample1.graphml puzzles/sample1.sol.json
```

#### Dificultat: molt lent amb molts goals

La versió original feia un `gt.shortest_path` per a cada estat final. Amb puzzles de 88.965 goals, eren 88.965 BFS individuals:

```
Versió original: 88.965 BFS × O(V+E) → hores de càlcul
Versió actual:   1 BFS + np.argmin    → segons
```

**Solució:** un sol `gt.shortest_distance` calcula les distàncies a tots els nodes alhora. Trobar el goal més proper és llavors `np.argmin(dist_arr[goal_indices])`, accés vectoritzat en O(n_goals).

#### Dificultat: `ValueError: Moviment invàlid` a `movie.py`

`solve.py` retornava moviments amb distància > 1 quan una peça llisca múltiples caselles (ex: `[4, "S", 2]`). `movie.py` aplica els moviments pas a pas amb `apply_move`, que valida físicament cada pas i falla si la distància és > 1.

**Solució:** `find_moves()` descompon qualsevol moviment en múltiples moviments d'1 pas:

```python
# Peça llisca 2 caselles cap al sud → dos moviments d'1 pas
[4, "S", 2]  →  [(4, "S", 1), (4, "S", 1)]
```

---

### `eval.py`

Avalua l'interès d'un puzzle i li assigna una puntuació de **1 a 5 estrelles** (enter).

#### Com funciona

Calcula quatre mesures sobre el graf d'estats amb les mateixes fórmules que `eval.py`:

| Mesura | Descripció | Pes |
|--------|-----------|-----|
| M1 | Sigmoide de la longitud del camí mínim | 45% |
| M2 | Complexitat: `log₂(nodes) × densitat` | 25% |
| M3 | Coeficient de variació dels graus al camí | 20% |
| M4 | Escassetat exponencial dels goals | 10% |

La puntuació final es mostra com un enter 1-5 amb el valor decimal entre parèntesis.

#### Ús

```bash
# A partir del JSON (construeix el graf internament)
python src/eval.py puzzles/sample1.json

# A partir del graphml (molt més ràpid per a grafs grans)
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
  ★ Puntuació final     : 4 / 5  (3.99 abans d'arrodonir)
────────────────────────────────────────────────────
```

#### Dificultat: molt lent per a grafs de 500k+ nodes (>20 minuts)

La versió inicial usava `minimize_blockmodel_dl` (algorisme de Louvain) per a la mesura de comunitats. Aquest algorisme és O(V²) i per a 500k nodes trigava més de 20 minuts.

**Solució:** eliminar tots els BFS globals addicionals. Totes les mesures s'obtenen de:
- L'array de graus (`degree_property_map().a`, numpy, O(V))
- El camí de `solve()` (ja calculat, reutilitzat per M3)
- Estadístiques simples (n_nodes, n_edges, n_goals) via `.a.sum()`

Resultat: de >20 minuts a <1 minut per a qualsevol mida de graf.

#### Dificultat: tots els puzzles tenien la mateixa nota

Les mesures estaven normalitzades per constants fixes (ex: `REF_PATH_LEN = 50`) que no s'adaptaven a la mida real del graf. Un puzzle petit i un de gegant podien treure la mateixa M1.

**Solució:** normalitzar amb una sigmoide de referència fixa independent de la mida del graf. Un camí de 52 moviments sempre treu ~0.97 independentment de si el graf té 100 o 1M nodes. M2 usa `log₂(nodes) × densitat` que creix naturalment amb la complexitat:

| Graf | M2 |
|------|----|
| 16 nodes | 0.08 |
| 35k nodes | 0.44 |
| 1.1M nodes | 0.77 |

---

### `rate.py`

Avalua un puzzle i envia la puntuació al repositori compartit.

#### Token d'autenticació

El token es distribueix individualment per correu de la UPC. **Mai s'ha de posar al codi font** per evitar filtrar-lo al repositori git.

```bash
# Opció 1 (recomanada): fitxer .token a l'arrel del projecte
echo "el-teu-token-aqui" > .token

# Afegir al .gitignore per no pujar-lo accidentalment
echo ".token" >> .gitignore

# Opció 2: variable d'entorn (temporal, no es desa)
export KLOTSKI_TOKEN=el-teu-token-aqui
```

#### Ús

```bash
# Veure la puntuació sense enviar (recomanat per provar primer)
python src/rate.py f15847df --dry-run

# Valorar un puzzle concret
python src/rate.py f15847df

# Informe detallat de les mesures
python src/rate.py f15847df --verbose

# Valorar tots els puzzles descarregats
python src/rate.py --all

# Dry-run de tots
python src/rate.py --all --dry-run
```

#### Prioritat de fitxers

`rate.py` busca el fitxer del puzzle en aquest ordre, prioritzant el `.graphml` per ser molt més ràpid:

```
puzzles/<id[:8]>.graphml  ← prioritat màxima (graf ja construït)
puzzles/<id>.graphml
puzzles/<id[:8]>.json     ← construeix el graf internament
puzzles/<id>.json
```

---

### `generate.py`

Genera puzzles nous amb BFS invers intel·ligent.

#### Com funciona

En comptes de col·locar peces a l'atzar i esperar que el resultat sigui interessant (estratègia molt ineficient), usa una estratègia inversa:

1. Col·loca les peces en una posició final vàlida (el goal).
2. Fa un BFS invers des del goal explorant tots els estats accessibles.
3. L'estat **més llunyà** del goal és l'estat inicial: garanteix el camí màxim possible per a aquell taulell.
4. Avalua el puzzle amb les mateixes fórmules que `eval.py` (sense construir el graf de graph-tool).
5. Si supera el llindar, desa. Si no, descarta en mil·lisegons.

Si es prem `Ctrl+C`, desa automàticament el millor puzzle trobat fins al moment amb sufix `_rescat`.

#### Ús

```bash
# Buscar un puzzle de 4.3★ o més (per defecte)
python src/generate.py

# Buscar puzzles de 3.0★ o més
python src/generate.py --min-stars 3.0

# Buscar 3 puzzles de 4.0★ o més
python src/generate.py --min-stars 4.0 -n 3

# Canviar el directori de sortida
python src/generate.py --output my_puzzles/

# Aturar en qualsevol moment i desar el millor trobat
# (prémer Ctrl+C)
```

Sortida en temps real:
```
Cercant puzzles de 4.3★ – 5.0★
Ctrl+C → desa el millor trobat fins ara.

[  142]  48mov /   85234n  3.87★   millor: 4.21★
[  143]  61mov /  312847n  4.52★   millor: 4.52★
  [✓] 4.52★  61mov  312847n  →  puzzles/puzzle_4.52stars_61mov_3847.json
```

#### Dificultat: trigava hores sense trobar puzzles de 4-5★

La versió inicial construïa el graf complet amb `build_graph` per a cada intent. Cada intent trigava 10-60 segons, i amb milers d'intents necessaris per trobar un puzzle de 4-5★, el temps total era de hores.

**Solució:** BFS invers directe sobre l'espai d'estats, sense `graph_tool`. Cada intent ara triga mil·lisegons. A més, les estadístiques del BFS (n_nodes, n_edges, path_len, path_degrees) s'usen directament per avaluar el puzzle amb les mateixes fórmules que `eval.py`, sense necessitat de construir el graf.

#### Dificultat: `ValueError: Les coordenades no estan ordenades`

En desar el puzzle generat, `Puzzle.from_json` fallava perquè les coordenades de les peces als `POLYOMINOES` no estaven sempre en ordre lexicogràfic.

**Solució:** ordenar les coordenades de cada peça just abans de desar:

```python
pieces_normalized = [sorted(coords) for coords in pieces]
```

---
# Pujada de puzzles al repositori (`upload.py`)

## Idea general

`upload.py` puja puzzles nous al repositori compartit del professor. A diferència de `rate.py` (que envia valoracions de puzzles ja existents), `upload.py` contribueix puzzles nous generats per nosaltres.

## Token d'autenticació

Igual que `rate.py`, cal el token personal distribuït per correu de la UPC.

```bash
# Opció 1 (recomanada): fitxer .token
echo "el-teu-token-aqui" > .token
echo ".token" >> .gitignore   # evitar pujar-lo al git

# Opció 2: variable d'entorn
export KLOTSKI_TOKEN=el-teu-token-aqui
```

## Ús

```bash
# Pujar un puzzle concret
python src/upload.py puzzles/sample1.json

# Veure el JSON del puzzle abans de pujar
python src/upload.py puzzles/sample1.json --verbose

# Pujar tots els puzzles de la carpeta puzzles/
python src/upload.py --all
```

Exemple de sortida:
```
Pujant 'puzzle_4.52stars_61mov_a3f7c2b1.json'...
  Puzzle: 5×6, 7 peces  [a3f7c2b1]
  [✓] Pujat correctament! ID: f9e2c1d4...
```

## Flux recomanat

```bash
# 1. Generar puzzles de qualitat
python src/generate.py --min-stars 4.0 -n 5

# 2. Avaluar-los abans de pujar (opcional però recomanat)
python src/eval.py puzzles/puzzle_4.52stars_61mov_a3f7c2b1.json --verbose

# 3. Pujar-los
python src/upload.py --all
```

## Limit del repositori

Quan hi ha més de 200 puzzles al repositori, en pujar un de nou el servidor substitueix automàticament un dels puzzles amb valoració més baixa. Per tant, és important pujar puzzles de qualitat (4★ o més) per garantir que sobreviuen al repositori.

## Flux de treball complet

```bash
# 1. Activar l'entorn
pixi shell

# 2. Descarregar puzzles del repositori
python src/download.py

# 3. Construir el graf d'un puzzle
python src/graph.py puzzles/f15847df.json

# 4. Resoldre el puzzle
python src/solve.py puzzles/f15847df.graphml

# 5. Verificar la solució
python src/movie.py puzzles/f15847df.json puzzles/f15847df.sol.json
python src/3D_view.py puzzles/f15847df.graphml puzzles/f15847df.sol.json

# 6. Avaluar el puzzle
python src/eval.py puzzles/f15847df.graphml --verbose

# 7. Enviar la valoració
python src/rate.py f15847df

# 8. Generar puzzles nous
python src/generate.py --min-stars 4.0

# 9. Enviar valoracions de tots els puzzles
python src/rate.py --all
```