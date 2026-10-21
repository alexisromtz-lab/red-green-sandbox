"""Superficie canonica de `--banco`: lo que la regla de `--piloto` no alcanza.

HUELLA-RED-GREEN-ANCLA-BANCO-20261020

`test_canonical_surface.py` sella la superficie de `--piloto` retirando las dos
volatiles (`seg`, `sandbox`). Esa regla NO alcanza a `--banco`: una fila lleva
dentro de su `detalle` la ruta de un `TemporaryDirectory` (`sandbox.py:1373`) y
ningun filtro de claves retira una ruta que vive dentro de un valor. Medido: dos
corridas identicas de `--banco` divergen en esa linea, con las volatiles ya
retiradas.

La mascara declarada en el pre-registro (§10.4-§10.5) retira el sufijo aleatorio
y la raiz temporal. Es determinista: una regex fija sobre TODOS los valores de
texto, nunca sobre claves. No es «normalizar a ojo».

El falsador: sin mascara, `--banco` diverge; con mascara, las dos corridas
coinciden. Si un dia divergiera sin mascara, este archivo lo grita — y entonces
la superficie se volvio estable por otra razon, que hay que medir, no suponer.
"""

import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from test_canonical_surface import RAIZ, limpiar, sha16, superficie

MASCARA = re.compile(r"sandbox_(corpus|ranura)_[A-Za-z0-9_]+")
RAIZ_TMP = re.compile(r"/(?:var/folders/[^/]+/[^/]+/T|tmp)(?=/|$)")

# Sello canonico del pre-registro §10.5 (regla C' = volatiles fuera + M1 + M2).
PILOTO = "099339b8301c594e"
BANCO = "1c8764e2ce7d170a"

MODOS = ("--piloto", "--banco")


def enmascarar(obj):
    """M1 y M2 sobre valores de texto, a cualquier profundidad. Nunca en claves."""
    if isinstance(obj, dict):
        return {k: enmascarar(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [enmascarar(v) for v in obj]
    if isinstance(obj, str):
        return RAIZ_TMP.sub("<TMP_ROOT>", MASCARA.sub(r"sandbox_\1_<TMP>", obj))
    return obj


def reporte_crudo(modo, raiz_repo=None):
    """Corre un modo y devuelve el JSON ya sin volatiles, SIN mascara."""
    raiz_repo = os.path.abspath(raiz_repo or RAIZ)
    p = subprocess.run(
        [sys.executable, os.path.join(raiz_repo, "sandbox.py"), modo, "--json"],
        cwd=raiz_repo,
        capture_output=True,
        text=True,
    )
    salida = p.stdout
    i = salida.index("## JSON")
    j = salida.index("\nHORA_FIN", i)
    bloque = salida[i:j]
    return limpiar(json.loads(bloque[bloque.index("{"):bloque.rindex("}") + 1]))


_CORRIDAS = {}


def corrida(modo, indice):
    """Corrida n-esima de un modo, memoizada: dos corridas son dos corridas."""
    clave = (modo, indice)
    if clave not in _CORRIDAS:
        _CORRIDAS[clave] = reporte_crudo(modo)
    return _CORRIDAS[clave]


def canonica(modo, indice, mascara=True):
    obj = corrida(modo, indice)
    return sha16(enmascarar(obj) if mascara else obj)


def test_el_sello_canonico_coincide_con_el_preregistro():
    assert canonica("--piloto", 0) == PILOTO, "cambio la superficie de --piloto"
    assert canonica("--banco", 0) == BANCO, (
        "cambio la superficie de --banco: si es deliberado, re-ancla el pre-registro "
        "(§10.5); si no, la superficie dejo de ser estable"
    )


def test_los_dos_modos_son_deterministas_con_mascara():
    for modo in MODOS:
        a = canonica(modo, 0)
        b = canonica(modo, 1)
        assert a == b, "%s divergio con la mascara puesta: %s != %s" % (modo, a, b)


def test_la_mascara_muerde_y_no_es_vacua():
    """Si la mascara no cambia nada en --banco, no esta cubriendo nada."""
    crudo = canonica("--banco", 0, mascara=False)
    con_mascara = canonica("--banco", 0)
    assert crudo != con_mascara, "la mascara es vacua en --banco"
    texto = json.dumps(enmascarar(corrida("--banco", 0)), ensure_ascii=False)
    assert "<TMP>" in texto, "ninguna ruta aleatoria fue enmascarada"
    assert not MASCARA.search(texto), "sobrevivio un sufijo aleatorio: %s" % texto[:200]
    assert "<TMP_ROOT>" in texto, "la raiz temporal no fue enmascarada"


def test_control_negativo_sin_mascara_banco_diverge():
    """El falsador: la mascara no es decorativa, es lo unico que hace estable --banco."""
    a = canonica("--banco", 0, mascara=False)
    b = canonica("--banco", 1, mascara=False)
    assert a != b, (
        "--banco fue estable SIN mascara: la superficie cambio de causa y el "
        "pre-registro §10.3 quedo sin objeto. Re-medir, no borrar el test"
    )


def test_la_mascara_es_inerte_en_piloto():
    """No perturba el ancla ya sellada de --piloto: mismo numero que su superficie()."""
    assert canonica("--piloto", 0) == superficie(), (
        "la mascara movio la superficie de --piloto: muerde donde no debe"
    )


if __name__ == "__main__":
    for modo in MODOS:
        print("%-9s sello=%s  sin_mascara=%s" % (
            modo, canonica(modo, 0), canonica(modo, 0, mascara=False)))
    print("ANCLA: superficie --banco bajo mascara declarada (pre-registro §10.4-§10.5)")
