"""Carga inicial do modulo Processos a partir do que ja existe: pz_prazos e pz_pastas.

Opcional. Cria UM processo por CNJ distinto (e clientes pelo nome), sem apagar nada e
sem duplicar: pode rodar de novo, na segunda vez so aparece o que ficou de fora.

Uso, na pasta backend/ (sempre comece pelo --simular):

    python carregar_processos_inicial.py --simular
    python carregar_processos_inicial.py --aplicar
    python carregar_processos_inicial.py --simular --incluir-sem-processo

--simular   so le e mostra o que criaria. Nao grava dado (cria as tabelas novas se faltarem).
--aplicar   copia o banco (arquivo .bak_carga_AAAAMMDD-HHMMSS ao lado) e grava.
--incluir-sem-processo
            tambem cria processo so com pasta, para pastas da REDE sem CNJ.
            Sao muitas: so use se quiser esse cadastro.

Destino: backend/carregar_processos_inicial.py
"""
import argparse
import asyncio
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.database import AsyncSessionLocal, init_db  # noqa: E402
from app.config import settings  # noqa: E402
from app import processos_nucleo as nuc  # noqa: E402


def _copia_do_banco() -> str:
    """Copia consistente do SQLite (API de backup), antes de gravar. '' se nao for arquivo."""
    url = settings.DATABASE_URL
    if 'sqlite' not in url or ':///' not in url:
        return ''
    origem = url.split(':///', 1)[1].split('?', 1)[0]
    if not Path(origem).exists():
        return ''
    destino = f"{origem}.bak_carga_{time.strftime('%Y%m%d-%H%M%S')}"
    with sqlite3.connect(origem) as src, sqlite3.connect(destino) as dst:
        src.backup(dst)
    return destino


def _imprime_plano(plano: dict) -> None:
    print(f"Processos a criar: {len(plano['novos'])} "
          f"(com CNJ: {plano['com_numero']}, so pasta: {plano['sem_numero']})")
    print(f"Ja existiam (pulados): {plano['ja_existem']}")
    print(f"Clientes novos (pelo nome): {plano['clientes_novos']}")
    print('Primeiros 15:')
    for it in plano['novos'][:15]:
        print(f"  pasta={it['pasta'] or '-':<10} CNJ={it['numero'] or '(sem)':<26} "
              f"cliente={it['cliente'] or '-'}  responsavel={it['responsavel_email'] or '-'}")


async def main(aplicar: bool, incluir_sem: bool) -> int:
    await init_db()
    async with AsyncSessionLocal() as db:
        plano = await nuc.planejar_carga(db, incluir_sem_processo=incluir_sem)
    _imprime_plano(plano)
    if not aplicar:
        print('\nSIMULACAO: nada foi gravado. Para gravar, rode com --aplicar.')
        return 0
    if not plano['novos']:
        print('\nNada a criar. Nenhuma copia nem gravacao feitas.')
        return 0
    copia = _copia_do_banco()
    print(f'\nCopia do banco antes da carga: {copia or "(nao foi possivel; confira antes)"}')
    async with AsyncSessionLocal() as db:
        res = await nuc.aplicar_carga(db, plano)
    print(f"Gravado: {res['processos_criados']} processo(s), {res['clientes_criados']} cliente(s).")
    async with AsyncSessionLocal() as db:
        de_novo = await nuc.planejar_carga(db, incluir_sem_processo=incluir_sem)
    print(f"Conferencia: novos em uma segunda leitura = {len(de_novo['novos'])} (esperado 0).")
    return 0 if not de_novo['novos'] else 1


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description='Carga inicial de processos (pz_prazos e pz_pastas).')
    grupo = ap.add_mutually_exclusive_group(required=True)
    grupo.add_argument('--simular', action='store_true', help='so mostra o que faria')
    grupo.add_argument('--aplicar', action='store_true', help='grava (com copia do banco antes)')
    ap.add_argument('--incluir-sem-processo', action='store_true')
    args = ap.parse_args()
    sys.exit(asyncio.run(main(aplicar=args.aplicar, incluir_sem=args.incluir_sem_processo)))
