#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Verificador de manifiesto — aparato de CI para repos de código y documento.

Mide el árbol RASTREADO (`git ls-files`) y falla cerrado:

  · `.json`  → debe parsear y NO estar vacío (`{}` o `[]` = vacío)
  · `.md`    → debe tener más de 10 líneas
  · `.py`    → debe compilar (sintaxis, sin ejecutar)

Si no hay ni un `.json`, ni un `.md`, ni un `.py`, no hay nada que medir → rojo.
Verde = «estos archivos existen, parsean y compilan», no «el repo es correcto».
"""
import json
import os
import subprocess
import sys
import tokenize

MIN_LINEAS_MD = 11  # más de 10 líneas


def rastreados():
    try:
        out = subprocess.run(
            ["git", "ls-files", "-z"], capture_output=True, check=True
        ).stdout
        rutas = [p for p in out.decode("utf-8", "surrogateescape").split("\0") if p]
        if rutas:
            return rutas
    except (OSError, subprocess.CalledProcessError):
        pass
    rutas = []
    for raiz, dirs, ficheros in os.walk("."):
        dirs[:] = [d for d in dirs if d not in (".git", "__pycache__", "node_modules", ".venv")]
        for f in ficheros:
            rutas.append(os.path.relpath(os.path.join(raiz, f), "."))
    return rutas


def leer(ruta):
    with open(ruta, "rb") as fh:
        return fh.read()


def main():
    rutas = rastreados()
    fallos, contados = [], {"json": 0, "md": 0, "py": 0}
    for ruta in rutas:
        ext = os.path.splitext(ruta)[1].lower()
        if ext not in (".json", ".md", ".py"):
            continue
        contados[ext[1:]] += 1
        try:
            if ext == ".py":
                compile(leer(ruta), ruta, "exec")
            elif ext == ".json":
                dato = json.loads(leer(ruta).decode("utf-8"))
                if dato in ({}, [], "", None):
                    fallos.append(f"{ruta}: json vacío")
            elif ext == ".md":
                texto = leer(ruta).decode("utf-8", "replace")
                n = len(texto.splitlines())
                if n < MIN_LINEAS_MD:
                    fallos.append(f"{ruta}: {n} líneas (< {MIN_LINEAS_MD})")
        except SyntaxError as e:
            fallos.append(f"{ruta}: no compila (línea {e.lineno}: {e.msg})")
        except (json.JSONDecodeError, UnicodeDecodeError, ValueError, tokenize.TokenError) as e:
            fallos.append(f"{ruta}: no parsea ({e})")
        except OSError as e:
            fallos.append(f"{ruta}: ilegible ({e})")

    total = sum(contados.values())
    print(
        f"MANIFIESTO: {total} artefactos · json {contados['json']} · "
        f"md {contados['md']} · py {contados['py']}"
    )
    if total == 0:
        print("NO_HAY_ARTEFACTOS: ni .json, ni .md, ni .py en el árbol rastreado — failing closed.")
        return 1
    for f in fallos:
        print(f"ROJO  {f}")
    if fallos:
        print(f"MANIFIESTO_ROTO: {len(fallos)} de {total} artefactos no miden — failing closed.")
        return 1
    print(f"MANIFIESTO_SANO: {total} artefactos parsean y compilan.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
