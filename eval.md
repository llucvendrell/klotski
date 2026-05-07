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