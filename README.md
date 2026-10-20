# red-green-sandbox

**Certifica que un parche resuelve un issue: demuestra la transición `RC != 0 → RC == 0`
sin mutar el examen.**

Es un laboratorio de reproducción en sandbox efímero. Recibe una receta (reproductor,
síntoma esperado y parche) y devuelve un veredicto que **no se puede fabricar**: si el
reproductor no falla antes del parche, el laboratorio aborta; si el parche toca el
reproductor o la regresión, aborta; si el problema no desaparece después, aborta.

```
SETUP -> RED -> PATCH -> GREEN -> TEARDOWN
```

## Por qué existe

Un PR que dice «arregla el issue» no dice nada. Un PR que dice «aquí está la falla
reproducida, aquí está el parche, y el examen quedó intacto» sí. Este laboratorio
produce esa segunda frase y la sostiene con hashes, no con adjetivos.

El invariante central — **`EXAMEN_MOVIDO = False`** — es lo que distingue un arreglo de
un test reescrito para pasar.

## Uso

```bash
python3 sandbox.py                     # piloto por defecto: 3 recetas sintéticas
python3 sandbox.py --banco             # banco must-fail: 9 casos que DEBEN abortar
python3 sandbox.py --json              # reporte máquina-legible
python3 sandbox.py --receta PATH.json  # receta externa, de fuera del repositorio
```

Salida del piloto (medida, `python3 3.14.7`):

```
[PILOTO] PARSING_SEPARADOR_EN_COMILLAS   RED rc=1 (AssertionError)  PATCH +11/-1  GREEN rc=0  CERTIFICADO_RED_GREEN
[PILOTO] FRONTERA_INCLUSIVA_OFF_BY_ONE   RED rc=1 (AssertionError)  PATCH +1/-1   GREEN rc=0  CERTIFICADO_RED_GREEN
[PILOTO] DENOMINADOR_CERO_DECLARADO      RED rc=1 (ZeroDivisionError) PATCH +2/-0 GREEN rc=0  CERTIFICADO_RED_GREEN
PILOTO: 3/3 CERTIFICADO_RED_GREEN
```

Banco must-fail: **5/5 por causa** (no sólo por código de salida):

| caso | fase | causa |
|---|---|---|
| `FALSO_REPRODUCTOR_PASA_EN_RED` | RED | `ABORTA_REPRODUCTOR_FALSO` |
| `SINTOMA_NO_OBSERVADO` | RED | `ABORTA_SINTOMA_NO_OBSERVADO` |
| `PARCHE_QUE_NO_CASA` | PATCH | `ABORTA_PARCHE_NO_APLICA` |
| `EXAMEN_DENTRO_DEL_PARCHE` | PATCH | `ABORTA_EXAMEN_MOVIDO` |
| `VERDE_QUE_NO_LLEGA` | GREEN | `ABORTA_VERDE_FALLIDO` |

## Receta externa — `--receta PATH.json`

El motor **no guarda casos ajenos: los recibe**. Un issue externo no se codifica dentro
de `sandbox.py`; se envuelve en JSON y se pasa por la ranura. La receta externa se valida
contra **el mismo contrato** que las internas.

```bash
python3 sandbox.py --receta /ruta/a/receta.json          # veredicto legible
python3 sandbox.py --receta /ruta/a/receta.json --json   # veredicto máquina-legible
```

`--receta` corre **sólo** la receta externa: no arrastra el piloto ni el banco
(`hacer_piloto = args.piloto or (not args.banco and not args.receta)`, `sandbox.py:986`).
Medido: la salida de una corrida con `--receta` tiene **0** líneas `[PILOTO]` y **1**
línea `[RECETA]`. Con `--json`, el reporte trae una clave `receta` con `caso`,
`fase_alcanzada` y `veredicto`.

### El contrato: seis claves, todas obligatorias

`CLAVES_RECETA` (`sandbox.py:80`) son las mismas seis que usan las recetas del
repositorio. Ninguna se suple con un default silencioso: si falta una, la receta **no
corre**.

| clave | tipo exigido | qué exige el motor |
|---|---|---|
| `nombre` | cadena no vacía | identificador del fix |
| `familia` | cadena no vacía | categoría del fallo |
| `sol_referencia` | cadena no vacía | familia del corpus que el fixture ejercita |
| `sintoma` | cadena no vacía | **subcadena** que debe aparecer en la salida del reproductor |
| `fixture` | objeto no vacío de cadenas | archivos relativos a escribir en el sandbox; **debe** traer `reproductor.py` y `regresion.py` |
| `parche` | lista no vacía | sustituciones exactas |

`sintoma` es una **cadena**, no un objeto: el motor busca esa subcadena en la salida
combinada del reproductor. `fixture` admite rutas con subdirectorio (`calc/texto.py`);
las claves del examen son `EXAMEN = ("reproductor.py", "regresion.py")`
(`sandbox.py:54`) y sin ellas la receta se rechaza.

Cada elemento de `parche` exige las cuatro claves de `CLAVES_PARCHE`
(`sandbox.py:66`): `archivo`, `buscar` y `reemplazar` cadenas no vacías, y
`ocurrencias` un **entero mayor o igual a 1** (un booleano se rechaza de forma
explícita). `buscar` tiene que casar **exactamente** `ocurrencias` veces.

```json
{
  "nombre": "CONTROL_README_RECETA_EXTERNA",
  "familia": "control/documentacion",
  "sol_referencia": "familia: control de la ranura externa",
  "sintoma": "AssertionError",
  "fixture": {
    "calc.py": "def doble(x):\n    return x + 2\n\n\ndef ident(x):\n    return x\n",
    "reproductor.py": "from calc import doble\nassert doble(3) == 6\n",
    "regresion.py": "from calc import ident\nassert ident(5) == 5\n"
  },
  "parche": [
    {
      "archivo": "calc.py",
      "buscar": "def doble(x):\n    return x + 2\n",
      "reemplazar": "def doble(x):\n    return x * 2\n",
      "ocurrencias": 1
    }
  ]
}
```

### Códigos de salida de la ranura

| RC | significado |
|---|---|
| `0` | `CERTIFICADO_RED_GREEN`: RED falló con el síntoma, PATCH aplicó, GREEN pasó |
| `1` | el motor abortó: la receta corrió y un invariante la rechazó |
| `2` | `ABORTA_RECETA_INVALIDA`: la receta no se pudo cargar ni validar, nada corrió |

`RC 2` domina: se aplica sólo si el acumulado era menor (`if rc < 2`).

### Controles medidos

Cinco corridas el `2026-10-20T05:04Z` con `python3 3.14.7`:

| control | entrada | salida |
|---|---|---|
| A | receta con cinco claves (sin `sol_referencia`) | `RC 2` · `claves ausentes: ['sol_referencia']` |
| B1 | seis claves, `regresion.py` que falla **antes** del parche | `RC 1` · `FASE=SETUP` · `ABORTA_REGRESION_ROTA` |
| B2 | la misma, con la regresión corregida | `RC 0` · `RED rc=1 (AssertionError) PATCH +1/-1 GREEN rc=0 CERTIFICADO_RED_GREEN` |
| C | `fixture` sin `reproductor.py` | `RC 2` · `el fixture no trae el examen: ['reproductor.py']` |
| E | `sintoma` es `TypeError` en un caso que falla con `AssertionError` | `RC 1` · `FASE=RED` · `ABORTA_SINTOMA_NO_OBSERVADO` |

B1 no es un fallo del motor: la **regresión se corre antes del parche**, en SETUP. Una
regresión que depende del bug que se está arreglando aborta la receta entera.

Teardown medido tras las cinco corridas: `find /tmp -maxdepth 1 -name
'sandbox_corpus_*'` devuelve **0** entradas.

## Reporte para pegar en un PR

```markdown
### Automated Verification via Red-Green Sandbox
- Phase 1 (RED): failed with `TypeError: NoneType has no attribute 'get'` (rc=1)
- Phase 2 (PATCH): atomic unified diff applied (+3 / -1), only declared blobs touched
- Phase 3 (GREEN): passed with rc=0, same reproductor byte-for-byte (sha16 pre == post)
- Invariant: test suite unchanged (EXAMEN_MOVIDO=False)
```

## Invariantes (todas medidas, ninguna leída)

- **RED**: `rc != 0` **y** el síntoma esperado presente en la salida. `rc == 0` ⇒
  `ABORTA_REPRODUCTOR_FALSO`; `rc != 0` sin síntoma ⇒ `ABORTA_SINTOMA_NO_OBSERVADO`.
- **PATCH**: cada sustitución casa exactamente `ocurrencias` veces; tocar
  `reproductor.py`/`regresion.py` ⇒ `ABORTA_EXAMEN_MOVIDO`; blobs tocados ≠ declarados
  ⇒ `ABORTA_ESCRITURA_NO_DECLARADA`.
- **GREEN**: mismo reproductor byte a byte y `rc == 0`. Si no ⇒ `ABORTA_VERDE_FALLIDO`.
- **TEARDOWN**: el sandbox (`/tmp/sandbox_corpus_*`) no sobrevive a la corrida.

### El banco mide que el motor sepa NO certificar

`--banco` exige `causa == espera` en cada fila. Una causa que ninguna fila dispara es
una rama que nadie ha visto ejecutarse. Cobertura declarada en `v1.2.0`: **8 de las 9
causas**. `ABORTA_RECETA_INVALIDA` queda fuera a propósito — vive en el validador de
`--receta` y se ejerce desde fuera (`RC=2`), no con filas del banco.

`ABORTA_REGRESION_ROTA` se emite en **dos caras** y la causa no las distingue; el
recibo sí, por `fase_alcanzada`: `SETUP` = la regresión ya fallaba en el árbol base (el
control de no-regresión no vale) y `GREEN` = el parche rompió la regresión. Son dos
filas, no una.

## Alcance

- El sandbox es un directorio temporal. El laboratorio **no** toca el árbol de trabajo.
- Los fixtures incluidos son **sintéticos**: nombran una familia de falla, no reclaman
  ser el objeto del issue que el usuario dice arreglar.
- Una receta de sustitución exacta exige que `buscar` cubra el bloque completo que
  `reemplazar` re-emite. Si el reemplazo trae la firma, el buscar trae la firma: es la
  lección de `CORR-01`, donde el propio invariante GREEN cazó un parche roto
  (`IndentationError`) que el autor no vio.

## Licencia

MIT. Ver `LICENSE`.

<!-- HUELLA-README-RECETA-EXTERNA-20261020 -->
