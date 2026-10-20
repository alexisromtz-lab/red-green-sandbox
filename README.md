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
python3 sandbox.py            # piloto: 3 recetas sintéticas
python3 sandbox.py --banco    # banco must-fail: 5 casos que DEBEN abortar
python3 sandbox.py --json     # reporte máquina-legible
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
