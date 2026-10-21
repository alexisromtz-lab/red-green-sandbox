#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Testigo del claims.json de red-green-sandbox: el contrato deja de ser prosa.

HUELLA-RG-CLAIMS-WITNESS-20261020

Acto `HUELLA-RG-SANDBOX-CLAIMS-WITNESS-README-20261020` (T3 README + T2 testigo +
T1 claims). El censo congelado en
`platino-labs/sim/PREREGISTRO_CLAIMS_RG_PC_20261020.md` §9.2 midio 12 figuras
distintas en el README; 10 resultaron mecanizables y aqui se verifican una a una.

Que exige este testigo por claim (los mismos cuatro eslabones que plasma-ade):

  1. PORTADOR — el `dato` existe como archivo. Un dato inexistente es
     DATO_SIN_PORTADOR.
  2. DERIVA — `deriva` nombra `parser:<ruta>::<funcion>` y esa ruta esta en
     `CARGA`, el censo de portadores preexistentes. La funcion tiene que existir
     (si no, PARSER_AUSENTE) y su codigo tiene que nombrar los lectores de su
     portador (si no, DERIVACION_CIEGA).
  3. CRUCE — la raiz de `ruta` (`banco`, `piloto`, `ramas`, `receta`) nombra un
     crudo distinto, y cada crudo tiene UN portador. Un claim cuyo `deriva` lee
     un portador y cuya `ruta` resuelve en otro es DERIVACION_CRUZADA: el numero
     vendria de un sitio y la prueba de otro.
  4. VALOR + PROSA — `ruta` resuelve dentro de su crudo y el valor vigente
     aparece en `afirma` (si no, VALOR_NO_ES_EL_CRUDO); y `afirma` aparece en el
     README (si no, README_DESALINEADO).

Divergencia declarada (D13): `deriva` NO puede apuntar a este archivo. Un
claims.json cuyo `deriva` nombrase a su propio testigo se verificaria a si
mismo, que es el defecto que este acto persigue. Los tres portadores son
anteriores al acto:

  * `tests/test_ancla_banco.py::reporte_crudo` — corre `sandbox.py <modo> --json`
    y parsea el recibo.
  * `sandbox.py::_ramas_del_validador` — cuenta por AST las ramas `Aborta` de
    `_cargar_receta`.
  * `tests/test_sandbox.py::correr` — invoca `sandbox.main` y devuelve la salida
    cruda, de donde se cuentan las lineas `[PILOTO]` y `[RECETA]`.

Normalizacion declarada de la prosa: se quitan `**` y backticks y se colapsan
los espacios antes de buscar `afirma`. No relaja nada — el README escribe
`**0** lineas `[PILOTO]`` y `**1**\\nlinea `[RECETA]``, donde el literal no
sobrevive al reflow de Markdown. `test_la_normalizacion_no_es_vacua` exige que
al menos un claim la necesite.

El falsador: `test_el_testigo_de_claims_sabe_fallar` muta el contrato en once
formas y exige que cada una sea cazada por su causa exacta. Un testigo que solo
aprueba el caso sano no discrimina.
"""

import importlib.util
import inspect
import json
import os
import re
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
CLAIMS = RAIZ / ".github" / "claims.json"
TESTS = RAIZ / "tests"

for _ruta in (str(TESTS), str(RAIZ)):
    if _ruta not in sys.path:
        sys.path.insert(0, _ruta)

# El propio testigo: ningun `deriva` puede nombrarlo (D13).
TESTIGO_REL = "tests/test_claims_witness.py"

# Portadores preexistentes y los lectores que su fuente tiene que nombrar.
CARGA = {
    "tests/test_ancla_banco.py": ("sandbox.py", "--json", "json.loads"),
    "sandbox.py": ("ast.parse", "Aborta", "__file__"),
    "tests/test_sandbox.py": ("sandbox.main", "redirect_stdout"),
}

# Cada raiz de `ruta` nombra un crudo, y cada crudo tiene UN portador.
PORTADOR_DE_RAIZ = {
    "banco": "tests/test_ancla_banco.py",
    "piloto": "tests/test_ancla_banco.py",
    "ramas": "sandbox.py",
    "receta": "tests/test_sandbox.py",
}

DERIVA = re.compile(r"^parser:(?P<ruta>[^:]+)::(?P<funcion>[A-Za-z_][A-Za-z0-9_]*)$")
SEGMENTO = re.compile(
    r"^(?P<clave>[A-Za-z_][A-Za-z0-9_]*)"
    r"(?:\[(?P<campo>[A-Za-z_][A-Za-z0-9_]*)=(?P<valor>[^\]]+)\])?"
    r"(?:#(?P<op>distintos))?$"
)
CAMPOS_CLAIM = ("id", "afirma", "dato", "ruta", "deriva", "polaridad", "prosa")
POLARIDADES = ("exacto",)

_MODULOS = {}
_CRUDOS = {}


def modulo(rel):
    """Importa un portador por ruta relativa, sin recargar lo que pytest ya importo."""
    nombre = Path(rel).stem
    mod = sys.modules.get(nombre)
    if mod is not None:
        return mod
    if rel not in _MODULOS:
        ruta = RAIZ / rel
        if not ruta.is_file():
            raise FileNotFoundError("PARSER_AUSENTE: no existe %s" % rel)
        spec = importlib.util.spec_from_file_location(nombre, ruta)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[nombre] = mod
        spec.loader.exec_module(mod)
        _MODULOS[rel] = mod
    return _MODULOS[rel]


def _recibo(modo):
    clave = ("recibo", modo)
    if clave not in _CRUDOS:
        _CRUDOS[clave] = modulo("tests/test_ancla_banco.py").reporte_crudo(modo)
    return _CRUDOS[clave]


def _crudo_ramas():
    if "ramas" not in _CRUDOS:
        _CRUDOS["ramas"] = {"ramas": modulo("sandbox.py")._ramas_del_validador()}
    return _CRUDOS["ramas"]


def _crudo_receta():
    if "receta" not in _CRUDOS:
        mod = modulo("tests/test_sandbox.py")
        with tempfile.TemporaryDirectory() as tmp:
            ruta = mod.receta_json(os.path.join(tmp, "receta.json"), mod.receta_piloto())
            rc, salida = mod.correr(["--receta", ruta])
        lineas = salida.splitlines()
        _CRUDOS["receta"] = {
            "rc": rc,
            "lineas_piloto": sum(1 for l in lineas if l.startswith("[PILOTO]")),
            "lineas_receta": sum(1 for l in lineas if l.startswith("[RECETA]")),
        }
    return _CRUDOS["receta"]


CRUDOS = {
    "banco": lambda: _recibo("--banco"),
    "piloto": lambda: _recibo("--piloto"),
    "ramas": _crudo_ramas,
    "receta": _crudo_receta,
}


def crudo_de(ruta):
    """La primera clave de `ruta` nombra el portador; el resto resuelve dentro."""
    raiz, _, resto = ruta.partition(".")
    if raiz not in CRUDOS:
        raise ValueError(
            "RUTA_INVALIDA: %r no nombra un crudo (%s)"
            % (ruta, ",".join(sorted(CRUDOS)))
        )
    if not resto:
        raise ValueError("RUTA_INVALIDA: %r no resuelve nada" % ruta)
    return CRUDOS[raiz](), resto


def _literal(txt):
    t = txt.strip()
    if t.lower() == "true":
        return True
    if t.lower() == "false":
        return False
    for cast in (int, float):
        try:
            return cast(t)
        except ValueError:
            pass
    return t.strip("'\"")


def resolver(obj, ruta):
    """Resuelve 'a.b[campo=false].c#distintos'; una lista al final vale su longitud."""
    actual = obj
    for segmento in ruta.split("."):
        m = SEGMENTO.match(segmento)
        if not m:
            raise ValueError("RUTA_INVALIDA: %r no es un segmento valido" % ruta)
        clave = m.group("clave")
        if isinstance(actual, dict):
            if clave not in actual:
                raise ValueError("RUTA_AUSENTE: %r no existe en el crudo" % ruta)
            actual = actual[clave]
        elif isinstance(actual, list) and actual and all(isinstance(i, dict) for i in actual):
            if not any(clave in i for i in actual):
                raise ValueError("RUTA_AUSENTE: %r no proyecta %r sobre la lista" % (ruta, clave))
            actual = [i.get(clave) for i in actual]
        else:
            raise ValueError("RUTA_AUSENTE: %r no desciende sobre %s" % (ruta, type(actual).__name__))
        campo = m.group("campo")
        if campo:
            if not isinstance(actual, list):
                raise ValueError("RUTA_INVALIDA: %r filtra sobre algo que no es lista" % ruta)
            esperado = _literal(m.group("valor"))
            actual = [i for i in actual if isinstance(i, dict) and i.get(campo) == esperado]
        if m.group("op") == "distintos":
            if not isinstance(actual, list):
                # HUELLA-GRAMATICA-DUAL-ALINEA-MENSAJE-20261020: la copia informativa
                # gana — el mensaje nombra la ruta que falló, igual que el global.
                raise ValueError(
                    "RUTA_INVALIDA: %r #distintos sobre algo que no es lista" % ruta
                )
            vistos, unicos = set(), []
            for item in actual:
                k = json.dumps(item, sort_keys=True, ensure_ascii=False)
                if k not in vistos:
                    vistos.add(k)
                    unicos.append(item)
            actual = unicos
    return len(actual) if isinstance(actual, list) else actual


def porta_valor(valor, afirma):
    """El valor vigente tiene que estar en la afirmacion, como token entero."""
    return re.search(r"(?<!\d)%s(?!\d)" % re.escape(str(valor)), afirma) is not None


def prosa(txt):
    """Markdown a prosa comparable: sin enfasis, sin backticks, espacios colapsados."""
    t = txt.replace("\u2212", "-").replace("**", "").replace("`", "")
    return re.sub(r"\s+", " ", t)


def cargar_claims(ruta=CLAIMS):
    """Lee el claims.json; si falta o no parsea, falla cerrado."""
    if not ruta.is_file():
        raise FileNotFoundError("CLAIMS_INVALIDO: falta %s" % ruta.name)
    try:
        return json.loads(ruta.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise ValueError("CLAIMS_INVALIDO: %s no parsea (%s)" % (ruta.name, exc))


def _portador_del_deriva(c, nombre, fallos):
    """Verifica el eslabon DERIVA/CRUCE y devuelve el portador nombrado o None."""
    m = DERIVA.match(c["deriva"])
    if m and m.group("ruta") == TESTIGO_REL:
        fallos.append(
            "DERIVA_AL_TESTIGO: %s deriva %r — el testigo se verificaria a si mismo (D13)"
            % (nombre, c["deriva"])
        )
        return None
    if not m or m.group("ruta") not in CARGA:
        fallos.append(
            "PARSER_AUSENTE: %s deriva %r y no nombra un portador de CARGA"
            % (nombre, c["deriva"])
        )
        return None
    try:
        mod = modulo(m.group("ruta"))
    except FileNotFoundError as exc:
        fallos.append("PARSER_AUSENTE: %s · %s" % (nombre, exc))
        return None
    funcion = getattr(mod, m.group("funcion"), None)
    if not callable(funcion):
        fallos.append(
            "PARSER_AUSENTE: %s deriva %r y esa funcion no existe"
            % (nombre, c["deriva"])
        )
        return None
    fuente = inspect.getsource(funcion)
    faltan = [t for t in CARGA[m.group("ruta")] if t not in fuente]
    if faltan:
        fallos.append(
            "DERIVACION_CIEGA: %s deriva en %s, que no lee %s (faltan %s)"
            % (nombre, funcion.__name__, m.group("ruta"), ",".join(faltan))
        )
        return None
    raiz = c["ruta"].partition(".")[0]
    if PORTADOR_DE_RAIZ.get(raiz) != m.group("ruta"):
        fallos.append(
            "DERIVACION_CRUZADA: %s resuelve en el crudo %r (portador %r) y deriva en %r"
            % (nombre, raiz, PORTADOR_DE_RAIZ.get(raiz), m.group("ruta"))
        )
        return None
    return m.group("ruta")


def inconsistencias_claims(obj, textos=None):
    """Devuelve las mentiras medibles del claims.json (vacio = contrato cumplido)."""
    fallos = []
    if not isinstance(obj, dict):
        return ["CLAIMS_INVALIDO: la raiz no es un objeto"]
    if obj.get("clase") != "A":
        fallos.append("CLAIMS_INVALIDO: clase %r no es mecanizable" % (obj.get("clase"),))
    lista = obj.get("claims")
    if not isinstance(lista, list) or not lista:
        return fallos + ["CLAIMS_VACIO: un claims.json sin claims no declara nada"]
    if textos is None:
        textos = {}

    ids = set()
    for i, c in enumerate(lista):
        faltan = [k for k in CAMPOS_CLAIM if not isinstance(c, dict) or not c.get(k)]
        if faltan:
            fallos.append("CLAIMS_INVALIDO: claim %d sin %s" % (i, ",".join(faltan)))
            continue
        nombre = c["id"]

        if nombre in ids:
            fallos.append("CLAIM_DUPLICADO: %s aparece dos veces" % nombre)
        ids.add(nombre)

        if c["polaridad"] not in POLARIDADES:
            fallos.append(
                "POLARIDAD_INVENTADA: %s polaridad %r fuera de %r"
                % (nombre, c["polaridad"], list(POLARIDADES))
            )

        dato_ok = (RAIZ / c["dato"]).is_file()
        if not dato_ok:
            fallos.append(
                "DATO_SIN_PORTADOR: %s declara %s y no existe en el arbol"
                % (nombre, c["dato"])
            )

        _portador_del_deriva(c, nombre, fallos)

        if dato_ok:
            try:
                crudo, resto = crudo_de(c["ruta"])
                valor = resolver(crudo, resto)
            except ValueError as exc:
                causa = str(exc)
                fallos.append("%s: %s · %s" % (causa.split(":", 1)[0], nombre, causa))
            else:
                if not porta_valor(valor, c["afirma"]):
                    fallos.append(
                        "VALOR_NO_ES_EL_CRUDO: %s afirma %r y el crudo da %s en %s"
                        % (nombre, c["afirma"], valor, c["ruta"])
                    )

        prosa_rel = c["prosa"]
        if prosa_rel not in textos:
            ruta_prosa = RAIZ / prosa_rel
            if not ruta_prosa.is_file():
                fallos.append("PROSA_AUSENTE: %s cita %s" % (nombre, prosa_rel))
                textos[prosa_rel] = None
            else:
                textos[prosa_rel] = prosa(ruta_prosa.read_text(encoding="utf-8"))
        if textos[prosa_rel] is None:
            continue
        if c["afirma"] not in textos[prosa_rel]:
            fallos.append(
                "README_DESALINEADO: %s afirma %r y %s no lo dice"
                % (nombre, c["afirma"], prosa_rel)
            )
    return fallos


def test_el_claims_declara_solo_lo_que_el_crudo_mide():
    """Portador real, derivacion que lo lee, valor vigente y prosa que lo cita."""
    fallos = inconsistencias_claims(cargar_claims())
    assert not fallos, "; ".join(fallos)


def test_el_censo_no_pierde_claims():
    """El censo de §9.2 midio 10 mecanizables: declarar menos es CLAIM_PERDIDO."""
    claims = cargar_claims()["claims"]
    assert len(claims) >= 10, (
        "CLAIM_PERDIDO: el censo midio 10 figuras mecanizables y el contrato declara %d"
        % len(claims)
    )


def test_ningun_deriva_apunta_al_testigo():
    """D13 en su forma pura: el contrato no puede verificarse con su propio testigo."""
    for c in cargar_claims()["claims"]:
        m = DERIVA.match(c["deriva"])
        assert m, "DERIVA_MALFORMADA: %s declara %r" % (c["id"], c["deriva"])
        assert m.group("ruta") != TESTIGO_REL, (
            "DERIVA_AL_TESTIGO: %s apunta a %s" % (c["id"], TESTIGO_REL)
        )


def test_la_normalizacion_no_es_vacua():
    """Si el literal sobreviviera al Markdown crudo, la normalizacion no haria nada."""
    crudo = (RAIZ / "README.md").read_text(encoding="utf-8")
    normalizado = prosa(crudo)
    necesitan = [
        c["afirma"]
        for c in cargar_claims()["claims"]
        if c["afirma"] not in crudo and c["afirma"] in normalizado
    ]
    assert necesitan, "NORMALIZACION_VACUA: ninguna afirmacion la necesita"


def test_el_testigo_de_claims_sabe_fallar():
    """Falsificador del testigo: cada mentira del claims.json tiene que ser cazada."""
    sano = cargar_claims()
    assert not inconsistencias_claims(sano), "EL_CLAIMS_SANO_YA_FALLA"

    def mutar(indice, campo, valor):
        copia = json.loads(json.dumps(sano))
        copia["claims"][indice][campo] = valor
        return copia

    duplicado = json.loads(json.dumps(sano))
    duplicado["claims"][1]["id"] = duplicado["claims"][0]["id"]

    mutaciones = {
        "DATO_SIN_PORTADOR": mutar(0, "dato", "solver_que_no_existe.py"),
        "PARSER_AUSENTE": mutar(
            0, "deriva", "parser:tests/test_ancla_banco.py::test_que_no_existe"
        ),
        "DERIVACION_CIEGA": mutar(
            0, "deriva", "parser:tests/test_ancla_banco.py::enmascarar"
        ),
        "DERIVA_AL_TESTIGO": mutar(
            0, "deriva", "parser:tests/test_claims_witness.py::inconsistencias_claims"
        ),
        "DERIVACION_CRUZADA": mutar(
            0, "deriva", "parser:sandbox.py::_ramas_del_validador"
        ),
        "RUTA_AUSENTE": mutar(0, "ruta", "banco.cobertura.no_existe"),
        "VALOR_NO_ES_EL_CRUDO": mutar(0, "ruta", "banco.cobertura.ramas"),
        "POLARIDAD_INVENTADA": mutar(0, "polaridad", "creciente"),
        "README_DESALINEADO": mutar(0, "afirma", "9/9 por causa y por rama"),
        "CLAIM_DUPLICADO": duplicado,
        "CLAIMS_VACIO": {"clase": "A", "claims": []},
        "CLAIMS_INVALIDO": {"clase": "C"},
    }
    for esperado, roto in mutaciones.items():
        cazado = inconsistencias_claims(roto)
        assert any(f.startswith(esperado + ":") for f in cazado), (
            "MUTACION_NO_CAZADA: %s — el testigo no discrimina (%r)" % (esperado, cazado)
        )

    roto = Path("/tmp/rg_claims_roto.json")
    roto.write_text("{ esto no es json", encoding="utf-8")
    try:
        try:
            cargar_claims(roto)
        except ValueError as exc:
            assert "CLAIMS_INVALIDO" in str(exc), "CLAIMS_INVALIDO_SIN_CAUSA"
        else:
            raise AssertionError("CLAIMS_ROTO_PARSEA")
    finally:
        roto.unlink(missing_ok=True)


if __name__ == "__main__":
    fallos = inconsistencias_claims(cargar_claims())
    for f in fallos:
        print(f)
    print("CLAIMS: %s" % ("ROJO" if fallos else "SANO"))
