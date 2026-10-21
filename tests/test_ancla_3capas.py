"""El ancla de tres capas de `red-green-sandbox`, y su control negativo.

HUELLA-RED-GREEN-ANCLA-20261020

Tres capas, todas derivadas del REPORTE (nunca del fuente):

  LEY         lo que el sistema decide: veredicto, fase, causa, sintomas, RC,
              y el sha16 del examen antes/despues (el examen no se mueve).
  FONTANERIA  el movimiento mecanico del parche: blobs pre/post, numstat,
              archivos declarados vs tocados, binarios.
  SUPERFICIE  el reporte completo, ya sin `seg` ni rutas de `tempfile`.

Y aparte, como CONTROL NEGATIVO: `sha256(sandbox.py)`. Ese número es un hash de
bytes: se mueve con un comentario y por eso no sirve de ancla. Se mide para
poder contrastarlo, no para usarlo.

El falsador que decide si esto es un ancla y no un hash disfrazado:
  ruido (`n_comment`, `n_print`)  -> las tres capas NO se mueven, el sha256 SI.
  senal (`s_examen`)              -> la LEY se mueve, la FONTANERIA no.
"""

import hashlib
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from test_canonical_surface import RAIZ, canonico, reporte, sha16

LEY_KEYS = (
    "caso",
    "veredicto",
    "fase_alcanzada",
    "causa",
    "detalle",
    "sintoma_esperado",
    "sintoma_pre_observado",
    "reproductor_sha16_pre",
    "reproductor_sha16_post",
    "reproductor_rc_pre",
    "reproductor_rc_post",
    "regresion_rc_pre",
    "regresion_rc_post",
    "teardown_ok",
)

FONTANERIA_KEYS = (
    "caso",
    "blobs",
    "numstat",
    "archivos_declarados",
    "archivos_tocados",
    "binarios",
    "repo_binarios",
)


def _proyectar(rep, claves):
    casos = sorted(rep["piloto"], key=lambda r: r["caso"])
    return [{k: r.get(k) for k in claves} for r in casos]


def capas(raiz_repo=None):
    """Las tres capas del ancla, como sha16."""
    rep = reporte(raiz_repo)
    return {
        "ley": sha16(_proyectar(rep, LEY_KEYS)),
        "fontaneria": sha16(_proyectar(rep, FONTANERIA_KEYS)),
        "superficie": sha16(rep),
    }


def baseline_bytes(raiz_repo=None):
    """Control negativo: sha256 del FUENTE. No es un ancla; es el contraste."""
    raiz_repo = os.path.abspath(raiz_repo or RAIZ)
    with open(os.path.join(raiz_repo, "sandbox.py"), "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


# --------------------------------------------------------------------------
# Mutaciones: ruido (no cambian la conducta) y senal (si la cambian)
# --------------------------------------------------------------------------


def n_comment(texto):
    return texto + "\n# Ruido de comentario: no cambia lo que el sistema hace.\n"


def n_print(texto):
    ancla = "def main(argv=None):\n"
    assert texto.count(ancla) == 1, "ancla de insercion no unica"
    return texto.replace(ancla, ancla + '    print("RUIDO_NOISE")\n', 1)


def s_examen(texto):
    clave = 'res["reproductor_sha16_post"] != res["reproductor_sha16_pre"]'
    assert texto.count(clave) == 1, "predicado del examen no unico"
    return texto.replace(
        clave, 'res["reproductor_sha16_post"] == res["reproductor_sha16_pre"]'
    )


def _copia_mutada(mutacion):
    """Copia el repo a un temporal con `sandbox.py` mutado. Devuelve la ruta."""
    destino = tempfile.mkdtemp(prefix="rg_ancla_")
    raiz = os.path.join(destino, "repo")
    shutil.copytree(
        RAIZ, raiz, ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc")
    )
    ruta = os.path.join(raiz, "sandbox.py")
    with open(ruta, encoding="utf-8") as fh:
        original = fh.read()
    with open(ruta, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(mutacion(original))
    return raiz


_BASE = {}


def _base():
    if not _BASE:
        _BASE.update(capas=capas(), bytes=baseline_bytes())
    return _BASE


def _medir(mutacion):
    raiz = _copia_mutada(mutacion)
    try:
        return {"capas": capas(raiz), "bytes": baseline_bytes(raiz)}
    finally:
        shutil.rmtree(os.path.dirname(raiz), ignore_errors=True)


# --------------------------------------------------------------------------
# Falsadores
# --------------------------------------------------------------------------


def test_las_tres_capas_son_distintas_entre_si():
    c = _base()["capas"]
    assert len({c["ley"], c["fontaneria"], c["superficie"]}) == 3, c


def test_tres_capas_son_deterministas():
    a = capas()
    b = capas()
    assert a == b, "dos corridas identicas dieron capas distintas: %s != %s" % (a, b)


def test_ruido_no_mueve_ninguna_capa_y_si_mueve_el_sha256():
    base = _base()
    for mutacion in (n_comment, n_print):
        m = _medir(mutacion)
        assert m["capas"] == base["capas"], (
            "%s movio el ancla conductual: %s -> %s"
            % (mutacion.__name__, base["capas"], m["capas"])
        )
        assert m["bytes"] != base["bytes"], (
            "%s no movio el sha256 del fuente: el experimento esta mal medido"
            % mutacion.__name__
        )


def test_senal_mueve_la_ley_y_no_la_fontaneria():
    base = _base()
    m = _medir(s_examen)
    assert m["capas"]["ley"] != base["capas"]["ley"], "la ley no capturo la senal"
    assert m["capas"]["fontaneria"] == base["capas"]["fontaneria"], (
        "la fontaneria se movio con una senal de LEY: %s -> %s"
        % (base["capas"]["fontaneria"], m["capas"]["fontaneria"])
    )
    assert m["capas"]["superficie"] != base["capas"]["superficie"], (
        "la superficie no capturo la senal"
    )


def test_baseline_de_bytes_no_es_ninguna_capa():
    base = _base()
    assert base["bytes"] not in base["capas"].values()


if __name__ == "__main__":
    c = _base()["capas"]
    print("LEY=%s" % c["ley"])
    print("FONTANERIA=%s" % c["fontaneria"])
    print("SUPERFICIE=%s" % c["superficie"])
    print("BASELINE_BYTES=%s" % _base()["bytes"])
    print("ANCLA: 3 capas · CONTROL NEGATIVO: sha256 del fuente")
