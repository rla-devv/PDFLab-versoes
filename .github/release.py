"""Cria a Release da versão do atualizacao.json, com os arquivos marcados com essa versão em "release" e o
instalador (PDF Lab.zip → PDFLab.zip). Roda no GitHub Actions (release.yml); usa só a biblioteca padrão e o gh.

- Versão que já tem Release publicada com todos os arquivos: não faz nada.
- Cria como rascunho, envia os arquivos e só então publica (ninguém vê uma Release pela metade).
- Rascunho ou Release incompleta de uma tentativa anterior: envia só o que falta.
- Confere o SHA-256 de cada arquivo com o atualizacao.json antes de enviar.
Copiado do repositório do código (publicacao/release.py) pelo publicar.py; não edite aqui.
"""
import hashlib, json, os, re, shutil, subprocess, sys, tempfile
from pathlib import Path

REPO, COMMIT = os.environ['GH_REPO'], os.environ['COMMIT']
INSTALADOR = ('PDF Lab.zip', 'PDFLab.zip')   # arquivo no repositório, nome na Release (sem espaço)
RE_NOME = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]*')
RE_ORIGEM = re.compile(r'(?:versoes|programa/\d+(?:\.\d+){1,3})/[A-Za-z0-9][A-Za-z0-9_.-]*')


def gh(*args):
    r = subprocess.run(['gh', 'api', *args], capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f'gh api {args[0]} falhou: {r.stderr}')
    return json.loads(r.stdout or 'null')


def main():
    m = json.loads(Path('atualizacao.json').read_text(encoding='utf-8'))
    versao = m['versao']
    if not re.fullmatch(r'\d+(?:\.\d+){1,3}', versao):
        sys.exit(f'versão inválida: {versao}')
    tag = f'v{versao}'
    arquivos = {}   # nome na Release -> arquivo no repositório
    for a in m.get('arquivos', []):
        ref = a.get('release')
        if not ref or not ref.startswith(tag + '/'):
            continue   # sem Release, ou de uma versão anterior (arquivo que não mudou)
        nome, origem = ref[len(tag) + 1:], a['origem']
        if not RE_NOME.fullmatch(nome) or not RE_ORIGEM.fullmatch(origem):
            sys.exit(f'nome ou origem inválidos: {ref} / {origem}')
        dados = Path(origem).read_bytes()
        if hashlib.sha256(dados).hexdigest() != a['sha256'] or len(dados) != a['tamanho']:
            sys.exit(f'{origem} não confere com o atualizacao.json')
        if arquivos.setdefault(nome, origem) != origem:
            sys.exit(f'dois arquivos com o nome {nome}')
    if Path(INSTALADOR[0]).is_file():
        arquivos[INSTALADOR[1]] = INSTALADOR[0]
    if not arquivos:
        print('nada para publicar')
        return

    releases = gh('--paginate', '--slurp', f'repos/{REPO}/releases')
    releases = [r for pagina in releases for r in pagina] if releases and isinstance(releases[0], list) else releases
    rel = next((r for r in releases if r['tag_name'] == tag), None)
    ja = {x['name'] for x in rel['assets']} if rel else set()
    if rel and not rel['draft'] and set(arquivos) <= ja:
        print(f'{tag} já tem Release completa: nada a fazer')
        return
    if not rel:
        rel = gh('--method', 'POST', f'repos/{REPO}/releases', '-f', f'tag_name={tag}', '-f', f'target_commitish={COMMIT}',
                 '-f', f'name=PDF Lab {versao}', '-f', 'body=' + '\n'.join(m.get('novidades', [])), '-F', 'draft=true')
    with tempfile.TemporaryDirectory() as tmp:
        for nome, origem in arquivos.items():
            if nome in ja:
                continue
            copia = Path(tmp) / nome
            shutil.copyfile(origem, copia)
            gh('--method', 'POST', '-H', 'Content-Type: application/octet-stream',
               f'https://uploads.github.com/repos/{REPO}/releases/{rel["id"]}/assets?name={nome}', '--input', str(copia))
            print(f'enviado: {nome}')
    if rel['draft']:
        gh('--method', 'PATCH', f'repos/{REPO}/releases/{rel["id"]}', '-F', 'draft=false', '-f', 'make_latest=true')
    print(f'Release {tag} publicada com {len(arquivos)} arquivo(s)')


if __name__ == '__main__':
    main()
