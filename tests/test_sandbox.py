# -*- coding: utf-8 -*-
"""Banco de conducta del laboratorio Red -> Green.

HUELLA-RED-GREEN-SANDBOX-BEHAVIOR-20261020

Estos tests NO reimplementan el laboratorio: lo INVOCAN por su entrada publica
(`sandbox.main`) y miden lo que el repositorio afirma en su README. Un test que
reimplementara el pipeline estaria midiendo el test, no el instrumento.

Lo que se mide, en las dos direcciones:

    POSITIVO  una receta que resuelve el sintoma se CERTIFICA (rc == 0)
    NEGATIVO  una receta que no resuelve el sintoma ABORTA (rc != 0)
    NEGATIVO  una receta ilegible ABORTA con rc == 2 (no corrio nada)

Y un control sobre el banco mismo (`test_banco_no_es_tautologia`): si se le
miente a una fila sobre su causa esperada, el banco debe PONERSE EN ROJO. Un
banco que devuelve verde con la expectativa torcida no mide: adorna.
"""

import contextlib
import copy
import io
import json
import os
import sys
import tempfile

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if RAIZ not in sys.path:
    sys.path.insert(0, RAIZ)

import sandbox  # noqa: E402  (la ruta del repo debe estar en sys.path antes)


def correr(argv):
    """Invoca la entrada publica y devuelve (rc, salida)."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = sandbox.main(argv)
    return rc, buf.getvalue()


def receta_json(destino, receta):
    with open(destino, "w", encoding="utf-8") as fh:
        json.dump(receta, fh, ensure_ascii=False)
    return destino


def receta_piloto():
    """Una receta del propio repo, copiada para poder mutarla."""
    return copy.deepcopy(sandbox.RECETAS_PILOTO[0])


# --------------------------------------------------------------------------
# POSITIVO: el instrumento certifica lo que si resuelve
# --------------------------------------------------------------------------


def test_piloto_certifica_las_tres_recetas():
    rc, salida = correr(["--piloto"])
    assert rc == 0, salida
    assert "PILOTO: 3/3 CERTIFICADO_RED_GREEN" in salida, salida
    assert "CERTIFICADO_RED_GREEN" in salida


def test_receta_externa_valida_certifica():
    with tempfile.TemporaryDirectory() as tmp:
        ruta = receta_json(os.path.join(tmp, "receta.json"), receta_piloto())
        rc, salida = correr(["--receta", ruta])
    assert rc == 0, salida
    assert "CERTIFICADO_RED_GREEN" in salida, salida


# --------------------------------------------------------------------------
# NEGATIVO: el instrumento se niega a certificar lo que no resuelve
# --------------------------------------------------------------------------


def test_parche_que_no_casa_aborta():
    receta = receta_piloto()
    receta["parche"][0]["buscar"] = "    return linea.split(',')\n"
    with tempfile.TemporaryDirectory() as tmp:
        ruta = receta_json(os.path.join(tmp, "receta.json"), receta)
        rc, salida = correr(["--receta", ruta])
    assert rc != 0, salida
    assert "ABORTA_PARCHE_NO_APLICA" in salida, salida


def test_reproductor_que_pasa_en_red_aborta():
    receta = receta_piloto()
    receta["fixture"]["reproductor.py"] = "print('NADA_QUE_REPRODUCIR')\n"
    with tempfile.TemporaryDirectory() as tmp:
        ruta = receta_json(os.path.join(tmp, "receta.json"), receta)
        rc, salida = correr(["--receta", ruta])
    assert rc != 0, salida
    assert "ABORTA_REPRODUCTOR_FALSO" in salida, salida


def test_receta_ilegible_aborta_con_rc_2():
    with tempfile.TemporaryDirectory() as tmp:
        ruta = os.path.join(tmp, "rota.json")
        with open(ruta, "w", encoding="utf-8") as fh:
            fh.write("{ esto no es json")
        rc, salida = correr(["--receta", ruta])
    assert rc == 2, salida
    assert "ABORTA_RECETA_INVALIDA" in salida, salida


# --------------------------------------------------------------------------
# El banco, y el control que prueba que el banco no es una tautologia
# --------------------------------------------------------------------------


def test_banco_cobertura_completa():
    rc, salida = correr(["--banco"])
    assert rc == 0, salida
    assert "COBERTURA: 9/9 causas con fila" in salida, salida
    assert "RAMAS: 17/17 ramas del validador ejercidas" in salida, salida


def test_banco_no_es_tautologia(monkeypatch):
    """Falsificador: con una expectativa torcida, el banco DEBE caer."""
    torcidas = copy.deepcopy(sandbox.RECETAS_BANCO)
    torcidas[0]["espera"] = "ABORTA_CAUSA_QUE_NADIE_EMITE"
    monkeypatch.setattr(sandbox, "RECETAS_BANCO", torcidas)
    rc, salida = correr(["--banco"])
    assert rc != 0, salida
    assert "BANCO: 8/9 causa correcta" in salida, salida
