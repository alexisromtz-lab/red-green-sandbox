"""Identidad citable: las cuatro superficies de version no pueden separarse.

HUELLA-CIERRE-RED-GREEN-20261127

El 27-Nov-2026 `pyproject.toml:7` decia `1.0.0` y `CITATION.cff` decia `1.3.0` —la
version del deposito y del tag v1.3.0—, y nada fallaba: ningun lector cruzaba las
superficies. Un desfase declarado en un comentario no es un desfase medido.

Aqui la version vive en cuatro sitios (`pyproject.toml`, `CITATION.cff`,
`sandbox.VERSION` y `.zenodo.json`) y este archivo exige que los cuatro digan lo
mismo. T4 es el control negativo: la misma comparacion, corrida sobre una copia con
`pyproject.toml` drifteado, TIENE que nombrar el archivo culpable. Una prueba que no
puede enrojecer no mide nada.
"""

import json
import os
import re
import shutil
import subprocess
import tempfile

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_RE_PYPROJECT = re.compile(r'(?m)^version\s*=\s*"([^"]+)"')
_RE_CFF = re.compile(r"(?m)^version:\s*([^\s#]+)")
_RE_MOTOR = re.compile(r'(?m)^VERSION\s*=\s*"([^"]+)"')


def _leer(raiz, nombre):
    with open(os.path.join(raiz, nombre), encoding="utf-8") as f:
        return f.read()


def _version_pyproject(raiz):
    m = _RE_PYPROJECT.search(_leer(raiz, "pyproject.toml"))
    return m.group(1) if m else None


def _version_cff(raiz):
    m = _RE_CFF.search(_leer(raiz, "CITATION.cff"))
    return m.group(1) if m else None


def _version_motor(raiz):
    m = _RE_MOTOR.search(_leer(raiz, "sandbox.py"))
    return m.group(1) if m else None


def _version_zenodo(raiz):
    ruta = os.path.join(raiz, ".zenodo.json")
    if not os.path.exists(ruta):
        return None
    with open(ruta, encoding="utf-8") as f:
        return json.load(f).get("version")


def _git(raiz, *args):
    return subprocess.run(["git", *args], cwd=raiz, capture_output=True, text=True)


def _tag_existe(raiz, version):
    """Pregunta al REPOSITORIO, no al checkout.

    `actions/checkout` clona con `fetch-depth: 1` y sin tags: ahi `git tag --list`
    sale vacio aunque el tag exista en el repositorio, y un lector que se fie del
    espacio local enrojece por el universo del observador, no por el sujeto
    (medido 2026-11-27: local verde con v1.3.0, CI rojo con el mismo arbol).

    Regla: si el espacio local de tags esta VACIO, esta truncado y se pregunta al
    remoto; si tiene tags, el tag que falta falta de verdad. Un git que no
    contesta es NO_MEDIDO — None — y nunca se lee como verde.
    """
    ref = "refs/tags/v" + version
    p = _git(raiz, "show-ref", "--verify", "--quiet", ref)
    if p.returncode == 0:
        return True
    if p.returncode != 1:
        return None
    local = _git(raiz, "tag", "--list")
    if local.returncode != 0:
        return None
    if local.stdout.strip():
        return False
    remoto = _git(raiz, "ls-remote", "--tags", "origin", ref)
    if remoto.returncode != 0:
        return None
    return bool(remoto.stdout.strip())


def divergencias(raiz=None):
    """Nombra cada superficie que se separa. Lista vacia = concordancia medida."""
    raiz = os.path.abspath(raiz or RAIZ)
    fuentes = {
        "pyproject.toml": _version_pyproject(raiz),
        "CITATION.cff": _version_cff(raiz),
        "sandbox.py": _version_motor(raiz),
        ".zenodo.json": _version_zenodo(raiz),
    }
    malas = []
    for nombre, valor in fuentes.items():
        if valor is None:
            malas.append("%s: sin version declarada" % nombre)
    vistas = {v for v in fuentes.values() if v is not None}
    if len(vistas) > 1:
        detalle = ", ".join("%s=%s" % (k, v) for k, v in sorted(fuentes.items()))
        malas.append("las superficies no concuerdan (%s)" % detalle)
    if len(vistas) == 1:
        hay = _tag_existe(raiz, next(iter(vistas)))
        if hay is False:
            malas.append("sin tag v%s: la version declarada no apunta a ningun objeto" % next(iter(vistas)))
        elif hay is None:
            malas.append("tag NO_MEDIDO: git no respondio en %s" % raiz)
    return malas


def test_01_las_cuatro_superficies_concuerdan():
    malas = divergencias()
    assert malas == [], "identidad citable rota: %s" % "; ".join(malas)


def test_02_el_doi_de_version_esta_en_la_cita_y_en_la_prosa():
    cff = _leer(RAIZ, "CITATION.cff")
    doi = re.search(r'(?m)^doi:\s*"([^"]+)"', cff).group(1)
    assert re.match(r"^10\.5281/zenodo\.\d+$", doi), "DOI con forma inesperada: %s" % doi
    assert doi in _leer(RAIZ, "README.md"), "el DOI de version no se nombra en README.md"


def test_03_el_deposito_declara_la_version_que_el_tag_apunta():
    with open(os.path.join(RAIZ, ".zenodo.json"), encoding="utf-8") as f:
        deposito = json.load(f)
    assert deposito["version"] == _version_cff(RAIZ)
    assert deposito["upload_type"] == "software"
    assert any(c.get("orcid") for c in deposito["creators"]), "creador sin ORCID"


def test_04_control_negativo_la_comparacion_muerde():
    """Si el lector no puede nombrar un desfase, no es un lector."""
    with tempfile.TemporaryDirectory() as tmp:
        for nombre in ("pyproject.toml", "CITATION.cff", "sandbox.py", ".zenodo.json"):
            shutil.copy(os.path.join(RAIZ, nombre), tmp)
        ruta = os.path.join(tmp, "pyproject.toml")
        with open(ruta, encoding="utf-8") as f:
            texto = f.read()
        with open(ruta, "w", encoding="utf-8") as f:
            f.write(_RE_PYPROJECT.sub('version = "9.9.9"', texto, count=1))
        malas = divergencias(tmp)
        assert malas, "el lector aprobo una copia con pyproject.toml drifteado"
        assert "pyproject.toml=9.9.9" in "; ".join(malas), malas
