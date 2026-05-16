# EXPLICACIO GENERATE.py

## Distribució esbiaixada
### Usem (random.choices) amb pesos per donar més probabilitat a puzzles de 6-7 peces i menys en funció del nombre de peces, si és molt alt o molt baix, establint com a límit el 12.

## Generació dels puzzles inversa
### Per a assegurar-nos que els puzzles que es generen tenen solució el que fem és a partir d'una posició final vàlida, anar fent moviments vàlids fins a arribar a una posició la qual anomenarem inicial. D'aquesta forma sabrem que hi ha una solució vàlida pel puzzle, és a dir, un camí al graf.

## Canonicalització
### Les peces s'han d'ordenar per (forma, posició) per crear un `Puzzle` vàlid, tal com exigeix `puzzle.py`.

## Peça objectiu
### Sempre és la primera peça (índex (0)) i el seu objectiu és tornar a la posició on estava quan vam col·locar les peces inicialment.

## Filtre de qualitat
### amb `--min-stars` pots descartar puzzles per sota d'una puntuació mínima.

## Densitat mínima
### Les peces han d'ocupar almenys el 75% del tauler per a evitar puzzles amb massa caselles buides.

## Distància mínima de la peça objectiu
### La peça objetciu ha d'estar a almenys 3 caselles de distància Manhattan del goal en l'estat inicial.

## Camí mínim de 10 passos
### El puzzle es descarta si la solució òptima és de menys de (10) moviments.

## Filtre de qualitat
### amb `--min-stars` es poden descartar puzzles per sota d'una puntuació mínima calculada amb `eval.py`.