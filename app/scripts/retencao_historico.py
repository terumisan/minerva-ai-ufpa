"""Simula expiração; só exclui com prazo explícito e --aplicar."""
import argparse
from contextlib import closing

try:
    from .ingestao import conectar_banco
except ImportError:
    from ingestao import conectar_banco


def expirar(conn, dias, aplicar=False):
    if dias < 1:
        raise ValueError("Prazo deve ser positivo")
    resultado = {}
    with conn, conn.cursor() as cur:
        for tabela in ("historico_minerva", "avaliacoes_minerva"):
            cur.execute("SELECT to_regclass(%s)", (tabela,))
            if cur.fetchone()[0] is None:
                resultado[tabela] = 0
                continue
            cur.execute(f"SELECT count(*) FROM {tabela} WHERE data_hora < now() - make_interval(days => %s)", (dias,))
            resultado[tabela] = cur.fetchone()[0]
            if aplicar:
                cur.execute(f"DELETE FROM {tabela} WHERE data_hora < now() - make_interval(days => %s)", (dias,))
    return {"aplicado": aplicar, "dias": dias, "registros": resultado}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dias", required=True, type=int)
    p.add_argument("--aplicar", action="store_true")
    args = p.parse_args()
    with closing(conectar_banco()) as conn:
        print(expirar(conn, args.dias, args.aplicar))


if __name__ == "__main__":
    main()
