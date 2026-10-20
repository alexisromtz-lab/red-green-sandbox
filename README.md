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
python3 sandbox.py --banco             # banco must-fail: 26 filas que DEBEN abortar (9 fase + 17 rama)
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

Banco must-fail: **9/9 por causa** (no sólo por código de salida) **+ 17/17 por rama**
del validador de `--receta`:

| caso | fase | causa |
|---|---|---|
| `FALSO_REPRODUCTOR_PASA_EN_RED` | RED | `ABORTA_REPRODUCTOR_FALSO` |
| `SINTOMA_NO_OBSERVADO` | RED | `ABORTA_SINTOMA_NO_OBSERVADO` |
| `FIXTURE_BINARIO_FALTANTE` | RED | `ABORTA_FIXTURE_BINARIO_FALTANTE` |
| `PARCHE_QUE_NO_CASA` | PATCH | `ABORTA_PARCHE_NO_APLICA` |
| `EXAMEN_DENTRO_DEL_PARCHE` | PATCH | `ABORTA_EXAMEN_MOVIDO` |
| `ESCRITURA_NO_DECLARADA` | PATCH | `ABORTA_ESCRITURA_NO_DECLARADA` |
| `VERDE_QUE_NO_LLEGA` | GREEN | `ABORTA_VERDE_FALLIDO` |
| `REGRESION_ROTA_ANTES` | SETUP | `ABORTA_REGRESION_ROTA` |
| `REGRESION_ROTA_DESPUES` | GREEN | `ABORTA_REGRESION_ROTA` |

Las 17 filas `RANURA_*` ejercen el validador de `--receta` por subproceso: una fila por
rama de `_cargar_receta`, cada una exigiendo `causa` + prefijo de `detalle` + `RC=2`.

## Receta externa — `--receta PATH.json`

El motor **no guarda casos ajenos: los recibe**. Un issue externo no se codifica dentro
de `sandbox.py`; se envuelve en JSON y se pasa por la ranura. La receta externa se valida
contra **el mismo contrato** que las internas.

```bash
python3 sandbox.py --receta /ruta/a/receta.json          # veredicto legible
python3 sandbox.py --receta /ruta/a/receta.json --json   # veredicto máquina-legible
```

`--receta` corre **sólo** la receta externa: no arrastra el piloto ni el banco
(`hacer_piloto = args.piloto or (not args.banco and not args.receta)`, `sandbox.py:1338`).
Medido: la salida de una corrida con `--receta` tiene **0** líneas `[PILOTO]` y **1**
línea `[RECETA]`. Con `--json`, el reporte trae una clave `receta` con `caso`,
`fase_alcanzada` y `veredicto`.

### El contrato: seis claves, todas obligatorias

`CLAVES_RECETA` (`sandbox.py:101`) son las mismas seis que usan las recetas del
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
(`sandbox.py:97`) y sin ellas la receta se rechaza.

Cada elemento de `parche` exige las cuatro claves de `CLAVES_PARCHE`
(`sandbox.py:109`): `archivo`, `buscar` y `reemplazar` cadenas no vacías, y
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

### Fixture binario por referencia de blob

`fixture` es un mapa de **texto**: no sirve para los bytes de un PNG o un `.npy`. Para eso
hay una séptima clave, **opcional**: `fixture_binario`, con forma
`{ruta -> {blob, bytes}}`. El contenido **no viaja en el JSON**: viaja el OID de Git, y con
`--repo DIR` el motor lo materializa desde el object DB.

```bash
python3 sandbox.py --receta receta.json --repo /ruta/al/repo   # materializa los binarios
```

Reglas, leídas del motor (`sandbox.py:613` `_materializar_binarios`, `sandbox.py:834`
validación de la clave):

| regla | consecuencia |
|---|---|
| `fixture_binario` es un objeto `ruta -> {blob, bytes}` | otra forma ⇒ `ABORTA_RECETA_INVALIDA` |
| cada entrada trae un OID de blob | sin OID ⇒ `ABORTA_RECETA_INVALIDA` |
| la ruta no repite una del `fixture` de texto | repetida ⇒ `ABORTA_RECETA_INVALIDA` |
| el OID se verifica **antes** de escribir, y `bytes` si viene | no cuadra ⇒ el archivo **no** se escribe |
| tras escribir se relee y se compara | distinto ⇒ se borra y cuenta como faltante |

Fail-closed en las dos direcciones: sin `--repo` no se supone nada — se declara
`motivo=SIN_REPO_LOCAL` y los archivos quedan **faltantes**, no resueltos; y si el RED no
muestra el síntoma pero su salida **nombra** un binario declarado que no se materializó, la
causa es `ABORTA_FIXTURE_BINARIO_FALTANTE`, no un `ABORTA` genérico: el fixture estaba
incompleto y lo dice.

Las **seis claves obligatorias no cambian**: `fixture_binario` es la séptima y es opcional,
así que toda receta anterior corre igual. La clave entró con `VERSION` = `1.1.0`
(`sandbox.py` 971 líneas, blob `0da5130b`); el motor va en `1.2.0` (1 057 líneas, blob
`5858e76f`), **medido en el commit `ce128fb` a `2026-10-20T15:52:31Z`**.

Las dos cifras son **mediciones con fecha**, no una afirmación de presente: si `HEAD` es
posterior al commit citado, esta línea no miente por omisión — **pide re-medición**. Cuando
el motor avance de versión, la línea se **re-mide** en un commit nuevo con su hora; el
número viejo no se reescribe.

Re-medición `v1.3.0` (`HUELLA-README-VERSION-FECHADA-V130-20261020`): el motor va en
`1.3.0`, `sandbox.py` **1 475 líneas / 52 990 B / blob `3fed2ea4`**, medido en el commit
`4e4084f` a `2026-10-20T16:24:36Z`. Ese mismo binario mide `--banco` 9/9 causa · 19/19
rama · 17/17 ramas del validador, `--piloto` 3/3, ambos `RC=0`.

<!-- HUELLA-README-FIXTURE-BLOB-20261020 -->
<!-- HUELLA-README-VERSION-FECHADA-20261020 -->

### Códigos de salida de la ranura

| RC | significado |
|---|---|
| `0` | `CERTIFICADO_RED_GREEN`: RED falló con el síntoma, PATCH aplicó, GREEN pasó |
| `1` | el motor abortó: la receta corrió y un invariante la rechazó |
| `2` | `ABORTA_RECETA_INVALIDA`: la receta no se pudo cargar ni validar, nada corrió |

`RC 2` domina: se aplica sólo si el acumulado era menor (`if rc < 2`).

### Controles medidos

Seis corridas con `python3 3.14.7`: cinco el `2026-10-20T05:04Z` y una el
`2026-10-20T15:42Z` (la última es un caso del banco, no una receta externa):

| control | entrada | salida |
|---|---|---|
| A | receta con cinco claves (sin `sol_referencia`) | `RC 2` · `claves ausentes: ['sol_referencia']` |
| B1 | seis claves, `regresion.py` que falla **antes** del parche | `RC 1` · `FASE=SETUP` · `ABORTA_REGRESION_ROTA` |
| B2 | la misma, con la regresión corregida | `RC 0` · `RED rc=1 (AssertionError) PATCH +1/-1 GREEN rc=0 CERTIFICADO_RED_GREEN` |
| C | `fixture` sin `reproductor.py` | `RC 2` · `el fixture no trae el examen: ['reproductor.py']` |
| E | `sintoma` es `TypeError` en un caso que falla con `AssertionError` | `RC 1` · `FASE=RED` · `ABORTA_SINTOMA_NO_OBSERVADO` |
| F | `fixture_binario` declarado y corrido **sin** `--repo` | `RC 1` · `FASE=RED` · `ABORTA_FIXTURE_BINARIO_FALTANTE` · `motivo=SIN_REPO_LOCAL` |

B1 no es un fallo del motor: la **regresión se corre antes del parche**, en SETUP. Una
regresión que depende del bug que se está arreglando aborta la receta entera.

Teardown medido tras las seis corridas: `find /tmp -maxdepth 1 -name
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
una rama que nadie ha visto ejecutarse. Cobertura medida en `v1.3.0`: **9 de las 9
causas**, contadas por AST sobre el propio fuente (`_causas_del_motor`), no declaradas.

Pero la causa es una unidad **gruesa**. En la ranura externa las 19 filas comparten
`ABORTA_RECETA_INVALIDA`: con una sola fila la cobertura por causa quedaba completa y
una rama muerta pasaba invisible — el mismo defecto que un total correcto con la
clasificación rota. Por eso `v1.3.0` mide además la **rama**: `_ramas_del_validador`
lee por AST los 17 sitios `Aborta` de `_cargar_receta` y cada recibo se atribuye a la
plantilla de `detalle` más específica que lo explica. Medido: **17/17 ramas**, 19 filas,
18 mensajes distintos (dos filas comparten la rama `ocurrencias`).

El control que prueba que el invariante no es decorativo: borrar la fila
`RANURA_PARCHE_VACIO` deja `BANCO 9/9 · 18/18` y `COBERTURA 9/9` en verde, y el banco
sale `RC=1` igual por `RAMAS 16/17`. Sin la cobertura por rama, ese hueco era invisible.

`ABORTA_REGRESION_ROTA` se emite en **dos caras** y la causa no las distingue; el
recibo sí, por `fase_alcanzada`: `SETUP` = la regresión ya fallaba en el árbol base (el
control de no-regresión no vale) y `GREEN` = el parche rompió la regresión. Son dos
filas, no una.

### El banco de conducta (`tests/`)

`--banco` vive dentro del instrumento: lo ejecuta el mismo módulo que certifica. Eso
deja una pregunta abierta que sólo se responde desde fuera: **¿el motor se comporta
como dice cuando lo llaman otros?** `tests/test_sandbox.py` lo invoca por su entrada
pública (`sandbox.main`) y mide las dos direcciones:

| test | mide | espera |
|---|---|---|
| `test_piloto_certifica_las_tres_recetas` | `--piloto` | `RC 0` · `3/3 CERTIFICADO_RED_GREEN` |
| `test_receta_externa_valida_certifica` | receta válida por `--receta` | `RC 0` · `CERTIFICADO_RED_GREEN` |
| `test_parche_que_no_casa_aborta` | parche con `buscar` ausente | `RC != 0` · `ABORTA_PARCHE_NO_APLICA` |
| `test_reproductor_que_pasa_en_red_aborta` | reproductor que pasa en RED | `RC != 0` · `ABORTA_REPRODUCTOR_FALSO` |
| `test_receta_ilegible_aborta_con_rc_2` | JSON roto | `RC 2` · `ABORTA_RECETA_INVALIDA` |
| `test_banco_cobertura_completa` | `--banco` | `RC 0` · `9/9 causas` · `17/17 ramas` |
| `test_banco_no_es_tautologia` | falsificador del banco | torcer una `espera` ⇒ `RC != 0` |

Los tests **no reimplementan** el pipeline: si lo hicieran, medirían el test y no el
instrumento. Y el último no mide el motor, mide el **banco**: con una expectativa
torcida el banco tiene que caer, o no está midiendo nada.

**El control negativo del banco de conducta** (medido `2026-10-20T23:36Z`): se mutó una
copia del fuente —`if n != s["ocurrencias"]` ⇒ `if False` y `if pre["rc"] == 0` ⇒
`if False`— y la suite pasó de `7 passed` a **`4 failed, 3 passed`**. Una suite que
sigue verde con el instrumento roto no es un test, es un adorno.

CI: el aparato declarado en `.github/ci-apparatus` es compuesto, en una línea (el
runner lee **sólo la primera**):

```
python .github/verify_manifest.py && python -m pytest -q tests/
```

Manifiesto primero (¿parsea?), conducta después (¿se comporta?). Medido local:
`MANIFIESTO_SANO` + `7 passed` ⇒ `RC 0`.

## Cómo citar

Versión `1.3.0` depositada en Zenodo el `2026-10-20`: DOI de **versión**
`10.5281/zenodo.23507563`, DOI de **concepto** (todas las versiones)
`10.5281/zenodo.23507562`. Los metadatos de la cita viven en `CITATION.cff` (blob
`ae8fd1d6` en el momento de acuñar). Sin ese archivo Zenodo habría archivado el release
con campos vacíos: el tag se creó **después** de los metadatos, no antes.

```bibtex
@software{roman_martinez_red_green_sandbox_2026,
  author  = {Roman Martinez, Jose Alexis and {Platino Labs}},
  title   = {Red-Green Sandbox},
  year    = 2026,
  month   = oct,
  version = {1.3.0},
  doi     = {10.5281/zenodo.23507563},
  url     = {https://doi.org/10.5281/zenodo.23507563}
}
```

<!-- HUELLA-README-DOI-V130-20261020 -->

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
