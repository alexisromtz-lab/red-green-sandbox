#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Laboratorio de reproduccion Red -> Green en sandbox efimero.

HUELLA-SANDBOX-RED-GREEN-20261019

Maquina de estados estricta, fail-closed:

    SETUP -> RED -> PATCH -> GREEN -> TEARDOWN

Invariantes (todas MEDIDAS, ninguna leida):

    RED    rc != 0  y  sintoma esperado presente en la salida
             rc == 0                    -> ABORTA_REPRODUCTOR_FALSO
             rc != 0 sin sintoma        -> ABORTA_SINTOMA_NO_OBSERVADO

    PATCH  cada sustitucion casa EXACTAMENTE `ocurrencias` veces
             cuentas distintas          -> ABORTA_PARCHE_NO_APLICA
             el parche toca el examen   -> ABORTA_EXAMEN_MOVIDO
             blobs fuera del parche     -> ABORTA_ESCRITURA_NO_DECLARADA

    GREEN  el mismo reproductor, byte a byte, con rc == 0
             rc != 0                    -> ABORTA_VERDE_FALLIDO
             reproductor movido         -> ABORTA_EXAMEN_MOVIDO
             regresion rota             -> ABORTA_REGRESION_ROTA

Alcance de escritura: SOLO el sandbox temporal (`/tmp/sandbox_corpus_*`).
Este modulo no importa `agent.py` ni `router_soluciones_v2.py` y no escribe
`INDICE_SOLUCIONES.json`: mide objetos ajenos sin tocarlos.

Ranura externa (HUELLA-SANDBOX-RECETA-EXTERNA-MRUN25-20261020): `--receta
PATH.json` ejecuta una receta de FUERA del repositorio, validada contra el mismo
contrato que las recetas internas. El motor no guarda casos ajenos: los recibe.
Un caso externo no se codifica dentro de este archivo; se envuelve en JSON.

Fixture binario (HUELLA-FIXTURE-BINARIO-SANDBOX-20261020): `fixture` es texto,
pero un fixture real trae bytes (un PNG, un .npy). Clave OPCIONAL
`fixture_binario` = {ruta -> {blob, bytes}}: el contenido NO viaja en el JSON,
viaja el OID de Git. Con `--repo DIR` se materializa con `git cat-file -p` en
modo `wb` verificando el OID ANTES de escribir; sin `--repo` no se inventa
nada: se declara `SIN_REPO_LOCAL` y la receta corre como hasta hoy. Si el RED
no muestra el sintoma y nombra un binario declarado que no se materializo, la
causa es `ABORTA_FIXTURE_BINARIO_FALTANTE`, no un ABORTA generico: el fixture
estaba incompleto y lo dice.

Banco de causas (HUELLA-BANCO-NEGATIVO-INSTRUMENTO-20261020): `--banco` no mide
que el motor certifique, mide que SEPA NO CERTIFICAR. Cada fila declara la causa
esperada y el banco exige `causa == espera`; una causa sin fila es una rama que
nadie ha visto dispararse. Cobertura declarada tras v1.2.0: 8 de las 9 causas.
`ABORTA_RECETA_INVALIDA` queda FUERA a proposito: vive en el validador de
`--receta`, que no pasa por `_correr_caso`, y se ejerce desde fuera, no con filas.

Dos caras, una causa: `ABORTA_REGRESION_ROTA` se emite antes y despues del
parche. `causa == espera` no las distingue; el recibo si, por `fase_alcanzada`
(SETUP = la regresion ya fallaba en base, el control no vale; GREEN = el parche
rompio la regresion). Se declaran como dos filas, no como una.

Nota de fidelidad: los fixtures son SINTETICOS. `sol_referencia` nombra la
familia del corpus que el laboratorio ejercita; NO se reclama que el fixture
sea el objeto de esa fila. La fila es la familia, el fixture es la instancia.
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from difflib import unified_diff

VERSION = "1.2.0"
PREFIJO_SANDBOX = "sandbox_corpus_"
TIMEOUT_S = 60
EXAMEN = ("reproductor.py", "regresion.py")

# Contrato de una receta externa: las MISMAS seis claves que las recetas del
# repositorio. Fail-closed: ninguna se suple con un default silencioso.
CLAVES_RECETA = (
    "nombre",
    "familia",
    "sol_referencia",
    "sintoma",
    "fixture",
    "parche",
)
CLAVES_PARCHE = ("archivo", "buscar", "reemplazar", "ocurrencias")

# --------------------------------------------------------------------------
# Fixtures (contenido exacto; sin dedent, para que el parche case literal)
# --------------------------------------------------------------------------

TEXTO_PRE = '''def limpio(s):
    return s.strip()
'''

REGRESION = '''from calc.texto import limpio

assert limpio("  x ") == "x"
print("REGRESION_OK")
'''

# --- R1: parsing, separador dentro de comillas ----------------------------

R1_PRE = '''def campos(linea):
    return [c.strip() for c in linea.split(",")]
'''

R1_TEST = '''from calc.csv_min import campos

caso = 'a,"b,c",d'
obtenido = campos(caso)
assert obtenido == ["a", "b,c", "d"], "campos(%r) = %r" % (caso, obtenido)
print("PARSING_OK", obtenido)
'''

R1_POST = '''def campos(linea):
    partes, actual, dentro = [], [], False
    for ch in linea:
        if ch == '"':
            dentro = not dentro
        elif ch == "," and not dentro:
            partes.append("".join(actual))
            actual = []
        else:
            actual.append(ch)
    partes.append("".join(actual))
    return [p.strip() for p in partes]
'''

# --- R2: frontera inclusiva ------------------------------------------------

R2_PRE = '''def rango(a, b):
    return list(range(a, b))
'''

R2_TEST = '''from calc.rango import rango

obtenido = rango(1, 3)
assert obtenido == [1, 2, 3], "rango(1, 3) = %r" % (obtenido,)
print("FRONTERA_OK", obtenido)
'''

R2_POST = '''def rango(a, b):
    return list(range(a, b + 1))
'''

# --- R3: denominador cero declarado, no dividido ---------------------------

R3_PRE = '''def tasa(n, d):
    return round(n / d, 4)
'''

R3_TEST = '''from calc.tasa import tasa

obtenido = tasa(3, 0)
assert obtenido is None, "tasa(3, 0) = %r" % (obtenido,)
print("DENOMINADOR_OK", obtenido)
'''

R3_POST = '''def tasa(n, d):
    if d == 0:
        return None
    return round(n / d, 4)
'''

# --------------------------------------------------------------------------
# Recetas
# --------------------------------------------------------------------------


def _fixture(modulo, contenido_pre, test):
    return {
        "calc/texto.py": TEXTO_PRE,
        "regresion.py": REGRESION,
        "reproductor.py": test,
        modulo: contenido_pre,
    }


# CORR-01 (2026-10-19T23:45Z, HUELLA-SANDBOX-RED-GREEN-CORR-01-20261019):
# En la primera corrida R1 y R2 declaraban `buscar` = SOLO el cuerpo, mientras
# `reemplazar` (R1_POST/R2_POST) trae la firma completa => el archivo quedaba con
# `def` duplicado, el reproductor moria con IndentationError y el laboratorio
# aborto con ABORTA_VERDE_FALLIDO. El invariante GREEN hizo su trabajo: no
# certifico un parche roto. La correccion es `buscar` = bloque PRE entero.

RECETAS_PILOTO = [
    {
        "nombre": "PARSING_SEPARADOR_EN_COMILLAS",
        "familia": "parsing/campos",
        "sol_referencia": "familia: frontera de campo — fixture sintetico",
        "sintoma": "AssertionError",
        "fixture": _fixture("calc/csv_min.py", R1_PRE, R1_TEST),
        "parche": [
            {
                "archivo": "calc/csv_min.py",
                "buscar": R1_PRE,
                "reemplazar": R1_POST,
                "ocurrencias": 1,
            }
        ],
    },
    {
        "nombre": "FRONTERA_INCLUSIVA_OFF_BY_ONE",
        "familia": "frontera/rango",
        "sol_referencia": "familia: limite declarado — fixture sintetico",
        "sintoma": "AssertionError",
        "fixture": _fixture("calc/rango.py", R2_PRE, R2_TEST),
        "parche": [
            {
                "archivo": "calc/rango.py",
                "buscar": R2_PRE,
                "reemplazar": R2_POST,
                "ocurrencias": 1,
            }
        ],
    },
    {
        "nombre": "DENOMINADOR_CERO_DECLARADO",
        "familia": "denominador/nulo",
        "sol_referencia": "familia: 0/0 declarado — fixture sintetico",
        "sintoma": "ZeroDivisionError",
        "fixture": _fixture("calc/tasa.py", R3_PRE, R3_TEST),
        "parche": [
            {
                "archivo": "calc/tasa.py",
                "buscar": "def tasa(n, d):\n    return round(n / d, 4)\n",
                "reemplazar": R3_POST,
                "ocurrencias": 1,
            }
        ],
    },
]

RECETAS_BANCO = [
    {
        "nombre": "FALSO_REPRODUCTOR_PASA_EN_RED",
        "familia": "banco/invariante-RED",
        "sol_referencia": "CONTROL NEGATIVO DEL LABORATORIO",
        "sintoma": "AssertionError",
        "espera": "ABORTA_REPRODUCTOR_FALSO",
        "fixture": _fixture("calc/csv_min.py", R1_PRE, "print('NADA_QUE_REPRODUCIR')\n"),
        "parche": [
            {
                "archivo": "calc/csv_min.py",
                "buscar": '    return [c.strip() for c in linea.split(",")]\n',
                "reemplazar": R1_POST,
                "ocurrencias": 1,
            }
        ],
    },
    {
        "nombre": "PARCHE_QUE_NO_CASA",
        "familia": "banco/invariante-PATCH",
        "sol_referencia": "CONTROL NEGATIVO DEL LABORATORIO",
        "sintoma": "AssertionError",
        "espera": "ABORTA_PARCHE_NO_APLICA",
        "fixture": _fixture("calc/csv_min.py", R1_PRE, R1_TEST),
        "parche": [
            {
                "archivo": "calc/csv_min.py",
                "buscar": "    return linea.split(',')\n",
                "reemplazar": R1_POST,
                "ocurrencias": 1,
            }
        ],
    },
    {
        "nombre": "VERDE_QUE_NO_LLEGA",
        "familia": "banco/invariante-GREEN",
        "sol_referencia": "CONTROL NEGATIVO DEL LABORATORIO",
        "sintoma": "AssertionError",
        "espera": "ABORTA_VERDE_FALLIDO",
        "fixture": _fixture("calc/csv_min.py", R1_PRE, R1_TEST),
        "parche": [
            {
                "archivo": "calc/csv_min.py",
                "buscar": "def campos(linea):\n",
                "reemplazar": "def campos(linea):  # parche cosmetico\n",
                "ocurrencias": 1,
            }
        ],
    },
    {
        "nombre": "SINTOMA_NO_OBSERVADO",
        "familia": "banco/invariante-RED-sintoma",
        "sol_referencia": "CONTROL NEGATIVO DEL LABORATORIO",
        "sintoma": "AssertionError",
        "espera": "ABORTA_SINTOMA_NO_OBSERVADO",
        "fixture": _fixture("calc/csv_min.py", R1_PRE, "raise SystemExit(7)\n"),
        "parche": [
            {
                "archivo": "calc/csv_min.py",
                "buscar": '    return [c.strip() for c in linea.split(",")]\n',
                "reemplazar": R1_POST,
                "ocurrencias": 1,
            }
        ],
    },
    {
        # Un fixture incompleto no se confunde con un sintoma ausente: el
        # reproductor nombra el binario declarado y el motor lo dice con causa
        # propia (HUELLA-FIXTURE-BINARIO-SANDBOX-20261020). Se declara 0*40 a
        # proposito: sin `--repo` no hay fuente, y el OID tampoco existe.
        "nombre": "FIXTURE_BINARIO_FALTANTE",
        "familia": "banco/invariante-fixture-binario",
        "sol_referencia": "CONTROL NEGATIVO DEL LABORATORIO",
        "sintoma": "InterpreterError",
        "espera": "ABORTA_FIXTURE_BINARIO_FALTANTE",
        "fixture": _fixture(
            "calc/csv_min.py",
            R1_PRE,
            "open('tests/data/falta.png', 'rb').read()\n",
        ),
        "fixture_binario": {"tests/data/falta.png": {"blob": "0" * 40, "bytes": 8}},
        "parche": [
            {
                "archivo": "calc/csv_min.py",
                "buscar": "def campos(linea):\n",
                "reemplazar": "def campos(linea):  # parche cosmetico\n",
                "ocurrencias": 1,
            }
        ],
    },
    {
        "nombre": "EXAMEN_DENTRO_DEL_PARCHE",
        "familia": "banco/invariante-examen-intocable",
        "sol_referencia": "CONTROL NEGATIVO DEL LABORATORIO",
        "sintoma": "AssertionError",
        "espera": "ABORTA_EXAMEN_MOVIDO",
        "fixture": _fixture("calc/csv_min.py", R1_PRE, R1_TEST),
        "parche": [
            {
                "archivo": "reproductor.py",
                "buscar": 'assert obtenido == ["a", "b,c", "d"]',
                "reemplazar": "assert True",
                "ocurrencias": 1,
            }
        ],
    },
    {
        # Cara ANTES de la misma causa: la regresion ya falla sobre el arbol
        # base, asi que el control de no-regresion no vale y el motor corta en
        # SETUP (regresion_rc_pre != 0, regresion_rc_post = None).
        "nombre": "REGRESION_ROTA_ANTES",
        "familia": "banco/invariante-REGRESION-antes",
        "sol_referencia": "CONTROL NEGATIVO DEL LABORATORIO",
        "sintoma": "AssertionError",
        "espera": "ABORTA_REGRESION_ROTA",
        "fixture": {
            **_fixture("calc/csv_min.py", R1_PRE, R1_TEST),
            "regresion.py": "raise SystemExit(9)\n",
        },
        "parche": [
            {
                "archivo": "calc/csv_min.py",
                "buscar": '    return [c.strip() for c in linea.split(",")]\n',
                "reemplazar": R1_POST,
                "ocurrencias": 1,
            }
        ],
    },
    {
        # Cara DESPUES: el parche arregla el reproductor y a la vez rompe la
        # regresion en OTRO archivo. El sintoma se observa, el examen no se
        # mueve, y lo que corta es la no-regresion (fase GREEN,
        # reproductor_rc_post = None).
        "nombre": "REGRESION_ROTA_DESPUES",
        "familia": "banco/invariante-REGRESION-despues",
        "sol_referencia": "CONTROL NEGATIVO DEL LABORATORIO",
        "sintoma": "AssertionError",
        "espera": "ABORTA_REGRESION_ROTA",
        "fixture": _fixture("calc/csv_min.py", R1_PRE, R1_TEST),
        "parche": [
            {
                "archivo": "calc/csv_min.py",
                "buscar": '    return [c.strip() for c in linea.split(",")]\n',
                "reemplazar": R1_POST,
                "ocurrencias": 1,
            },
            {
                "archivo": "calc/texto.py",
                "buscar": "    return s.strip()\n",
                "reemplazar": "    return s\n",
                "ocurrencias": 1,
            },
        ],
    },
    {
        # El mismo archivo declarado con dos grafias: `_aplicar` lo escribe de
        # verdad, pero el registro queda con dos claves mientras el snapshot
        # tiene una. El invariante no puede atribuir la escritura y corta en
        # PATCH en vez de certificar.
        "nombre": "ESCRITURA_NO_DECLARADA",
        "familia": "banco/invariante-escritura-declarada",
        "sol_referencia": "CONTROL NEGATIVO DEL LABORATORIO",
        "sintoma": "AssertionError",
        "espera": "ABORTA_ESCRITURA_NO_DECLARADA",
        "fixture": _fixture("calc/csv_min.py", R1_PRE, R1_TEST),
        "parche": [
            {
                "archivo": "./calc/csv_min.py",
                "buscar": "def campos(linea):\n",
                "reemplazar": "def campos(linea):  # alias\n",
                "ocurrencias": 1,
            },
            {
                "archivo": "calc/csv_min.py",
                "buscar": '    return [c.strip() for c in linea.split(",")]\n',
                "reemplazar": R1_POST,
                "ocurrencias": 1,
            },
        ],
    },
]


# --------------------------------------------------------------------------
# Utilidades
# --------------------------------------------------------------------------


class Aborta(Exception):
    """Corte fail-closed con causa declarada."""

    def __init__(self, causa, detalle):
        Exception.__init__(self, detalle)
        self.causa = causa
        self.detalle = detalle


def _blob_git(datos):
    return hashlib.sha1(b"blob %d\0" % len(datos) + datos).hexdigest()


def _sha256_hex(texto):
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def _escribir(raiz, archivos):
    for rel in sorted(archivos):
        p = os.path.join(raiz, rel)
        carpeta = os.path.dirname(p)
        if carpeta:
            os.makedirs(carpeta, exist_ok=True)
        with open(p, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(archivos[rel])


def _materializar_binarios(raiz, manifiesto, repo_dir):
    """`fixture_binario` -> archivos en BYTES, desde el object DB de Git.

    HUELLA-FIXTURE-BINARIO-SANDBOX-20261020
    Git es agnostico al tipo de contenido: un blob es bytes crudos. Por eso la
    escritura es `wb` y el contenido sale de `git cat-file -p`, no del worktree.
    Orden fail-closed: se verifica el OID contra el declarado (y `bytes` si
    viene) ANTES de escribir; un manifiesto que no cuadra no deja archivo.
    Sin `--repo` no se supone nada: se declara SIN_REPO_LOCAL y los archivos
    quedan como faltantes, no como resueltos.
    """
    items = []
    for rel in sorted(manifiesto or {}):
        v = manifiesto[rel]
        if isinstance(v, str):
            items.append((rel, v, None))
        else:
            items.append((rel, (v or {}).get("blob"), (v or {}).get("bytes")))
    inf = {"declarados": len(items), "materializados": 0, "faltantes": [],
           "motivo": None, "repo": repo_dir}
    if not items:
        return inf
    if not repo_dir or not os.path.isdir(os.path.join(repo_dir, ".git")):
        inf["motivo"] = "SIN_REPO_LOCAL"
        inf["faltantes"] = [rel for rel, _, _ in items]
        return inf
    for rel, blob, esperado in items:
        if not blob:
            inf["faltantes"].append(rel)
            continue
        try:
            datos = subprocess.check_output(
                ["git", "--no-optional-locks", "-C", repo_dir, "cat-file", "-p", blob]
            )
        except (subprocess.CalledProcessError, OSError):
            inf["faltantes"].append(rel)
            continue
        if _blob_git(datos) != blob:
            inf["faltantes"].append(rel)
            continue
        if esperado is not None and len(datos) != esperado:
            inf["faltantes"].append(rel)
            continue
        p = os.path.join(raiz, rel)
        carpeta = os.path.dirname(p)
        if carpeta:
            os.makedirs(carpeta, exist_ok=True)
        with open(p, "wb") as fh:
            fh.write(datos)
        with open(p, "rb") as fh:
            if fh.read() != datos:
                os.remove(p)
                inf["faltantes"].append(rel)
                continue
        inf["materializados"] += 1
    return inf


def _snapshot(raiz):
    tab = {}
    for base, dirs, files in os.walk(raiz):
        dirs[:] = sorted(d for d in dirs if d != "__pycache__")
        for nom in sorted(files):
            p = os.path.join(base, nom)
            rel = os.path.relpath(p, raiz).replace(os.sep, "/")
            with open(p, "rb") as fh:
                tab[rel] = _blob_git(fh.read())
    return tab


def _entorno(raiz):
    env = dict(os.environ)
    env["PYTHONPATH"] = raiz
    env["PYTHONHASHSEED"] = "0"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["TZ"] = "UTC"
    return env


def _correr(raiz, archivo):
    t0 = time.time()
    try:
        proc = subprocess.run(
            [sys.executable, archivo],
            cwd=raiz,
            env=_entorno(raiz),
            capture_output=True,
            text=True,
            timeout=TIMEOUT_S,
        )
        rc, out, err = proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired:
        rc, out, err = 124, "", "TIMEOUT_%ds" % TIMEOUT_S
    return {
        "rc": rc,
        "salida": out,
        "error": err,
        "seg": round(time.time() - t0, 3),
    }


def _numstat(pre, post):
    mas = menos = 0
    for linea in unified_diff(
        pre.splitlines(True), post.splitlines(True), lineterm="", n=0
    ):
        if linea.startswith("+++") or linea.startswith("---"):
            continue
        if linea.startswith("+"):
            mas += 1
        elif linea.startswith("-"):
            menos += 1
    return mas, menos


def _aplicar(raiz, sustituciones):
    """Aplica sustituciones exactas. Devuelve el registro por archivo."""
    por_archivo = {}
    for s in sustituciones:
        por_archivo.setdefault(s["archivo"], []).append(s)

    registro = {}
    for archivo in sorted(por_archivo):
        if archivo in EXAMEN:
            raise Aborta(
                "ABORTA_EXAMEN_MOVIDO",
                "el parche apunta a %s (el examen no se edita)" % archivo,
            )
        p = os.path.join(raiz, archivo)
        if not os.path.isfile(p):
            raise Aborta("ABORTA_PARCHE_NO_APLICA", "archivo ausente: %s" % archivo)

        with open(p, encoding="utf-8") as fh:
            pre = fh.read()
        post = pre
        for s in por_archivo[archivo]:
            n = post.count(s["buscar"])
            if n != s["ocurrencias"]:
                raise Aborta(
                    "ABORTA_PARCHE_NO_APLICA",
                    "%s: ocurrencias medidas=%d esperadas=%d"
                    % (archivo, n, s["ocurrencias"]),
                )
            post = post.replace(s["buscar"], s["reemplazar"])

        mas, menos = _numstat(pre, post)
        with open(p, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(post)
        registro[archivo] = {
            "blob_pre": _blob_git(pre.encode("utf-8")),
            "blob_post": _blob_git(post.encode("utf-8")),
            "mas": mas,
            "menos": menos,
            "bytes_pre": len(pre.encode("utf-8")),
            "bytes_post": len(post.encode("utf-8")),
        }
    return registro


def _hash_parche(sustituciones):
    canon = json.dumps(
        sustituciones, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return _sha256_hex(canon)


def _cargar_receta(ruta):
    """Carga y valida una receta externa. Fail-closed, sin defaults silenciosos.

    HUELLA-SANDBOX-RECETA-EXTERNA-MRUN25-20261020
    """
    if not os.path.isfile(ruta):
        raise Aborta(
            "ABORTA_RECETA_INVALIDA", "ruta ausente o no es un archivo: %s" % ruta
        )
    try:
        with open(ruta, encoding="utf-8") as fh:
            receta = json.load(fh)
    except ValueError as e:
        raise Aborta("ABORTA_RECETA_INVALIDA", "JSON ilegible: %s" % e)

    if not isinstance(receta, dict):
        raise Aborta("ABORTA_RECETA_INVALIDA", "la receta no es un objeto JSON")

    faltan = [k for k in CLAVES_RECETA if k not in receta]
    if faltan:
        raise Aborta(
            "ABORTA_RECETA_INVALIDA",
            "claves ausentes: %s (contrato: %s)" % (faltan, list(CLAVES_RECETA)),
        )

    for clave in ("nombre", "familia", "sol_referencia", "sintoma"):
        if not isinstance(receta[clave], str) or not receta[clave].strip():
            raise Aborta(
                "ABORTA_RECETA_INVALIDA", "%s debe ser una cadena no vacia" % clave
            )

    fixture = receta["fixture"]
    if not isinstance(fixture, dict) or not fixture:
        raise Aborta(
            "ABORTA_RECETA_INVALIDA", "fixture debe ser un objeto JSON no vacio"
        )
    for rel in sorted(fixture):
        if not isinstance(fixture[rel], str):
            raise Aborta(
                "ABORTA_RECETA_INVALIDA",
                "fixture[%r] debe ser una cadena de texto" % rel,
            )
    faltan_examen = [k for k in EXAMEN if k not in fixture]
    if faltan_examen:
        raise Aborta(
            "ABORTA_RECETA_INVALIDA", "el fixture no trae el examen: %s" % faltan_examen
        )

    # Clave OPCIONAL: el fixture binario viaja como referencia (ruta -> blob),
    # nunca como contenido. Se valida la forma y que no colisione con el texto.
    binario = receta.get("fixture_binario") or {}
    if binario:
        if not isinstance(binario, dict):
            raise Aborta(
                "ABORTA_RECETA_INVALIDA",
                "fixture_binario debe ser un objeto JSON ruta -> {blob, bytes}",
            )
        for rel in sorted(binario):
            v = binario[rel]
            oid = v if isinstance(v, str) else (v or {}).get("blob")
            if not isinstance(oid, str) or not oid.strip():
                raise Aborta(
                    "ABORTA_RECETA_INVALIDA",
                    "fixture_binario[%r] debe traer un blob OID" % rel,
                )
            if rel in fixture:
                raise Aborta(
                    "ABORTA_RECETA_INVALIDA",
                    "fixture_binario[%r] repite una ruta del fixture de texto" % rel,
                )
    receta["fixture_binario"] = binario

    parche = receta["parche"]
    if not isinstance(parche, list) or not parche:
        raise Aborta("ABORTA_RECETA_INVALIDA", "parche debe ser una lista no vacia")
    for i, s in enumerate(parche):
        if not isinstance(s, dict):
            raise Aborta("ABORTA_RECETA_INVALIDA", "parche[%d] no es un objeto" % i)
        faltan_s = [k for k in CLAVES_PARCHE if k not in s]
        if faltan_s:
            raise Aborta(
                "ABORTA_RECETA_INVALIDA",
                "parche[%d] sin claves: %s (contrato: %s)"
                % (i, faltan_s, list(CLAVES_PARCHE)),
            )
        for clave in ("archivo", "buscar", "reemplazar"):
            if not isinstance(s[clave], str) or not s[clave]:
                raise Aborta(
                    "ABORTA_RECETA_INVALIDA",
                    "parche[%d].%s debe ser una cadena no vacia" % (i, clave),
                )
        if isinstance(s["ocurrencias"], bool) or not isinstance(
            s["ocurrencias"], int
        ):
            raise Aborta(
                "ABORTA_RECETA_INVALIDA",
                "parche[%d].ocurrencias debe ser un entero" % i,
            )
        if s["ocurrencias"] < 1:
            raise Aborta(
                "ABORTA_RECETA_INVALIDA",
                "parche[%d].ocurrencias debe ser >= 1 (declarado: %d)"
                % (i, s["ocurrencias"]),
            )

    return receta


# --------------------------------------------------------------------------
# El runner de las cuatro fases
# --------------------------------------------------------------------------


def _correr_caso(receta, repo_dir=None):
    res = {
        "caso": receta["nombre"],
        "familia": receta["familia"],
        "sol_referencia": receta["sol_referencia"],
        "laboratorio": "v%s" % VERSION,
        "sandbox": None,
        "repo_binarios": repo_dir,
        "binarios": None,
        "fase_alcanzada": "SETUP",
        "hash_parche": _hash_parche(receta["parche"]),
        "hash_parche_sha16": _hash_parche(receta["parche"])[:16],
        "reproductor_rc_pre": None,
        "reproductor_rc_post": None,
        "sintoma_esperado": receta["sintoma"],
        "sintoma_pre_observado": False,
        "regresion_rc_pre": None,
        "regresion_rc_post": None,
        "reproductor_sha16_pre": None,
        "reproductor_sha16_post": None,
        "archivos_declarados": sorted({s["archivo"] for s in receta["parche"]}),
        "archivos_tocados": [],
        "numstat": {},
        "blobs": {},
        "teardown_ok": None,
        "veredicto": "ABORTA",
        "causa": None,
        "detalle": None,
        "seg": None,
    }
    t0 = time.time()
    ruta = None
    try:
        with tempfile.TemporaryDirectory(
            prefix=PREFIJO_SANDBOX, dir=("/tmp" if os.path.isdir("/tmp") else None)
        ) as raiz:
            ruta = raiz
            res["sandbox"] = raiz

            # ---------------- Fase 0: setup ----------------
            _escribir(raiz, receta["fixture"])
            # Los binarios van DESPUES del texto y ANTES del snapshot: la
            # escritura es `wb` y no puede pasar por el mapa de cadenas.
            bin_ = _materializar_binarios(raiz, receta.get("fixture_binario"), repo_dir)
            res["binarios"] = bin_
            snap_pre = _snapshot(raiz)
            res["fase_alcanzada"] = "SETUP"

            # ---------------- Fase 4a: regresion pre ----------------
            reg_pre = _correr(raiz, "regresion.py")
            res["regresion_rc_pre"] = reg_pre["rc"]
            if reg_pre["rc"] != 0:
                raise Aborta(
                    "ABORTA_REGRESION_ROTA",
                    "la regresion no pasa ANTES del parche: rc=%d" % reg_pre["rc"],
                )

            # ---------------- Fase 1: RED ----------------
            res["fase_alcanzada"] = "RED"
            pre = _correr(raiz, "reproductor.py")
            res["reproductor_rc_pre"] = pre["rc"]
            res["reproductor_sha16_pre"] = snap_pre["reproductor.py"][:16]
            combinado = (pre["salida"] or "") + (pre["error"] or "")
            res["sintoma_pre_observado"] = receta["sintoma"] in combinado
            if pre["rc"] == 0:
                raise Aborta(
                    "ABORTA_REPRODUCTOR_FALSO",
                    "el reproductor devuelve rc=0 sobre el estado defectuoso: "
                    "no hay bug que reparar o el test no captura el problema",
                )
            if not res["sintoma_pre_observado"]:
                # Un fixture incompleto no se confunde con un sintoma ausente:
                # si la salida nombra un binario DECLARADO que no se pudo
                # materializar, la causa lo dice con nombre y motivo.
                faltan_bin = [
                    rel
                    for rel in (bin_.get("faltantes") or [])
                    if os.path.basename(rel) in combinado
                ]
                if faltan_bin:
                    raise Aborta(
                        "ABORTA_FIXTURE_BINARIO_FALTANTE",
                        "rc=%d sin el sintoma %r; la salida nombra binarios "
                        "declarados sin materializar: %s (motivo=%s, repo=%s)"
                        % (
                            pre["rc"],
                            receta["sintoma"],
                            faltan_bin,
                            bin_.get("motivo"),
                            repo_dir,
                        ),
                    )
                raise Aborta(
                    "ABORTA_SINTOMA_NO_OBSERVADO",
                    "rc=%d pero el sintoma %r no aparece en la salida"
                    % (pre["rc"], receta["sintoma"]),
                )

            # ---------------- Fase 2: PATCH ----------------
            res["fase_alcanzada"] = "PATCH"
            registro = _aplicar(raiz, receta["parche"])
            res["blobs"] = registro
            res["numstat"] = {
                k: {"mas": v["mas"], "menos": v["menos"]} for k, v in registro.items()
            }

            snap_post = _snapshot(raiz)
            tocados = sorted(
                k for k in snap_post if k in snap_pre and snap_post[k] != snap_pre[k]
            )
            tocados += sorted(k for k in snap_post if k not in snap_pre)
            tocados += sorted(k for k in snap_pre if k not in snap_post)
            res["archivos_tocados"] = sorted(set(tocados))
            declarados = set(registro)
            if set(res["archivos_tocados"]) != declarados:
                raise Aborta(
                    "ABORTA_ESCRITURA_NO_DECLARADA",
                    "tocados=%s declarados=%s"
                    % (res["archivos_tocados"], sorted(declarados)),
                )

            # ---------------- Fase 3: GREEN ----------------
            res["fase_alcanzada"] = "GREEN"
            res["reproductor_sha16_post"] = snap_post["reproductor.py"][:16]
            if res["reproductor_sha16_post"] != res["reproductor_sha16_pre"]:
                raise Aborta(
                    "ABORTA_EXAMEN_MOVIDO",
                    "el reproductor cambio entre RED y GREEN: %s -> %s"
                    % (res["reproductor_sha16_pre"], res["reproductor_sha16_post"]),
                )

            reg_post = _correr(raiz, "regresion.py")
            res["regresion_rc_post"] = reg_post["rc"]
            if reg_post["rc"] != 0:
                raise Aborta(
                    "ABORTA_REGRESION_ROTA",
                    "la regresion se rompio con el parche: rc=%d" % reg_post["rc"],
                )

            post = _correr(raiz, "reproductor.py")
            res["reproductor_rc_post"] = post["rc"]
            if post["rc"] != 0:
                raise Aborta(
                    "ABORTA_VERDE_FALLIDO",
                    "el reproductor sigue rojo (rc=%d) despues del parche" % post["rc"],
                )

            res["veredicto"] = "CERTIFICADO_RED_GREEN"
    except Aborta as e:
        res["causa"] = e.causa
        res["detalle"] = e.detalle
    finally:
        res["seg"] = round(time.time() - t0, 3)
        if ruta is not None:
            res["teardown_ok"] = not os.path.exists(ruta)

    return res


# --------------------------------------------------------------------------
# Salida
# --------------------------------------------------------------------------


def _linea_piloto(r):
    if r["veredicto"] == "CERTIFICADO_RED_GREEN":
        det = r["numstat"][r["archivos_declarados"][0]]
        return "[PILOTO] %-34s RED rc=%s (%s)  PATCH +%d/-%d  GREEN rc=%s  %s" % (
            r["caso"],
            r["reproductor_rc_pre"],
            r["sintoma_esperado"],
            det["mas"],
            det["menos"],
            r["reproductor_rc_post"],
            r["veredicto"],
        )
    return "[PILOTO] %-34s FASE=%s  CAUSA=%s  detalle=%s" % (
        r["caso"],
        r["fase_alcanzada"],
        r["causa"],
        r["detalle"],
    )


def _linea_banco(r, espera):
    ok = "OK" if r["causa"] == espera else "ROJO_CAUSA_DISTINTA"
    return "[BANCO]  %-34s FASE=%-5s rc_pre=%-4s CAUSA=%-28s ESPERA=%-28s %s" % (
        r["caso"],
        r["fase_alcanzada"],
        r["reproductor_rc_pre"],
        str(r["causa"]),
        espera,
        ok,
    )


def _linea_receta(r, ruta):
    marca = ""
    b = r.get("binarios") or {}
    if b.get("declarados"):
        marca = "  bin=%d/%d%s" % (
            b.get("materializados", 0),
            b.get("declarados", 0),
            "" if not b.get("faltantes") else " faltan=%s" % ",".join(b["faltantes"]),
        )
    if r["veredicto"] == "CERTIFICADO_RED_GREEN":
        mas = sum(v["mas"] for v in r["numstat"].values())
        menos = sum(v["menos"] for v in r["numstat"].values())
        return (
            "[RECETA] %-34s RED rc=%s (%s)  PATCH +%d/-%d  "
            "GREEN rc=%s  %s%s  ruta=%s"
            % (
                r["caso"],
                r["reproductor_rc_pre"],
                r["sintoma_esperado"],
                mas,
                menos,
                r["reproductor_rc_post"],
                r["veredicto"],
                marca,
                ruta,
            )
        )
    return "[RECETA] %-34s FASE=%s  CAUSA=%s  detalle=%s%s  ruta=%s" % (
        r["caso"],
        r["fase_alcanzada"],
        r["causa"],
        r["detalle"],
        marca,
        ruta,
    )


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Laboratorio Red -> Green en sandbox efimero"
    )
    ap.add_argument("--piloto", action="store_true", help="corre las 3 recetas piloto")
    ap.add_argument("--banco", action="store_true", help="corre el banco must-fail")
    ap.add_argument("--json", action="store_true", help="emite el reporte JSON")
    ap.add_argument(
        "--receta",
        metavar="PATH",
        default=None,
        help="corre una receta externa en JSON (contrato: %s)"
        % ", ".join(CLAVES_RECETA),
    )
    ap.add_argument(
        "--repo",
        metavar="DIR",
        default=None,
        help="arbol git de donde materializar `fixture_binario` (git cat-file -p, modo wb)",
    )
    args = ap.parse_args(argv)

    hacer_piloto = args.piloto or (not args.banco and not args.receta)
    hacer_banco = args.banco

    print("HORA_INI=%s VERSION=%s" % (time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), VERSION))
    print("PY=%s" % sys.version.split()[0])

    salida = {}
    rc = 0

    if hacer_piloto:
        resultados = [_correr_caso(r, args.repo) for r in RECETAS_PILOTO]
        certificados = sum(1 for r in resultados if r["veredicto"] == "CERTIFICADO_RED_GREEN")
        for r in resultados:
            print(_linea_piloto(r))
        print(
            "PILOTO: %d/%d CERTIFICADO_RED_GREEN"
            % (certificados, len(resultados))
        )
        salida["piloto"] = resultados
        if certificados != len(resultados):
            rc = 1

    if hacer_banco:
        filas = []
        correctas = 0
        for receta in RECETAS_BANCO:
            r = _correr_caso(receta, args.repo)
            filas.append(r)
            if r["causa"] == receta["espera"]:
                correctas += 1
            print(_linea_banco(r, receta["espera"]))
        print("BANCO: %d/%d causa correcta" % (correctas, len(filas)))
        salida["banco"] = filas
        if correctas != len(filas):
            rc = 1

    if args.receta:
        # Ranura externa: el motor recibe la receta, no la guarda.
        receta_externa = None
        try:
            receta_externa = _cargar_receta(args.receta)
        except Aborta as e:
            print(
                "[RECETA] %-34s CAUSA=%s  detalle=%s  ruta=%s"
                % ("RECETA_EXTERNA", e.causa, e.detalle, args.receta)
            )
            salida["receta"] = {
                "ruta": args.receta,
                "veredicto": "ABORTA",
                "causa": e.causa,
                "detalle": e.detalle,
            }
            # RC=2 domina: la receta no se pudo ejecutar (nada corrio).
            if rc < 2:
                rc = 2
        if receta_externa is not None:
            r = _correr_caso(receta_externa, args.repo)
            print(_linea_receta(r, args.receta))
            salida["receta"] = r
            if r["veredicto"] != "CERTIFICADO_RED_GREEN" and rc == 0:
                rc = 1

    if args.json:
        print("## JSON")
        print(json.dumps(salida, ensure_ascii=False, indent=2, sort_keys=True))

    print("HORA_FIN=%s RC=%d" % (time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), rc))
    return rc


if __name__ == "__main__":
    sys.exit(main())
