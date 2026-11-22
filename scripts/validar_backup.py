#!/usr/bin/env python3
"""Restaura um dump em banco temporário; nunca restaura sobre a base ativa."""
import argparse
import json
import re
import subprocess
import uuid
from pathlib import Path


def executar(script, *args, stdin=None):
    return subprocess.run(
        ["docker", "exec", "-i", "ufpa_rag_db", "sh", "-c", script, "sh", *args],
        stdin=stdin, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True,
    ).stdout.decode()


def inventario(banco):
    def query(sql):
        return executar('psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$1" -At -c "$2"', banco, sql).strip()
    tabelas = query("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename").splitlines()
    resultado = {}
    for tabela in tabelas:
        if not re.fullmatch(r"[a-z_][a-z_0-9]*", tabela):
            raise ValueError("Nome de tabela fora do padrão esperado")
        resultado[tabela] = query(f'SELECT count(*), md5(string_agg(t::text, chr(10) ORDER BY t::text)) FROM "{tabela}" t')
    return resultado


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dump", type=Path)
    parser.add_argument("--relatorio", type=Path)
    args = parser.parse_args()
    nome = "minerva_restore_" + uuid.uuid4().hex[:12]
    base = executar('printf "%s" "$POSTGRES_DB"').strip()
    assert nome != base
    # Use um dump recém-criado e sem gravações concorrentes para comparar
    # com o estado atual; mudanças posteriores ao dump causam divergência.
    antes = inventario(base)
    executar('createdb -U "$POSTGRES_USER" "$1"', nome)
    try:
        with args.dump.open("rb") as dump:
            executar('pg_restore -U "$POSTGRES_USER" -d "$1" --no-owner --no-privileges --exit-on-error', nome, stdin=dump)
        depois = inventario(nome)
        if antes != depois:
            raise ValueError("Dump restaurado difere da base atual; verificar gravações após o backup")
        report = {"restore_aprovado": True, "tabelas_contagens_hashes": depois}
        if args.relatorio:
            args.relatorio.write_text(json.dumps(report, indent=2))
            args.relatorio.chmod(0o600)
        print(f"Restauração aprovada: {len(depois)} tabelas com contagens e hashes coincidentes")
    finally:
        executar('dropdb -U "$POSTGRES_USER" --force "$1"', nome)


if __name__ == "__main__":
    main()
