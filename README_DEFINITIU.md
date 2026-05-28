# Klotski — Pràctica 2 d'AP2

Projecte de resolució i generació de trencaclosques de peces lliscants (*sliding block puzzles*) basat en grafs d'estats. Inclou eines per descarregar puzzles d'un repositori compartit, construir i analitzar el seu graf, resoldre'ls automàticament, avaluar-ne la dificultat i generar-ne de nous.

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
   - [upload.py](#uploadpy)
4. [Flux de treball complet](#flux-de-treball-complet)

---

## Instal·lació i entorn

```bash
# Clonar el repositori
git clone https://github.com/llucvendrell/klotski.git
cd klotski

# Instal·lar dependències amb Pixi
pixi install

# Activar l'entorn (cal fer-ho abans d'executar qualsevol script)
pixi shell
```

Un cop actiu, el terminal mostra el prefix `(Klotski)`. Alternativament, es pot usar `pixi run python src/...` sense activar l'entorn.

> **Error freqüent:** Si apareix `ModuleNotFoundError: No module named 'graph_tool'` o `No module named 'pygame'`, significa que s'està usant el Python del sistema en comptes del de Pixi. Solució: activar `pixi shell` o usar `pixi run python`.

---

## Eines proporcionades

Aquests scripts vénen donats i no s'han modificat.

### `play.py` — Joc interactiu

```bash
python src/play.py puzzles/sample1.json
```

Obre una finestra gràfica per jugar al puzzle manualment arrossegant les peces amb el ratolí. Tecles: `R` reinicia, `Esc` surt.

### `image.py` — Imatge de l'estat inicial

```bash
python src/image.py puzzles/sample1.json
```

Genera un fitxer `.png` amb la representació visual de l'estat inicial del puzzle. El fitxer es desa al directori des d'on s'executa la comanda.

### `movie.py` — GIF animat de la solució

```bash
python src/movie.py puzzles/sample1.json puzzles/sample1.sol.json
```

Genera un GIF animat que mostra la seqüència de moviments de la solució. Requereix que `solve.py` hagi generat prèviament el fitxer `.sol.json`.

### `3D_view.py` — Visualitzador 3D del graf

```bash
# Sense solució
python src/3D_view.py puzzles/sample1.graphml

# Amb solució ressaltada en groc
python src/3D_view.py puzzles/sample1.graphml puzzles/sample1.sol.json
```

Obre el navegador amb una visualització 3D interactiva del graf d'estats. Els nodes grocs representen l'estat inicial i els verds els estats finals.

---

## Eines implementades

### `download.py`

Descarrega puzzles del repositori compartit (`https://klotski.pauek.dev`).

#### Com funciona

El repositori exposa dos endpoints:
- `GET /api/puzzles` → llista dels 100 puzzles amb millor valoració
- `GET /api/puzzles/<id>` → puzzle individual en format JSON

#### Ús

```bash
# Descarregar tots els puzzles del rànking
python src/download.py

# Descarregar un puzzle concret per ID complet
python src/download.py f15847df05c62d0d2d79e90182f6c020468abc41fefe3e3696902fb4ced9d2d0
```

Els puzzles es desen a `puzzles/<id[:8]>.json`. Usa únicament `urllib` de la biblioteca estàndard, valida cada puzzle amb `Puzzle.from_json()` abans de desar-lo i mostra el progrés amb `[✓]` o `[✗]`.

---

### `graph.py`

Construeix el graf d'estats d'un puzzle i el desa en format `.graphml`.

#### Com funciona

Cada node del graf representa una disposició de les peces. Dues disposicions estan connectades per una aresta si es pot passar d'una a l'altra amb un sol moviment vàlid. L'exploració es fa amb DFS iteratiu des de l'estat inicial.

El graf resultant té les següents propietats per node:
- `state`: posicions de totes les peces en format JSON
- `is_start`: `True` si és l'estat inicial
- `is_goal`: `True` si és un estat final
- `puzzle`: JSON del puzzle (metadada del graf)

#### Ús

```bash
python src/graph.py puzzles/sample1.json
# genera: puzzles/sample1.graphml

# Ruta de sortida personalitzada
python src/graph.py puzzles/sample1.json puzzles/output.graphml
```

#### Optimitzacions implementades

**Canonicalització de peces iguals (`state_key`):** si hi ha dues peces amb la mateixa forma, intercanviar-les dona el mateix estat visual però un `State` diferent. `state_key` agrupa peces de la mateixa forma i ordena les seves posicions dins del grup, de manera que dos estats visualment idèntics es representen amb el mateix node. Això pot reduir la mida del graf fins a un 50% quan hi ha peces repetides.

**Evitar arestes duplicades:** la guarda `if src_idx < dst_idx` garanteix que cada aresta s'afegeix exactament una vegada, evitant el doblement d'arestes que causava errors a `movie.py`.

---

### `solve.py`

Resol un puzzle i desa la seqüència de moviments en format `.sol.json`.

#### Com funciona

Fa un BFS directament sobre els estats del joc des de l'estat inicial. Per cada estat explorat comprova si és un estat final (`is_goal`). Quan el troba, reconstrueix el camí seguint els pares cap enrere i retorna la seqüència de moviments.

Usa `collections.deque` per al BFS, que garanteix operacions de cua en O(1) en comptes de O(n) amb llistes.

#### Ús

```bash
python src/solve.py puzzles/sample1.graphml
# genera: puzzles/sample1.sol.json

# Verificar la solució visualment
python src/movie.py puzzles/sample1.json puzzles/sample1.sol.json
python src/3D_view.py puzzles/sample1.graphml puzzles/sample1.sol.json
```

---

### `eval.py`

Avalua l'interès d'un puzzle i li assigna una puntuació de **1 a 5 estrelles** (enter).

#### Principis de disseny

- **Un camí llarg sempre puntua alt**, independentment de la mida del graf.
- **Un graf gran és un indicador positiu**: molts estats possibles indiquen un espai de joc ric i complex.
- **Zero BFS globals addicionals**: totes les mesures s'obtenen de l'array de graus (numpy) i del camí que calcula `solve()`. No es fa cap BFS addicional.

#### Les sis mesures

| Mesura | Descripció | Pes |
|--------|-----------|:---:|
| M1 | Longitud del camí mínim (sigmoide) | 35% |
| M2 | Complexitat: `log(nodes) × densitat` | 20% |
| M3 | Coeficient de variació dels graus al camí | 15% |
| M4 | Escassetat exponencial dels goals | 10% |
| M5 | Ratio de callejons sense sortida (dead-ends) | 10% |
| M6 | Punts de pas obligat (bottlenecks al camí) | 10% |

**M1** usa una funció sigmoidea amb referència fixa independent del graf: un camí de 15 moviments obté 0.50, un de 30 moviments obté 0.82 i un de 52 moviments obté ~0.97.

> **Aclaració**: Una funció sigmoidea és una funció matemàtica amb forma de (S) que dona valors entre (0) i (1). S'usa perquè la dificultat humana no és lineal: Passasr de 5 a 10 moviments és un salt enorme, mentre que passar de 50 a 55 és practicament insignificant. Aleshores, la funció sigmoidea el que fa és capturar aquesta idea de creixement ràpid a l'inici i més lent quan el camí és llarg 

**M2** combina mida i densitat: `log(n_nodes) × (n_edges / n_nodes) / 75`. Un graf de 35k nodes obté ~0.44 i un d'1.1M nodes obté ~0.77.

**M3** mesura si el camí passa per estats de connectivitat molt variada (interseccions vs. callejons). Un camí monòton és previsible; un camí variat és enganyós i interessant.

**M4** usa `exp(-5 × n_goals / n_nodes)`: pocs goals relatius al total significa que és difícil arribar a la solució per casualitat.

**M5** premia els puzzles amb molts callejons sense sortida (nodes de grau 1): indiquen que hi ha moltes rutes falses que enganen el jugador.

**M6** premia els puzzles amb entre un 10% i un 30% de punts de pas obligat al camí (nodes de grau 2): donen sensació d'estructura i fases sense fer el puzzle trivial.

#### Les tres penalitzacions

| Penalització | Condició | Màxim |
|-------------|----------|:-----:|
| P1 camí curt | path_len < 10 moviments | -0.25 |
| P2 graf petit | n_nodes < 100 | -0.20 |
| P3 massa goals | n_goals / n_nodes > 30% | -0.15 |

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
Avaluant 'sample1'...
────────────────────────────────────────────────────
  Nodes del graf        : 35976
  Arestes               : 78216
  Estats finals (goals) : 2412
  Longitud camí mínim   : 28 moviments
────────────────────────────────────────────────────
  M1 longitud camí      : 0.764  (pes 35%)
  M2 complexitat graf   : 0.441  (pes 20%)
  M3 varietat al camí   : 0.312  (pes 15%)
  M4 escassetat goals   : 0.713  (pes 10%)
  M5 ratio dead-ends    : 0.541  (pes 10%)
  M6 bottlenecks        : 0.623  (pes 10%)
────────────────────────────────────────────────────
  ★ Puntuació final     : 3 / 5  (2.87 abans d'arrodonir)
────────────────────────────────────────────────────
```

#### Dificultats trobades

**Tots els puzzles tenien la mateixa nota.** Les mesures estaven normalitzades per constants fixes que no s'adaptaven a la mida real del graf. Solució: usar la sigmoide (M1) i `log × densitat` (M2), que creixen de forma natural amb la complexitat sense requerir normalització externa.

**La modularitat de Louvain trigava >20 minuts.** Una versió anterior usava `minimize_blockmodel_dl` com a mesura de comunitats, que és O(V²). Per a 500k nodes el temps era inviable. Solució: eliminar tots els algorismes quadràtics i obtenir totes les mesures de l'array de graus numpy en O(V).

**El clustering de graf era sempre 0.0.** El coeficient de clustering mesura triangles (A-B, B-C, A-C). En grafs de puzzles lliscants no es formen triangles per construcció matemàtica. Solució: substituir pel coeficient de variació dels graus del camí (M3).

---

### `rate.py`

Avalua un puzzle amb `eval.py` i envia la puntuació al repositori compartit.

#### Com funciona

Busca el fitxer del puzzle per nom parcial a la carpeta `puzzles/`, prioritzant el `.graphml` si existeix. Avalua el puzzle i envia la puntuació via `POST /api/puzzles/<id>/votes`. Si s'usa `--all`, processa tots els puzzles de la carpeta mostrant el progrés en temps real. Si es prem `Ctrl+C`, informa de quants s'han enviat i quin ha estat l'últim amb èxit.

#### Ús

```bash
# Veure la puntuació sense enviar
python src/rate.py f15847df --dry-run

# Valorar un puzzle concret
python src/rate.py f15847df

# Informe detallat de les mesures
python src/rate.py f15847df --verbose

# Valorar tots els puzzles de la carpeta
python src/rate.py --all

# Dry-run de tots
python src/rate.py --all --dry-run
```

Exemple de sortida amb `--all`:
```
S'han trobat 25 puzzles únics a processar.

--- [Puzzle 1/25] ---
[+] Carregant graf precalculat 'f15847df.graphml'...
  [✓] Enviada correctament la valoració de 3 estrelles per al puzzle 'f15847df'.
  [📢 XIVATO] Estat actual: 1 enviats correctament. Últim amb èxit: f15847df

--- [Puzzle 2/25] ---
...
```

---

### `generate.py`

Genera puzzles nous amb BFS invers intel·ligent.

#### Com funciona

En comptes de col·locar peces a l'atzar i esperar que el resultat sigui interessant, usa una estratègia inversa:

1. Col·loca les peces en una posició final vàlida (el goal).
2. Fa un BFS invers des del goal explorant tots els estats accessibles.
3. L'estat **més llunyà** del goal és l'estat inicial: garanteix el camí màxim possible.
4. Avalua el puzzle amb les mateixes fórmules que `eval.py` (sense construir el graf de graph-tool).
5. Si supera el llindar de qualitat, el desa. Si no, descarta en mil·lisegons.

Si es prem `Ctrl+C`, desa automàticament el millor puzzle trobat fins al moment.

#### Paràmetres de generació

**Dimensions del taulell:** entre 5×5 i 6×6, amb més probabilitat per a taulells de 5×6 i 6×5.

**Nombre de peces:** distribució esbiaixada entre 6 i 8 peces, amb probabilitats 35%/40%/25% respectivament. Prioritzem 7 peces com a equilibri entre complexitat i temps d'avaluació.

**Densitat mínima del 75%:** les peces han d'ocupar almenys el 75% del taulell per evitar puzzles amb masses caselles buides.

**Camí mínim de 10 passos:** els puzzles que es resolen en menys de 10 moviments es descarten automàticament.

**Parets aleatòries:** cada puzzle pot tenir fins a un 10% de caselles com a parets, afegint varietat i forçant recorreguts no trivials.

#### Ús

```bash
# Buscar un puzzle de 4.3★ o més (per defecte)
python src/generate.py

# Buscar puzzles de 3.0★ o més
python src/generate.py --min-stars 3.0

# Buscar 3 puzzles de 4.0★ o més
python src/generate.py --min-stars 4.0 -n 3

# Aturar i desar el millor trobat (Ctrl+C)
```

Sortida en temps real:
```
Cercant 1 puzzle(s) de 4.3★ – 5.0★
Ctrl+C → desa els millors trobats fins ara.

[  142]  48mov /   85234n  3.87★   millor: 4.21★
[  143]  61mov /  312847n  4.52★   millor: 4.52★
  [✓] 4.52★  61mov  312847n  →  puzzles/puzzle_4.52stars_61mov_3f2a1b4c.json
```

#### Dificultats trobades

**Trigava hores sense trobar puzzles de qualitat.** La versió inicial construïa el graf complet amb `build_graph` per a cada intent, trigant 10-60 segons per intent. Solució: BFS invers directe sense graph-tool. Cada intent ara triga mil·lisegons, i les estadístiques del BFS s'usen directament per avaluar amb les mateixes fórmules que `eval.py`.

**Puzzles que es resolien en un sol moviment.** Sense filtres, el BFS invers podia generar puzzles on la peça objectiu quedava a un sol pas del goal. Solució: descartar puzzles amb menys de 10 moviments i aplicar un filtre de distància Manhattan mínima de 3 caselles.

**`ValueError: Les coordenades no estan ordenades`.** Les coordenades dels `POLYOMINOES` no estaven sempre en ordre lexicogràfic. Solució: ordenar les coordenades amb `sorted()` just abans de crear l'objecte `Piece`.

---

### `upload.py`

Puja puzzles nous al repositori compartit.

#### Ús

```bash
# Pujar un puzzle concret
python src/upload.py puzzles/puzzle_4.52stars_61mov_3f2a1b4c.json

# Veure el JSON del puzzle abans de pujar
python src/upload.py puzzles/sample1.json --verbose

# Pujar tots els puzzles de la carpeta puzzles/
python src/upload.py --all
```

El token es llegeix del fitxer `.token` a l'arrel del projecte o de la variable d'entorn `KLOTSKI_TOKEN`. **Mai s'ha de posar al codi font** per evitar filtrar-lo al repositori git.

```bash
echo "el-teu-token-aqui" > .token
echo ".token" >> .gitignore
```

> **Nota:** quan el repositori té més de 200 puzzles, en pujar-ne un de nou el servidor substitueix automàticament un dels puzzles amb valoració més baixa. És important pujar puzzles de qualitat (4★ o més).

---

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

# 5. Verificar la solució visualment
python src/movie.py puzzles/f15847df.json puzzles/f15847df.sol.json
python src/3D_view.py puzzles/f15847df.graphml puzzles/f15847df.sol.json

# 6. Avaluar el puzzle
python src/eval.py puzzles/f15847df.graphml --verbose

# 7. Enviar la valoració
python src/rate.py f15847df

# 8. Generar puzzles nous de qualitat
python src/generate.py --min-stars 4.0

# 9. Pujar els puzzles generats
python src/upload.py --all

# 10. Enviar valoracions de tots els puzzles
python src/rate.py --all
```