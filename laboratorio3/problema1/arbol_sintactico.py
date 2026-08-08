
from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

try:
    from graphviz import Digraph
    from graphviz.backend import ExecutableNotFound
except ImportError:
    Digraph = None  # type: ignore[assignment,misc]
    ExecutableNotFound = RuntimeError  # type: ignore[assignment,misc]


CONCAT = "·"
BINARIOS = {"|", CONCAT}
POSTFIJOS = {"*", "+", "?"}
PRECEDENCIA = {"|": 1, CONCAT: 2}


class ErrorExpresion(ValueError):
    """Indica que una expresión regular tiene sintaxis incorrecta."""


@dataclass(frozen=True)
class Token:
    texto: str
    posicion: int
    literal: bool = False


@dataclass
class Nodo:
    """Guarda la información de un nodo del árbol sintáctico."""

    valor: str
    izquierdo: Nodo | None = None
    derecho: Nodo | None = None

    @property
    def es_hoja(self) -> bool:
        return self.izquierdo is None and self.derecho is None


def tokenizar(expresion: str) -> list[Token]:
    """Separa operandos, operadores, escapes y clases de caracteres."""
    tokens: list[Token] = []
    i = 0
    while i < len(expresion):
        caracter = expresion[i]
        posicion = i + 1
        if caracter.isspace():
            i += 1
        elif caracter == "\\":
            if i + 1 >= len(expresion):
                raise ErrorExpresion(f"escape incompleto en la posición {posicion}")
            tokens.append(Token(expresion[i : i + 2], posicion, True))
            i += 2
        elif caracter == "[":
            inicio = i
            i += 1
            escapado = False
            while i < len(expresion):
                if escapado:
                    escapado = False
                elif expresion[i] == "\\":
                    escapado = True
                elif expresion[i] == "]":
                    break
                i += 1
            if i >= len(expresion):
                raise ErrorExpresion(f"clase sin cerrar en la posición {posicion}")
            tokens.append(Token(expresion[inicio : i + 1], posicion, True))
            i += 1
        else:
            tokens.append(Token(caracter, posicion, caracter not in "()|*+?"))
            i += 1
    if not tokens:
        raise ErrorExpresion("la expresión está vacía")
    return tokens


def termina_operando(token: Token) -> bool:
    return token.literal or token.texto == ")" or token.texto in POSTFIJOS


def inicia_operando(token: Token) -> bool:
    return token.literal or token.texto == "("


def insertar_concatenacion(tokens: list[Token]) -> tuple[list[Token], list[str]]:
    """Hace explícita la concatenación implícita mediante el símbolo ·."""
    resultado: list[Token] = []
    pasos: list[str] = []
    for token in tokens:
        if resultado and termina_operando(resultado[-1]) and inicia_operando(token):
            anterior = resultado[-1]
            resultado.append(Token(CONCAT, token.posicion))
            pasos.append(f"Entre {anterior.texto!r} y {token.texto!r} se insertó '{CONCAT}'.")
        resultado.append(token)
    return resultado, pasos


def formato(elementos: list[str]) -> str:
    return " ".join(elementos) if elementos else "∅"


def shunting_yard(tokens: list[Token]) -> tuple[list[str], list[str]]:
    """Convierte tokens infijos a postfix y registra cada estado del algoritmo."""
    salida: list[str] = []
    pila: list[Token] = []
    pasos: list[str] = []
    espera_operando = True

    for numero, token in enumerate(tokens, 1):
        texto = token.texto
        if token.literal:
            if not espera_operando:
                raise ErrorExpresion(f"falta operador antes de {texto!r}")
            salida.append(texto)
            accion = "operando a salida"
            espera_operando = False
        elif texto == "(":
            if not espera_operando:
                raise ErrorExpresion(f"falta operador antes de '(' en {token.posicion}")
            pila.append(token)
            accion = "apilar '('"
            espera_operando = True
        elif texto == ")":
            if espera_operando:
                raise ErrorExpresion(f"')' inesperado en {token.posicion}")
            while pila and pila[-1].texto != "(":
                salida.append(pila.pop().texto)
            if not pila:
                raise ErrorExpresion(f"')' sin apertura en {token.posicion}")
            pila.pop()
            accion = "vaciar hasta '('"
            espera_operando = False
        elif texto in POSTFIJOS:
            if espera_operando:
                raise ErrorExpresion(f"{texto!r} no tiene operando")
            salida.append(texto)
            accion = f"postfijo {texto!r} a salida"
        elif texto in BINARIOS:
            if espera_operando:
                raise ErrorExpresion(f"{texto!r} no tiene operando izquierdo")
            while (
                pila
                and pila[-1].texto in BINARIOS
                and PRECEDENCIA[pila[-1].texto] >= PRECEDENCIA[texto]
            ):
                salida.append(pila.pop().texto)
            pila.append(token)
            accion = f"apilar {texto!r} por precedencia"
            espera_operando = True
        else:
            raise ErrorExpresion(f"token desconocido: {texto!r}")

        pasos.append(
            f"{numero:>3} | {texto!r:<10} | {accion:<32} | "
            f"{formato([x.texto for x in pila]):<18} | {formato(salida)}"
        )

    if espera_operando:
        raise ErrorExpresion("la expresión termina esperando un operando")
    while pila:
        token = pila.pop()
        if token.texto == "(":
            raise ErrorExpresion(f"'(' sin cierre en {token.posicion}")
        salida.append(token.texto)
        pasos.append(
            f"  - | {'fin':<10} | {'vaciar pila':<32} | "
            f"{formato([x.texto for x in pila]):<18} | {formato(salida)}"
        )
    return salida, pasos


def simplificar_extensiones(postfix: list[str]) -> tuple[list[str], list[str]]:
    """Sustituye R+ por RR*· y R? por Rε| en la expresión postfix."""
    pila: list[list[str]] = []
    pasos: list[str] = []
    for token in postfix:
        if token not in BINARIOS | POSTFIJOS:
            pila.append([token])
        elif token == "*":
            if not pila:
                raise ErrorExpresion("'*' no tiene operando")
            pila[-1] = [*pila[-1], "*"]
        elif token == "+":
            if not pila:
                raise ErrorExpresion("'+' no tiene operando")
            operando = pila.pop()
            convertido = [*operando, *operando, "*", CONCAT]
            pila.append(convertido)
            pasos.append(f"{formato(operando)} +  ⇒  {formato(convertido)}")
        elif token == "?":
            if not pila:
                raise ErrorExpresion("'?' no tiene operando")
            operando = pila.pop()
            convertido = [*operando, "ε", "|"]
            pila.append(convertido)
            pasos.append(f"{formato(operando)} ?  ⇒  {formato(convertido)}")
        else:
            if len(pila) < 2:
                raise ErrorExpresion(f"{token!r} no tiene dos operandos")
            derecho = pila.pop()
            izquierdo = pila.pop()
            pila.append([*izquierdo, *derecho, token])
    if len(pila) != 1:
        raise ErrorExpresion("postfix inválido")
    return pila[0], pasos


def construir_arbol(postfix: list[str]) -> tuple[Nodo, list[str]]:
    """Construye el árbol sintáctico usando una pila de objetos Nodo."""
    pila: list[Nodo] = []
    pasos: list[str] = []
    for token in postfix:
        if token not in BINARIOS | {"*"}:
            pila.append(Nodo(token))
            accion = f"crear hoja {token!r}"
        elif token == "*":
            if not pila:
                raise ErrorExpresion("postfix inválido: '*' sin hijo")
            hijo = pila.pop()
            pila.append(Nodo("*", izquierdo=hijo))
            accion = "crear nodo unario '*'"
        else:
            if len(pila) < 2:
                raise ErrorExpresion(f"postfix inválido: {token!r} sin dos hijos")
            derecho = pila.pop()
            izquierdo = pila.pop()
            pila.append(Nodo(token, izquierdo, derecho))
            accion = f"crear nodo binario {token!r}"
        pasos.append(f"Token {token!r:<10} → {accion}; nodos en pila: {len(pila)}")
    if len(pila) != 1:
        raise ErrorExpresion("el postfix no produjo un único árbol")
    return pila[0], pasos


def crear_grafo(raiz: Nodo, titulo: str) -> Digraph:
    """Convierte los objetos Nodo en un grafo dirigido de la librería Graphviz."""
    if Digraph is None:
        raise ErrorExpresion(
            "Falta la librería 'graphviz'. Ejecute: python -m pip install graphviz"
        )
    grafo = Digraph(comment=titulo, format="png", encoding="utf-8")
    grafo.attr(
        label=titulo,
        labelloc="t",
        fontsize="18",
        fontname="Arial",
        rankdir="TB",
        bgcolor="white",
        nodesep="0.55",
        ranksep="0.80",
        splines="line",
    )
    grafo.attr("node", shape="circle", style="filled", fillcolor="#dbeafe",
               color="#1d4ed8", fontname="Arial", fontsize="16",
               width="0.60", height="0.60", fixedsize="true")
    grafo.attr("edge", color="#475569", penwidth="1.6")
    contador = 0

    def agregar(nodo: Nodo) -> str:
        nonlocal contador
        identificador = f"n{contador}"
        contador += 1
        grafo.node(identificador, nodo.valor)
        if nodo.izquierdo is not None:
            hijo_izquierdo = agregar(nodo.izquierdo)
            grafo.edge(identificador, hijo_izquierdo)
        if nodo.derecho is not None:
            hijo_derecho = agregar(nodo.derecho)
            grafo.edge(identificador, hijo_derecho)
        return identificador

    agregar(raiz)
    return grafo


def dibujar_con_graphviz(
    raiz: Nodo, salida: Path, indice: int, expresion: str, mostrar: bool
) -> Path:
    """Renderiza el árbol como PNG y opcionalmente lo abre en pantalla."""
    grafo = crear_grafo(raiz, f"Expresión {indice}: {expresion}")
    base = salida / f"arbol_expresion_{indice}"
    grafo.save(filename=f"{base.name}.gv", directory=salida)
    try:
        generado = grafo.render(
            filename=f"{base.name}.gv", directory=salida, cleanup=False, view=mostrar
        )
    except ExecutableNotFound as error:
        ruta_dot = base.with_suffix(".gv")
        ruta_dot.write_text(grafo.source, encoding="utf-8")
        raise ErrorExpresion(
            "Graphviz no encontró el ejecutable 'dot'. Instale Graphviz y agréguelo al PATH. "
            f"El código DOT se guardó en {ruta_dot}."
        ) from error
    return Path(generado)


def procesar_archivo(ruta: Path, salida: Path, mostrar_arboles: bool) -> int:
    """Procesa cada línea, imprime la ejecución y genera los dibujos."""
    try:
        expresiones = [x.strip() for x in ruta.read_text(encoding="utf-8").splitlines() if x.strip()]
    except (OSError, UnicodeError) as error:
        print(f"No se pudo leer {ruta}: {error}")
        return 1
    if not expresiones:
        print("El archivo no contiene expresiones.")
        return 1

    salida.mkdir(parents=True, exist_ok=True)
    for indice, expresion in enumerate(expresiones, 1):
        print("\n" + "=" * 110)
        print(f"EXPRESIÓN {indice}: {expresion}")
        try:
            tokens, inserciones = insertar_concatenacion(tokenizar(expresion))
            postfix_extendido, pasos_sy = shunting_yard(tokens)
            postfix_final, simplificaciones = simplificar_extensiones(postfix_extendido)
            raiz, pasos_arbol = construir_arbol(postfix_final)

            print("\n1. CONCATENACIONES EXPLÍCITAS")
            print("\n".join(f"   {x}" for x in inserciones) or "   Ninguna.")
            print("\n2. CONVERSIÓN INFIX A POSTFIX (SHUNTING YARD)")
            print("Paso | Token      | Acción                           | Pila               | Salida")
            print("-" * 110)
            print("\n".join(pasos_sy))
            print(f"\nPOSTFIX CON EXTENSIONES: {formato(postfix_extendido)}")
            print("\n3. SIMPLIFICACIÓN DE + Y ?")
            print("\n".join(f"   {x}" for x in simplificaciones) or "   No fue necesaria.")
            print(f"POSTFIX FINAL: {formato(postfix_final)}")
            print("\n4. CONSTRUCCIÓN DEL ÁRBOL")
            print("\n".join(f"   {x}" for x in pasos_arbol))

            ruta_imagen = dibujar_con_graphviz(
                raiz, salida, indice, expresion, mostrar_arboles
            )
            print(f"\nÁRBOL GRAPHVIZ GENERADO: {ruta_imagen}")
        except ErrorExpresion as error:
            print(f"ERROR: {error}")
            return 1
    return 0


def main() -> int:
    carpeta = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description="Convierte regex infix a postfix y dibuja su árbol.")
    parser.add_argument("archivo", nargs="?", type=Path, default=carpeta / "expresiones.txt")
    parser.add_argument(
        "--sin-ventana",
        action="store_true",
        help="genera los PNG con Graphviz sin abrir el visor de imágenes",
    )
    argumentos = parser.parse_args()
    return procesar_archivo(argumentos.archivo, carpeta / "arboles", not argumentos.sin_ventana)


if __name__ == "__main__":
    raise SystemExit(main())
