# Estratègia d'avaluació de puzzles (`eval.py`)

## Idea general

Per valorar si un puzzle és *interessant*, construïm el seu graf d'estats
i en mesurem quatre propietats estructurals. La combinació ponderada
d'aquestes mesures, descomptant dues penalitzacions, dona una puntuació
final entre **0 i 5 estrelles**.

La intuïció central és que un bon puzzle ha de ser **difícil de resoldre**
(camí llarg i poc obvi), però alhora **tenir estructura** (no ser un laberint
caòtic sense lògica interna).

---

## Les quatre mesures

### M1 · Longitud del camí mínim `(pes 40%)`

La mesura més directa: quants moviments mínims cal per resoldre el puzzle.
Un puzzle de 3 moviments és trivial; un de 40 o més és genuïnament difícil.

```
m1 = min(path_len / 40, 1.0)
```

Rep el pes més alt perquè és la mesura més intuïtiva per a un jugador humà.

---

### M2 · Ratio camí / estats totals `(pes 25%)`

Un puzzle pot tenir un camí llarg però un graf enorme, de manera que la
solució és fàcil de trobar per exploració aleatòria. Aquesta mesura captura
si la solució és *difícil de descobrir* en relació al total d'estats possibles.

```
ratio = path_len / n_nodes
m2 = 1.0 - min(ratio, 1.0)   # invertit: ratio baix → puntuació alta
```

Un ratio baix significa que el camí correcte és una fracció petita de tots
els camins possibles, cosa que fa el puzzle més enganyós.

---

### M3 · Proporció de ponts `(pes 20%)`

Un **pont** és una aresta del graf que, si s'elimina, desconnecta el graf.
En termes de joc, un pont és un moviment *obligatori*: el jugador ha de
passar-hi sí o sí, sense alternativa.

```
m3 = min(n_bridges / (n_edges * 0.3), 1.0)
```

Alguns ponts fan el puzzle interessant perquè indiquen **fases** clares
(zones ben connectades unides per passatges estrets). Massa ponts, però,
fan el puzzle massa lineal i avorridor, cosa que la fórmula limita
naturalment en normalitzar per un llindar del 30% d'arestes.

---

### M4 · Dispersió de distàncies als estats finals `(pes 15%)`

Sovint hi ha múltiples estats finals (la peça objectiu pot estar en la
posició correcta amb les peces secundàries en moltes configuracions
diferents). Si tots els estats finals estan a la mateixa distància de
l'inici, qualsevol camí que arribi a un goal és igualment bo: el puzzle
és fàcil d'encertar per casualitat.

Si la distància varia molt entre els diferents goals, el jugador pot
anar cap a un goal molt llunyà sense saber-ho, cosa que fa el puzzle
més enganyós i interessant.

```
m4 = min((max_dist - min_dist) / 20.0, 1.0)
```

---

## Les dues penalitzacions

### P1 · Massa estats finals `(-0.20)`

S'aplica si hi ha més de 10 estats finals. Molts goals significa que
gairebé qualsevol configuració de les peces secundàries és vàlida,
cosa que redueix dràsticament la dificultat real del puzzle.

### P2 · Graf massa petit `(-0.30)`

S'aplica si el graf té menys de 30 nodes. Un graf tan petit indica un
puzzle trivial on el jugador pot explorar tots els estats en pocs segons.

---

## Fórmula final

```
score = W_PATH * m1 + W_RATIO * m2 + W_BRIDGE * m3 + W_DISP * m4
score = max(0.0, score - P1 - P2)
stars = score * 5.0
```

Els pesos (0.40 / 0.25 / 0.20 / 0.15) sumen 1.0, de manera que la
puntuació base sempre és a [0, 1] i la puntuació final sempre és a [0, 5].

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
────────────────────────────────────────────────
  Nodes del graf      : 342
  Arestes             : 891
  Estats finals       : 4
  Longitud camí mínim : 18 moviments
────────────────────────────────────────────────
  M1 longitud camí    : 0.450  (pes 40%)
  M2 ratio camí/nodes : 0.947  (pes 25%)
  M3 ponts            : 0.312  (pes 20%)
  M4 dispersió goals  : 0.200  (pes 15%)
────────────────────────────────────────────────
  Puntuació base      : 0.601
  ★ Puntuació final   : 3.01 / 5.00
────────────────────────────────────────────────
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