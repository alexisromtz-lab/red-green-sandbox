"""Superficie canonica de `sandbox.py`: el reporte sin lo volatil.

HUELLA-RED-GREEN-CANONICAL-20261020

Un ancla conductual no puede leer el fuente: si lo leyera, un comentario la
moveria. Por eso la superficie se calcula SOLO desde el reporte JSON, y lo que
varia entre dos corridas identicas —`seg`, `sandbox` (ruta de `tempfile`)— se
borra antes de serializar. Lo que queda es lo que el sistema dice que hizo.
"""

import hashlib
import json
import os
import subprocess
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Campos que cambian entre dos corridas con la misma entrada.
VOLATILES = ("seg", "sandbox")


def limpiar(obj):
    """Borra los campos volatiles en cualquier profundidad."""
    if isinstance(obj, dict):
        return {k: limpiar(v) for k, v in obj.items() if k not in VOLATILES}
    if isinstance(obj, list):
        return [limpiar(v) for v in obj]
    return obj


def reporte(raiz_repo=None):
    """Corre el piloto y devuelve el reporte ya limpio."""
    raiz_repo = os.path.abspath(raiz_repo or RAIZ)
    p = subprocess.run(
        [sys.executable, os.path.join(raiz_repo, "sandbox.py"), "--piloto", "--json"],
        cwd=raiz_repo,
        capture_output=True,
        text=True,
    )
    salida = p.stdout
    i = salida.index("{")
    j = salida.rindex("}")
    return limpiar(json.loads(salida[i : j + 1]))


def canonico(obj):
    """Serializacion determinista: claves ordenadas, sin espacios."""
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha16(obj):
    return hashlib.sha256(canonico(obj).encode("utf-8")).hexdigest()[:16]


def superficie(raiz_repo=None):
    return sha16(reporte(raiz_repo))


def test_superficie_no_lleva_campos_volatiles():
    limpio = canonico(reporte())
    for campo in VOLATILES:
        assert '"%s"' % campo not in limpio, "campo volatil sobrevivio: %s" % campo
    assert "/tmp/" not in limpio, "ruta de tempfile en la superficie"


def test_superficie_es_determinista():
    a = superficie()
    b = superficie()
    assert a == b, "dos corridas identicas dieron superficies distintas: %s != %s" % (
        a,
        b,
    )
