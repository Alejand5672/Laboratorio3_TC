"""Conversor de expresiones regulares infijas a postfijas."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path


CONCATENACION = "·"
OPERADORES_BINARIOS = {"|", CONCATENACION}
OPERADORES_POSTFIJOS = {"*", "+", "?"}
PRECEDENCIA = {"|": 1, CONCATENACION: 2}


class ErrorExpresion(ValueError):
    """Error de sintaxis acompañado por una posicion legible."""


@dataclass(frozen=True)
class Token:
    texto: str
    posicion: int
    literal: bool = False


def tokenizar(expresion: str) -> list[Token]:
    """Separa operadores, literales escapados y clases de caracteres."""
    tokens: list[Token] = []
    i = 0

    while i < len(expresion):
        caracter = expresion[i]
        posicion = i + 1

        if caracter.isspace():
            i += 1
            continue

        if caracter == "\\":
            if i + 1 == len(expresion):
                raise ErrorExpresion(
                    f"barra invertida sin caracter escapado en la posicion {posicion}"
                )
            tokens.append(Token(expresion[i : i + 2], posicion, literal=True))
            i += 2
            continue

        if caracter == "[":
            inicio = i
            i += 1
            escapado = False
            while i < len(expresion):
                actual = expresion[i]
                if escapado:
                    escapado = False
                elif actual == "\\":
                    escapado = True
                elif actual == "]":
                    break
                i += 1

            if i == len(expresion):
                raise ErrorExpresion(
                    f"clase de caracteres sin ']' en la posicion {posicion}"
                )
            if i == inicio + 1:
                raise ErrorExpresion(f"clase de caracteres vacia en la posicion {posicion}")
            tokens.append(Token(expresion[inicio : i + 1], posicion, literal=True))
            i += 1
            continue

        if caracter in "()|*+?":
            tokens.append(Token(caracter, posicion))
        else:
            tokens.append(Token(caracter, posicion, literal=True))
        i += 1

    if not tokens:
        raise ErrorExpresion("la expresion esta vacia")
    return tokens


def puede_terminar(token: Token) -> bool:
    return token.literal or token.texto == ")" or token.texto in OPERADORES_POSTFIJOS


def puede_iniciar(token: Token) -> bool:
    return token.literal or token.texto == "("


def insertar_concatenacion(tokens: list[Token]) -> tuple[list[Token], list[str]]:
    """Agrega el operador · cuando la concatenacion estaba implicita."""
    resultado: list[Token] = []
    inserciones: list[str] = []

    for token in tokens:
        if resultado and puede_terminar(resultado[-1]) and puede_iniciar(token):
            resultado.append(Token(CONCATENACION, token.posicion))
            inserciones.append(
                f"se inserto '·' antes de la posicion {token.posicion} "
                f"(entre {resultado[-2].texto!r} y {token.texto!r})"
            )
        resultado.append(token)
    return resultado, inserciones


def formatear(tokens: list[str] | list[Token]) -> str:
    textos = [token.texto if isinstance(token, Token) else token for token in tokens]
    return " ".join(textos) if textos else "∅"


def a_postfija(tokens: list[Token]) -> tuple[list[str], list[str]]:
    """Aplica Shunting Yard y registra el estado después de cada token."""
    salida: list[str] = []
    pila: list[Token] = []
    pasos: list[str] = []
    espera_operando = True

    for numero, token in enumerate(tokens, start=1):
        texto = token.texto

        if token.literal:
            if not espera_operando:
                raise ErrorExpresion(
                    f"falta un operador antes de {texto!r} en la posicion {token.posicion}"
                )
            salida.append(texto)
            accion = "enviar operando a la salida"
            espera_operando = False
        elif texto == "(":
            if not espera_operando:
                raise ErrorExpresion(f"falta un operador antes de '(' en {token.posicion}")
            pila.append(token)
            accion = "apilar '('"
            espera_operando = True
        elif texto == ")":
            if espera_operando:
                raise ErrorExpresion(f"')' inesperado en la posicion {token.posicion}")
            while pila and pila[-1].texto != "(":
                salida.append(pila.pop().texto)
            if not pila:
                raise ErrorExpresion(f"')' sin apertura en la posicion {token.posicion}")
            pila.pop()
            accion = "vaciar hasta '(' y descartar los parentesis"
            espera_operando = False
        elif texto in OPERADORES_POSTFIJOS:
            if espera_operando:
                raise ErrorExpresion(
                    f"operador {texto!r} sin operando en la posicion {token.posicion}"
                )
            salida.append(texto)
            accion = f"enviar operador postfijo {texto!r} a la salida"
            espera_operando = False
        elif texto in OPERADORES_BINARIOS:
            if espera_operando:
                raise ErrorExpresion(
                    f"operador {texto!r} sin operando izquierdo en {token.posicion}"
                )
            while (
                pila
                and pila[-1].texto in OPERADORES_BINARIOS
                and PRECEDENCIA[pila[-1].texto] >= PRECEDENCIA[texto]
            ):
                salida.append(pila.pop().texto)
            pila.append(token)
            accion = f"apilar operador {texto!r} segun su precedencia"
            espera_operando = True
        else:
            raise ErrorExpresion(f"token no reconocido: {texto!r}")

        pasos.append(
            f"{numero:>3} | {texto!r:<12} | {accion:<48} | "
            f"{formatear([x.texto for x in pila]):<20} | {formatear(salida)}"
        )

    if espera_operando:
        raise ErrorExpresion("la expresion termina esperando un operando")

    while pila:
        token = pila.pop()
        if token.texto == "(":
            raise ErrorExpresion(f"'(' sin cierre en la posicion {token.posicion}")
        salida.append(token.texto)
        pasos.append(
            f"  - | {'fin':<12} | {'vaciar operador restante':<48} | "
            f"{formatear([x.texto for x in pila]):<20} | {formatear(salida)}"
        )
    return salida, pasos


def convertir_extensiones(postfija: list[str]) -> tuple[list[str], list[str]]:
    """Convierte R+ en RR*· y R? en Rε| usando fragmentos postfijos."""
    pila: list[list[str]] = []
    pasos: list[str] = []

    for token in postfija:
        if token not in OPERADORES_BINARIOS | OPERADORES_POSTFIJOS:
            pila.append([token])
        elif token == "*":
            if not pila:
                raise ErrorExpresion("'*' no tiene operando")
            pila[-1] = [*pila[-1], "*"]
        elif token == "+":
            if not pila:
                raise ErrorExpresion("'+' no tiene operando")
            operando = pila.pop()
            convertido = [*operando, *operando, "*", CONCATENACION]
            pila.append(convertido)
            pasos.append(f"{formatear(operando)} +  =>  {formatear(convertido)}")
        elif token == "?":
            if not pila:
                raise ErrorExpresion("'?' no tiene operando")
            operando = pila.pop()
            convertido = [*operando, "ε", "|"]
            pila.append(convertido)
            pasos.append(f"{formatear(operando)} ?  =>  {formatear(convertido)}")
        else:
            if len(pila) < 2:
                raise ErrorExpresion(f"{token!r} no tiene dos operandos")
            derecho = pila.pop()
            izquierdo = pila.pop()
            pila.append([*izquierdo, *derecho, token])

    if len(pila) != 1:
        raise ErrorExpresion("la expresion no forma un arbol de operadores valido")
    return pila[0], pasos


def procesar(expresion: str) -> tuple[list[str], list[str], list[str], list[str]]:
    tokens = tokenizar(expresion)
    tokens_con_concat, inserciones = insertar_concatenacion(tokens)
    postfija_extendida, pasos = a_postfija(tokens_con_concat)
    postfija_final, conversiones = convertir_extensiones(postfija_extendida)
    return postfija_final, inserciones, pasos, conversiones


def procesar_archivo(ruta: Path) -> int:
    try:
        lineas = ruta.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as error:
        print(f"No se pudo leer '{ruta}': {error}")
        return 1

    expresiones = [(n, linea.strip()) for n, linea in enumerate(lineas, 1) if linea.strip()]
    if not expresiones:
        print(f"El archivo '{ruta}' no contiene expresiones.")
        return 1

    hubo_errores = False
    for indice, (_, expresion) in enumerate(expresiones, start=1):
        print("\n" + "=" * 100)
        print(f"EXPRESION {indice}: {expresion}")
        try:
            postfija, inserciones, pasos, conversiones = procesar(expresion)
            print("\n1. CONCATENACIONES IMPLICITAS")
            print("\n".join(f"   - {paso}" for paso in inserciones) or "   Ninguna.")
            print("\n2. PASOS DE SHUNTING YARD")
            print("Paso | Token        | Accion                                           | Pila                 | Salida")
            print("-" * 130)
            print("\n".join(pasos))
            print("\n3. CONVERSION DE EXTENSIONES (+ y ?)")
            print("\n".join(f"   - {paso}" for paso in conversiones) or "   No fue necesaria.")
            print(f"\nPOSTFIJA FINAL: {formatear(postfija)}")
        except ErrorExpresion as error:
            hubo_errores = True
            print(f"\nERROR: {error}")

    return 1 if hubo_errores else 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Convierte expresiones regulares infijas a postfijas con Shunting Yard."
    )
    parser.add_argument(
        "archivo",
        nargs="?",
        type=Path,
        default=Path(__file__).with_name("expresiones_problema3.txt"),
        help="archivo UTF-8 con una expresion por linea",
    )
    return procesar_archivo(parser.parse_args().archivo)


if __name__ == "__main__":
    raise SystemExit(main())
