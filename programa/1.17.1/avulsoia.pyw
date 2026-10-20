"""Avulso IA — abre o editor de PDF numa janela própria do Windows.

A interface é a página AvulsoIA-editorPDF.html (um arquivo só, com tudo embutido).
O pywebview a exibe numa janela usando o WebView2, o mesmo componente do Edge
que já vem no Windows 10 e 11.

Como a página não precisa de servidor, ela é aberta direto do disco: nada fica
escutando na rede, nem mesmo em 127.0.0.1.

Roda no Python portátil que o instalar.bat coloca na pasta python, dentro da pasta do app: não precisa
de Python instalado no Windows.

Atualizações (mais abaixo, neste mesmo arquivo): ao abrir e a cada 15 minutos, consulta o repositório
público de versões; havendo versão nova, pergunta numa janela do Windows e só instala
se a pessoa confirmar. A página continua sem acesso à rede: quem baixa é este arquivo.

Uso:
    pythonw avulsoia.pyw              abre na janela própria
    pythonw avulsoia.pyw --navegador  abre no navegador padrão
    python  avulsoia.pyw --instalar   chamado pelo instalar.bat: baixa o resto do app e os componentes
                                      da janela e cria os atalhos
"""

import ctypes
import hashlib
import io
import json
import logging
import os
import re
import shutil
import signal
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import traceback
import urllib.request
import webbrowser
import zipfile
from html import escape
from pathlib import Path

TITLE = 'Avulso IA'
ROOT = Path(__file__).resolve().parent
PAGE = ROOT / 'AvulsoIA-editorPDF.html'
ICON = ROOT / 'avulsoia.ico'
LOG_FILE = ROOT / 'logs' / 'avulsoia.log'
# identidade própria no Windows: a barra de tarefas mostra o ícone do Avulso IA (e não o do Python)
APP_ID = 'RLAdev.AvulsoIA'
INTERVALO_ATUALIZACAO = 15 * 60   # segundos
# Versão da parte da JANELA deste arquivo (o que roda no processo que abre a janela: Janela, Trabalhador,
# Api, main) e da lista REQUISITOS. Aumente quando mudar qualquer uma delas: a janela aberta continua com o
# código antigo na memória: o trabalhador novo fecha e abre o app sozinho (reabrir_se_janela_antiga) e o popup avisa.
JANELA_VERSAO = 2
# Trabalhador que cai: reabre em 2 s, até 5 vezes em 10 minutos
QUEDAS_MAX, QUEDAS_JANELA_S, QUEDA_ESPERA_S = 5, 600, 2
# guarda as preferências da página (ex.: tema claro/escuro) entre uma abertura e outra
STORAGE_DIR = ROOT / 'dados-janela'

# Python portátil (python.org, "embeddable") em python\; os componentes da janela ficam no site-packages dele
PYTHON_DIR = ROOT / 'python'
SITE_PACKAGES = Path(sys.prefix) / 'Lib' / 'site-packages'
# só mexe nos componentes quando roda no Python portátil do app (não num Python de desenvolvimento)
GERENCIA_REQUISITOS = Path(sys.prefix).resolve() == PYTHON_DIR.resolve()

# Componentes da janela (pywebview e o que ele usa no Windows), baixados do PyPI com o SHA-256 fixo aqui.
# Mudou esta lista? Na próxima abertura o app reinstala os componentes sozinho.
PYPI = 'https://files.pythonhosted.org/packages/'
REQUISITOS = [
    ('pywebview-6.2.1-py3-none-any.whl', '3d/25/9491695c22c4842c5b3903b4dc172e0eecf67a27c0af34a71512c9b76a0a',
     '9d07275f53894ab4d5e2e0e996227193e7187dec276d9b624dccbce029216b46'),
    ('pythonnet-3.2.1-cp311.cp312.cp313.cp314.cp315-none-any.whl', 'd8/dc/c96a542079a69d3d091e91808fc8aaf9a0d5e2f8e73a63560e4379134bb6',
     'dd5668b74b0c903d9a24e1ba86f728fc490f8e919d56b3c24bf06739b9ee2b7f'),
    ('clr_loader-0.3.1-py3-none-any.whl', '5e/da/ec1a6e36624000b6df0dd61183c42342ee5814c073315e802cadaad04d2f',
     'cbad189de20d202a7d621956b0fc38049e13c9bf7ca2923441eff725cd121aa1'),
    ('cffi-2.1.1-cp314-cp314-win_amd64.whl', 'a7/06/1c3e01e3ba14c39f6d10bfbac52753b7e22259e38088e5cfe1d704918690',
     '3222ba5d678f80a030e6afbcc33dc1ae5cb45facabb61cee2c7016b8432fde48'),
    ('pycparser-3.11-py3-none-any.whl', '90/11/0e6f11117525ff0eec40ebac3d313376f102df93ca44ad9e893ee85e4f89',
     '51d5a8ba2be0bbe440b99d2112604c95bbbc3c2748a64260186c541e1729cd80'),
    ('bottle-0.13.4-py2.py3-none-any.whl', '83/f6/b55ec74cfe68c6584163faa311503c20b0da4c09883a41e8e00d6726c954',
     '045684fbd2764eac9cdeb824861d1551d113e8b683d8d26e296898d3dd99a12e'),
    ('typing_extensions-4.16.0-py3-none-any.whl', '49/d3/b8441a820a491ddfc024b0b0cf0393375b75ea13866d9c66727e54c2fc80',
     '481caa481374e813c1b176ada14e97f1f67a4539ce9cfeb3f350d78d6370c2e8'),
    # o PyPI não tem o proxy_tools pronto; é um arquivo de Python puro, tirado do pacote-fonte oficial
    ('proxy_tools-0.1.0.tar.gz', 'f2/cf/77d3e19b7fabd03895caca7857ef51e4c409e0ca6b37ee6e9f7daa50b642',
     'ccb3751f529c047e2d8a58440d86b205303cf0fe8146f784d1cbcd94f0a28010'),
]
MARCA_REQUISITOS = 'avulsoia-requisitos.txt'

WINDOW = dict(width=1400, height=900, min_size=(1000, 680), background_color='#f2f6f5')

# textos que o próprio pywebview mostra (ex.: janela "Salvar arquivo" dos downloads)
LOCALIZATION = {
    'global.quitConfirmation': 'Deseja mesmo sair?',
    'global.ok': 'OK',
    'global.quit': 'Sair',
    'global.cancel': 'Cancelar',
    'global.saveFile': 'Salvar arquivo',
    'windows.fileFilter.allFiles': 'Todos os arquivos',
    'windows.fileFilter.otherFiles': 'Outros tipos de arquivo',
}

log = logging.getLogger('avulsoia')


# ---------------------------------------------------------------------------------------------------------
# Atualização: consulta o atualizacao.json do repositório PÚBLICO de versões (rla-devv/avulsoIA-versoes),
# baixa a página nova e, se mudou, o ícone. Confere tamanho, SHA-256 e a versão escrita dentro da página
# ANTES de gravar qualquer coisa; grava em .novo e renomeia; guarda a página anterior em versoes-anteriores/.
# Só troca a página (AvulsoIA-editorPDF.html) e o ícone (avulsoia.ico): nunca código Python.
# Nada é enviado: só baixa os arquivos publicados.

BASE = 'https://raw.githubusercontent.com/rla-devv/avulsoIA-versoes/main/'
# só para os testes: aponta para servidores locais no lugar do GitHub e do PyPI
if os.environ.get('AVULSOIA_VERSOES_URL', '').startswith('http://127.0.0.1:'):
    BASE = os.environ['AVULSOIA_VERSOES_URL']
if os.environ.get('AVULSOIA_PYPI_URL', '').startswith('http://127.0.0.1:'):
    PYPI = os.environ['AVULSOIA_PYPI_URL']

PAGINA = 'AvulsoIA-editorPDF.html'
PROGRAMA = 'avulsoia.pyw'
ICONE = 'avulsoia.ico'
ANTERIORES = 'versoes-anteriores'
LISTA = 'arquivos-do-app.txt'   # o que a última instalação gravou (para remover o que sair do pacote)
# nunca são tocados pela atualização
PROTEGIDOS = {'python', '.venv', 'logs', 'dados-janela', ANTERIORES, LISTA, 'instalar.bat'}

VERSAO = r'\d+(?:\.\d+){1,3}'
_PARTES = r'[A-Za-z0-9][A-Za-z0-9_.-]*(?:/[A-Za-z0-9][A-Za-z0-9_.-]*)*'   # sem "..", sem "/" no começo
RE_CAMINHO = re.compile(_PARTES)
RE_ORIGEM = re.compile(rf'(?:versoes|programa/{VERSAO})/{_PARTES}')
RE_VERSAO_PAGINA = re.compile(rf"const APP_VERSION = '({VERSAO})'")
RE_SHA = re.compile(r'[0-9a-f]{64}')
LIMITE_ARQUIVO = 50 * 1024 * 1024
LIMITE_PACOTE = 20 * 1024 * 1024


class ErroAtualizacao(Exception):
    pass


def ver(v):
    return tuple(int(x) for x in v.split('.'))


def sha(dados):
    return hashlib.sha256(dados).hexdigest()


def versao_instalada(app):
    try:
        texto = (Path(app) / PAGINA).read_text(encoding='utf-8', errors='replace')
    except OSError:
        return '0.0.0'
    m = RE_VERSAO_PAGINA.search(texto)
    return m.group(1) if m else '0.0.0'


def _baixar_url(url, limite):
    req = urllib.request.Request(url, headers={'User-Agent': 'AvulsoIA-janela', 'Cache-Control': 'no-cache'})
    with urllib.request.urlopen(req, timeout=30) as r:
        dados = r.read(limite + 1)
    if len(dados) > limite:
        raise ErroAtualizacao(f'{url.rsplit("/", 1)[-1]} é maior que o permitido')
    return dados


def _baixar(caminho, limite):
    return _baixar_url(BASE + caminho, limite)


def caminho_valido(c):
    return isinstance(c, str) and bool(RE_CAMINHO.fullmatch(c)) and c.split('/')[0].lower() not in PROTEGIDOS


def _arquivo_valido(a):
    return (isinstance(a, dict) and caminho_valido(a.get('caminho'))
            and isinstance(a.get('origem'), str) and RE_ORIGEM.fullmatch(a['origem'])
            and isinstance(a.get('sha256'), str) and RE_SHA.fullmatch(a['sha256'])
            and isinstance(a.get('tamanho'), int) and 0 < a['tamanho'] <= LIMITE_ARQUIVO)


def consultar():
    """Lê o atualizacao.json publicado e confere o formato. Levanta erro se algo estiver estranho."""
    try:
        m = json.loads(_baixar(f'atualizacao.json?t={int(time.time())}', 256 * 1024))
    except (OSError, ValueError) as e:
        raise ErroAtualizacao(f'não foi possível consultar as versões ({e})') from e
    arquivos = m.get('arquivos') if isinstance(m, dict) else None
    if not (isinstance(m, dict) and isinstance(m.get('versao'), str) and re.fullmatch(VERSAO, m['versao'])
            and isinstance(m.get('novidades', []), list) and all(isinstance(n, str) for n in m.get('novidades', []))
            and isinstance(arquivos, list) and arquivos and all(_arquivo_valido(a) for a in arquivos)):
        raise ErroAtualizacao('o aviso de versão publicado está com formato inesperado')
    caminhos = [a['caminho'] for a in arquivos]
    if len(set(c.lower() for c in caminhos)) != len(caminhos) or PAGINA not in caminhos or PROGRAMA not in caminhos:
        raise ErroAtualizacao('a lista de arquivos publicada está incompleta')
    return m


def ha_versao_nova(m, app):
    return ver(m['versao']) > ver(versao_instalada(app))


def precisa_instalar(m, app):
    # versão nova ou algum arquivo do pacote faltando (ex.: primeira instalação)
    return ha_versao_nova(m, app) or any(not (Path(app) / a['caminho']).is_file() for a in m['arquivos'])


def _conferir(nome, dados, info):
    if len(dados) != info['tamanho']:
        raise ErroAtualizacao(f'{nome}: tamanho diferente do publicado')
    if sha(dados) != info['sha256']:
        raise ErroAtualizacao(f'{nome}: conteúdo diferente do publicado (SHA-256)')


def _ler_lista(app):
    try:
        linhas = (Path(app) / LISTA).read_text(encoding='utf-8').splitlines()
    except OSError:
        return []
    return [c for c in linhas if caminho_valido(c)]


def instalar(m, app):
    """Baixa e confere todos os arquivos; só então troca. Qualquer falha desfaz tudo.

    Devolve {'versao': ..., 'programa': True se mudou código Python (o app precisa reabrir)}."""
    app = Path(app)
    v = m['versao']
    novos = {}
    for a in m['arquivos']:
        destino = app / a['caminho']
        if destino.is_file() and sha(destino.read_bytes()) == a['sha256']:
            continue   # igual ao publicado: não baixa nem regrava
        dados = _baixar(a['origem'], a['tamanho'])
        _conferir(a['caminho'], dados, a)
        novos[a['caminho']] = dados

    pagina = novos.get(PAGINA) or (app / PAGINA).read_bytes()
    texto = pagina.decode('utf-8', errors='replace')
    if (not texto.lower().startswith('<!doctype html>')
            or f'<span id="app-version">{v}</span>' not in texto
            or f"const APP_VERSION = '{v}'" not in texto):
        raise ErroAtualizacao('a página baixada não é a versão anunciada')
    if ICONE in novos and not novos[ICONE].startswith(b'\x00\x00\x01\x00'):
        raise ErroAtualizacao('o ícone baixado não é um arquivo .ico')

    listados = [a['caminho'] for a in m['arquivos']]
    sair = [c for c in _ler_lista(app) if c not in listados and (app / c).is_file()]

    # tudo conferido. 1) guarda o que vai ser trocado ou removido; 2) grava em .novo; 3) troca
    copia = app / ANTERIORES / versao_instalada(app)
    for c in [*novos, *sair]:
        if (app / c).is_file():
            (copia / c).parent.mkdir(parents=True, exist_ok=True)
            # cópia byte a byte: o shutil.copy2 do Python 3.14 no Windows usa o CopyFile2, que falhou no teste
            (copia / c).write_bytes((app / c).read_bytes())
    feitos = []
    try:
        for c, dados in novos.items():
            (app / c).parent.mkdir(parents=True, exist_ok=True)
            (app / (c + '.novo')).write_bytes(dados)
        for c in novos:
            os.replace(app / (c + '.novo'), app / c)   # troca de uma vez: nunca fica um arquivo pela metade
            feitos.append(c)
        for c in sair:
            (app / c).unlink()
            feitos.append(c)
            pasta = (app / c).parent
            while pasta != app and not any(pasta.iterdir()):
                pasta.rmdir()
                pasta = pasta.parent
        (app / LISTA).write_text('\n'.join(listados) + '\n', encoding='utf-8')
    except OSError as e:
        for c in feitos:
            if (copia / c).is_file():
                (app / c).parent.mkdir(parents=True, exist_ok=True)
                (app / c).write_bytes((copia / c).read_bytes())
            else:
                (app / c).unlink(missing_ok=True)
        for c in novos:
            (app / (c + '.novo')).unlink(missing_ok=True)
        raise ErroAtualizacao(f'não foi possível trocar os arquivos ({e})') from e
    return {'versao': v, 'programa': any(c.endswith(('.py', '.pyw')) for c in novos)}


# --- componentes da janela (pywebview), no site-packages do Python portátil ---

def _assinatura_requisitos():
    return sha(json.dumps(REQUISITOS).encode())


def requisitos_ok():
    try:
        return (SITE_PACKAGES / MARCA_REQUISITOS).read_text(encoding='utf-8').strip() == _assinatura_requisitos()
    except OSError:
        return False


def _extrair(pasta, nome, dados):
    partes = nome.split('/')
    if not nome or nome.startswith('/') or '\\' in nome or ':' in nome or any(p in ('', '.', '..') for p in partes):
        raise ErroAtualizacao(f'pacote com caminho inesperado: {nome}')
    destino = pasta.joinpath(*partes)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(dados)


def instalar_requisitos():
    """Baixa e confere todos os pacotes; monta um site-packages novo e só então troca pelo atual."""
    baixados = []
    for arquivo, caminho, sha256 in REQUISITOS:
        dados = _baixar_url(f'{PYPI}{caminho}/{arquivo}', LIMITE_PACOTE)
        if sha(dados) != sha256:
            raise ErroAtualizacao(f'{arquivo}: conteúdo diferente do publicado (SHA-256)')
        baixados.append((arquivo, dados))
    novo = SITE_PACKAGES.with_name('site-packages.novo')
    antigo = SITE_PACKAGES.with_name('site-packages.antigo')
    for p in (novo, antigo):
        shutil.rmtree(p, ignore_errors=True)
    novo.mkdir(parents=True)
    for arquivo, dados in baixados:
        if arquivo.endswith('.whl'):
            with zipfile.ZipFile(io.BytesIO(dados)) as z:
                for nome in z.namelist():
                    # a pasta .data de um pacote só tem scripts de linha de comando, que o app não usa
                    if not nome.endswith('/') and not nome.split('/')[0].endswith('.data'):
                        _extrair(novo, nome, z.read(nome))
        else:
            raiz = arquivo[:-len('.tar.gz')] + '/'
            pacote = raiz + arquivo.split('-')[0] + '/'
            with tarfile.open(fileobj=io.BytesIO(dados), mode='r:gz') as t:
                for membro in t.getmembers():
                    if membro.isfile() and membro.name.startswith(pacote):
                        _extrair(novo, membro.name[len(raiz):], t.extractfile(membro).read())
    (novo / MARCA_REQUISITOS).write_text(_assinatura_requisitos(), encoding='utf-8')
    if SITE_PACKAGES.exists():
        os.replace(SITE_PACKAGES, antigo)
    os.replace(novo, SITE_PACKAGES)
    shutil.rmtree(antigo, ignore_errors=True)


# atalho dentro da pasta do app, com nome que diz o que é: quem abrir a pasta sabe em que clicar
ATALHO_NA_PASTA = 'Abrir Avulso IA.lnk'
# nomes que esse atalho já teve: saem depois que o novo existe
ATALHOS_ANTIGOS_NA_PASTA = ['Abrir o Avulso IA.lnk']
ATALHOS_PS1 = r"""
$ErrorActionPreference = 'Stop'
$shell = New-Object -ComObject WScript.Shell
$lugares = @(, (Join-Path $env:AVULSOIA_PASTA $env:AVULSOIA_ATALHO_NA_PASTA))
if ($env:AVULSOIA_SO_PASTA -ne '1') {
  $lugares += (Join-Path ([Environment]::GetFolderPath('Desktop')) 'Avulso IA.lnk')
  $lugares += (Join-Path ([Environment]::GetFolderPath('Programs')) 'Avulso IA.lnk')
}
foreach ($lugar in $lugares) {
  $atalho = $shell.CreateShortcut($lugar)
  $atalho.TargetPath = $env:AVULSOIA_ALVO
  $atalho.Arguments = '"' + $env:AVULSOIA_PROGRAMA + '"'
  $atalho.WorkingDirectory = $env:AVULSOIA_PASTA
  $atalho.IconLocation = $env:AVULSOIA_ICONE
  $atalho.Description = 'Avulso IA - edicao, organizacao e conversao de PDFs'
  $atalho.Save()
}
"""


def criar_atalhos(so_pasta=False):
    """Atalho "Abrir Avulso IA" na pasta do app e "Avulso IA" na Área de Trabalho e no Menu Iniciar
    (caminhos por variável de ambiente: pastas com acento). so_pasta: só o da pasta do app."""
    if sys.platform != 'win32':
        return
    with tempfile.TemporaryDirectory() as tmp:
        script = Path(tmp) / 'atalhos.ps1'
        script.write_text(ATALHOS_PS1, encoding='ascii')
        env = dict(os.environ, AVULSOIA_ALVO=str(PYTHON_DIR / 'pythonw.exe'), AVULSOIA_PROGRAMA=str(ROOT / PROGRAMA),
                   AVULSOIA_PASTA=str(ROOT), AVULSOIA_ICONE=str(ICON), AVULSOIA_ATALHO_NA_PASTA=ATALHO_NA_PASTA,
                   AVULSOIA_SO_PASTA='1' if so_pasta else '0')
        subprocess.run(['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(script)],
                       env=env, check=True, capture_output=True, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))


def apagar_atalhos_antigos():
    """Apaga o atalho da pasta com nome antigo, só depois que o de nome novo existe."""
    if not (ROOT / ATALHO_NA_PASTA).exists():
        return
    for nome in ATALHOS_ANTIGOS_NA_PASTA:
        (ROOT / nome).unlink(missing_ok=True)


def instalar_app():
    """--instalar (chamado pelo instalar.bat): baixa o resto do app e os componentes da janela e cria os atalhos."""
    try:
        m = consultar()
        if precisa_instalar(m, ROOT):
            print(f' Baixando o Avulso IA {m["versao"]}...')
            if instalar(m, ROOT)['programa'] and not os.environ.get('AVULSOIA_REINSTALOU'):
                # veio um avulsoia.pyw mais novo: ele continua a instalação
                env = dict(os.environ, AVULSOIA_REINSTALOU='1')
                return subprocess.call([sys.executable, str(ROOT / PROGRAMA), '--instalar'], env=env)
        if GERENCIA_REQUISITOS and not requisitos_ok():
            print(' Baixando os componentes do programa...')
            instalar_requisitos()
        print(' Criando os atalhos (na pasta do app, na Área de Trabalho e no Menu Iniciar)...')
        criar_atalhos()
        apagar_atalhos_antigos()
    except (ErroAtualizacao, OSError, subprocess.CalledProcessError) as e:
        log.exception('Instalação não terminou')
        print(f' Não consegui terminar a instalação: {e}')
        return 1
    return 0


def setup_logging():
    LOG_FILE.parent.mkdir(exist_ok=True)
    logging.basicConfig(
        filename=LOG_FILE,
        level=logging.INFO,
        format='%(asctime)s %(levelname)s %(name)s: %(message)s',
        encoding='utf-8',
    )
    # o pythonw.exe não tem console: sem isso, qualquer print derrubaria o app
    if sys.stdout is None or sys.stderr is None:
        stream = open(LOG_FILE, 'a', encoding='utf-8', buffering=1)
        sys.stdout = sys.stdout or stream
        sys.stderr = sys.stderr or stream


def open_in_browser():
    log.info('Abrindo no navegador padrão: %s', PAGE)
    webbrowser.open(PAGE.as_uri())


def error_page(title, detail):
    return f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><title>Avulso IA</title>
<style>
body{{margin:0;min-height:100vh;display:grid;place-items:center;background:#f2f6f5;color:#102022;
font:15px/1.6 "Segoe UI",system-ui,sans-serif}}
.box{{max-width:620px;background:#fff;border:1px solid #d9e3e1;border-radius:20px;padding:34px 36px;
box-shadow:0 6px 20px rgba(16,40,34,.08)}}
.logo{{width:44px;height:44px;border-radius:12px;background:#0c7a70;color:#fff;display:grid;place-items:center;
font-weight:800;margin-bottom:16px}}
h1{{margin:0 0 8px;font-size:22px}} p{{margin:0 0 10px;color:#5a6b6d}}
pre{{white-space:pre-wrap;background:#f2f6f5;border-radius:10px;padding:12px;font-size:12.5px;color:#5a6b6d;max-height:220px;overflow:auto}}
</style></head><body><div class="box"><div class="logo">A</div>
<h1>{escape(title)}</h1>
<p>Se o problema continuar, reinstale o Avulso IA pelo <b>instalar.bat</b>.</p>
<p>Detalhes técnicos (também salvos em <b>logs\\avulsoia.log</b>):</p>
<pre>{escape(detail)}</pre></div></body></html>"""


def identidade_windows():
    if sys.platform != 'win32':
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
    except Exception:
        log.exception('Não foi possível definir a identidade do app no Windows')


def recarregar_icones_do_windows():
    # o ícone do atalho pode ter mudado com a atualização; avisa o Windows para redesenhar
    if sys.platform != 'win32':
        return
    try:
        ctypes.windll.shell32.SHChangeNotify(0x08000000, 0, None, None)   # SHCNE_ASSOCCHANGED
    except Exception:
        log.exception('Não foi possível recarregar os ícones')


def pagina_espera(texto, detalhe=''):
    """Página mostrada na própria janela enquanto o trabalhador reinicia (nas cores do app)."""
    return f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><title>Avulso IA</title>
<style>
:root{{--bg:#f2f6f5;--surface:#fff;--ink:#102022;--muted:#5a6b6d;--line:#d9e3e1;--accent:#0c7a70;--soft:#e0f2ef}}
@media (prefers-color-scheme:dark){{:root{{--bg:#0c1315;--surface:#141d20;--ink:#e5eeed;--muted:#92a5a6;--line:#263436;--accent:#45cfbe;--soft:#15302d}}}}
body{{margin:0;min-height:100vh;display:grid;place-items:center;background:var(--bg);color:var(--ink);font:15px/1.5 "Segoe UI",system-ui,sans-serif}}
.box{{text-align:center;background:var(--surface);border:1px solid var(--line);border-radius:16px;padding:34px 44px;max-width:520px}}
.logo{{width:44px;height:44px;border-radius:12px;background:var(--accent);color:var(--surface);display:grid;place-items:center;font-weight:800;margin:0 auto 10px}}
.nome{{font-weight:750;font-size:18px}} .frase{{color:var(--muted);font-size:13px;margin-bottom:22px}}
.giro{{width:38px;height:38px;border-radius:50%;border:4px solid var(--soft);border-top-color:var(--accent);margin:0 auto 14px;animation:g .8s linear infinite}}
@keyframes g{{to{{transform:rotate(360deg)}}}} @media (prefers-reduced-motion:reduce){{.giro{{animation:none}}}}
.det{{color:var(--muted);font-size:13px;margin-top:4px}}
</style></head><body><div class="box"><div class="logo">A</div><div class="nome">Avulso IA</div>
<div class="frase">Edição, organização e conversão de PDFs diretamente no seu computador.</div>
<div class="giro"></div><b>{escape(texto)}</b><div class="det">{escape(detalhe)}</div></div></body></html>"""


# --- trabalhador: a lógica de atualização, num processo filho (fala por stdin/stdout, uma linha JSON) ---

def processo_vivo(pid):
    if sys.platform == 'win32':
        # no Windows, os.kill(pid, 0) encerraria o processo: pergunta pelo identificador dele
        k = ctypes.windll.kernel32
        h = k.OpenProcess(0x00100000, False, pid)   # SYNCHRONIZE
        if not h:
            return False
        vivo = k.WaitForSingleObject(h, 0) == 0x102   # WAIT_TIMEOUT: ainda rodando
        k.CloseHandle(h)
        return vivo
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def reabrir_se_janela_antiga(janela_aberta):
    """A atualização trouxe uma parte da janela nova (JANELA_VERSAO maior que a da janela aberta): este trabalhador
    novo fecha a janela antiga e abre o app de novo, sozinho, para a pessoa não ter de fazer isso. A janela antiga
    está na tela "Aplicando a atualização…", esperando este trabalhador. Fecha primeiro e só então abre (no Windows
    os componentes da janela ficam presos enquanto ela está aberta)."""
    if not janela_aberta or janela_aberta >= JANELA_VERSAO:
        return False
    pid = int(os.environ.get('AVULSOIA_JANELA_PID') or os.getppid())
    log.info('Parte da janela atualizada (%s -> %s): reabrindo o Avulso IA sozinho', janela_aberta, JANELA_VERSAO)
    try:
        os.kill(pid, signal.SIGTERM)   # no Windows: TerminateProcess
    except OSError:
        log.exception('Não foi possível fechar a janela antiga')
    for _ in range(100):
        if not processo_vivo(pid):
            break
        time.sleep(0.1)
    cmd = json.loads(os.environ['AVULSOIA_REABRIR_COM']) if os.environ.get('AVULSOIA_REABRIR_COM') else [sys.executable, str(ROOT / PROGRAMA)]
    flags = getattr(subprocess, 'DETACHED_PROCESS', 0) | getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0)
    subprocess.Popen(cmd, cwd=str(ROOT), creationflags=flags, close_fds=True,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return True


def trabalhador():
    """--trabalhador: recebe pedidos da janela pela entrada padrão e responde pela saída padrão.

    Pedidos: {"id": n, "pedido": "verificar" | "instalar" | "ping"}; respostas: {"id": n, "resposta": {...}}.
    Avisos sem pedido: {"evento": "pronto", ...} ao começar e {"evento": "nova_versao", ...} quando a consulta
    automática (ao abrir e a cada 15 min) acha versão nova. Nada vai para a rede além do repositório de versões."""
    saida = sys.stdout
    trava_saida, trava = threading.Lock(), threading.Lock()
    janela_aberta = int(os.environ.get('AVULSOIA_JANELA', '0') or 0)   # JANELA_VERSAO do processo da janela

    def enviar(msg):
        with trava_saida:
            saida.write(json.dumps(msg, ensure_ascii=False) + '\n')
            saida.flush()

    def info(m):
        # reabrir: a versão nova muda a parte da janela (ou os componentes), que só troca fechando o app
        return {'versao': m['versao'], 'atual': versao_instalada(ROOT), 'novidades': m.get('novidades', []),
                'reabrir': int(m.get('janela', 0) or 0) > janela_aberta}

    def verificar():
        with trava:
            try:
                m = consultar()
            except ErroAtualizacao as e:
                log.warning('Consulta de atualização: %s', e)
                return {'estado': 'erro', 'mensagem': 'Não foi possível verificar agora. Confira a conexão com a internet.'}
            if not ha_versao_nova(m, ROOT):
                return {'estado': 'atual', 'versao': versao_instalada(ROOT)}
            return {'estado': 'disponivel', **info(m)}

    def instalar_agora():
        with trava:
            try:
                m = consultar()
            except ErroAtualizacao as e:
                log.warning('Consulta de atualização: %s', e)
                return {'estado': 'erro', 'mensagem': 'Não foi possível atualizar agora. Confira a conexão com a internet.'}
            atual = versao_instalada(ROOT)
            if not ha_versao_nova(m, ROOT):
                return {'estado': 'atual', 'versao': atual}
            try:
                r = instalar(m, ROOT)
            except (ErroAtualizacao, OSError) as e:
                log.exception('Atualização para %s não instalada', m['versao'])
                return {'estado': 'erro', 'mensagem': f'A atualização não foi instalada ({e}). Nada foi alterado.'}
            log.info('Atualizado de %s para %s', atual, m['versao'])
            return {'estado': 'instalada', 'versao': m['versao'], 'programa': r['programa'], 'reabrir': info(m)['reabrir']}

    def consulta_automatica():
        time.sleep(5)   # deixa a janela abrir antes da primeira consulta
        while True:
            r = verificar()
            if r['estado'] == 'disponivel':
                enviar({'evento': 'nova_versao', **r})
            time.sleep(INTERVALO_ATUALIZACAO)

    pedidos = {'verificar': verificar, 'instalar': instalar_agora, 'ping': lambda: {'ok': True}}
    if reabrir_se_janela_antiga(janela_aberta):
        return
    enviar({'evento': 'pronto', 'versao': versao_instalada(ROOT), 'janela': JANELA_VERSAO})
    if os.environ.get('AVULSOIA_SEM_CONSULTA') != '1':
        threading.Thread(target=consulta_automatica, daemon=True).start()
    for linha in sys.stdin:   # termina quando a janela fecha a entrada (ou encerra o processo)
        try:
            msg = json.loads(linha)
            pedido = pedidos.get(msg.get('pedido'))
            resposta = pedido() if pedido else {'estado': 'erro', 'mensagem': 'pedido desconhecido'}
        except Exception as e:
            log.exception('Pedido não atendido')
            msg, resposta = (msg if isinstance(msg, dict) else {}), {'estado': 'erro', 'mensagem': str(e)}
        if 'id' in msg:
            enviar({'id': msg['id'], 'resposta': resposta})


class Trabalhador:
    """No processo da janela: inicia, vigia e conversa com o trabalhador. Nunca fecha a janela."""

    def __init__(self, ao_evento, ao_desistir):
        self.ao_evento, self.ao_desistir = ao_evento, ao_desistir
        self.proc = None
        self.info = {}
        self.pronto = threading.Event()
        self.trava = threading.Lock()
        self.respostas = {}
        self.seq = 0
        self.quedas = []
        self.ativo = False   # falso depois de parar(): uma saída do processo não conta como queda

    def iniciar(self):
        self.ativo = True
        self.pronto.clear()
        LOG_FILE.parent.mkdir(exist_ok=True)
        erros = open(LOG_FILE, 'a', encoding='utf-8')   # o que o trabalhador escrever de erro vai para o log
        env = dict(os.environ, AVULSOIA_JANELA=str(JANELA_VERSAO), AVULSOIA_JANELA_PID=str(os.getpid()), PYTHONIOENCODING='utf-8')
        proc = subprocess.Popen([sys.executable, str(ROOT / PROGRAMA), '--trabalhador'], cwd=str(ROOT), env=env,
                                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=erros, text=True,
                                encoding='utf-8', bufsize=1, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        erros.close()
        self.proc = proc
        threading.Thread(target=self._ler, args=(proc,), daemon=True).start()
        log.info('Trabalhador iniciado (processo %s)', proc.pid)

    def _ler(self, proc):
        for linha in proc.stdout:
            try:
                msg = json.loads(linha)
            except ValueError:
                continue
            if 'id' in msg:
                espera = self.respostas.get(msg['id'])
                if espera:
                    espera[1] = msg.get('resposta')
                    espera[0].set()
            elif msg.get('evento') == 'pronto':
                self.info = msg
                self.pronto.set()
            else:
                try:
                    self.ao_evento(msg)
                except Exception:
                    log.exception('Aviso do trabalhador não tratado')
        codigo = proc.wait()
        for espera in list(self.respostas.values()):   # quem esperava resposta não fica preso
            espera[0].set()
        if proc is self.proc and self.ativo:
            self._caiu(codigo)

    def _caiu(self, codigo):
        agora = time.monotonic()
        self.quedas = [t for t in self.quedas if agora - t < QUEDAS_JANELA_S]
        log.warning('O trabalhador parou inesperadamente (código %s)', codigo)
        if len(self.quedas) >= QUEDAS_MAX:
            log.error('O trabalhador caiu %s vezes em %s s; desisti de reabrir', QUEDAS_MAX, QUEDAS_JANELA_S)
            self.ao_desistir()
            return
        self.quedas.append(agora)
        time.sleep(QUEDA_ESPERA_S)
        if self.ativo:
            self.iniciar()

    def pedir(self, pedido, espera_s=180):
        if not self.pronto.wait(60):
            return {'estado': 'erro', 'mensagem': 'O Avulso IA ainda está abrindo. Tente de novo em instantes.'}
        with self.trava:
            self.seq += 1
            n = self.seq
            evento = threading.Event()
            self.respostas[n] = [evento, None]
            try:
                self.proc.stdin.write(json.dumps({'id': n, 'pedido': pedido}) + '\n')
                self.proc.stdin.flush()
            except (OSError, ValueError, AttributeError):
                evento.set()
        evento.wait(espera_s)
        resposta = self.respostas.pop(n, [None, None])[1]
        return resposta or {'estado': 'erro', 'mensagem': 'Não foi possível verificar agora. Tente de novo em instantes.'}

    def parar(self, *_):
        self.ativo = False
        proc = self.proc
        if proc and proc.poll() is None:
            try:
                proc.stdin.close()
            except OSError:
                pass
            proc.terminate()
            try:
                proc.wait(5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(5)

    def reiniciar(self):
        self.parar()
        self.iniciar()
        return self.pronto.wait(60)


class Janela:
    """Processo da janela: pequeno e quase nunca muda. É o único que cria a janela do pywebview; as
    atualizações acontecem no trabalhador, e a janela só recarrega a página (nunca fecha)."""

    def __init__(self):
        self.janela = None
        self.adiada = None   # versão que a pessoa deixou para depois (não pergunta de novo sozinho)
        self.trabalhador = Trabalhador(self.ao_evento, self.ao_desistir)

    def _js(self, codigo):
        try:
            return self.janela.evaluate_js(codigo)
        except Exception:
            return None

    def ocupada(self):
        return bool(self._js('!!(window.avulsoOcupado && window.avulsoOcupado())'))

    def botao_na_pagina(self):
        # o botão só aparece quando a ponte página → programa funciona
        return self._js('!!(window.avulsoNovaVersao && !document.getElementById("updateBtn").hidden)') is True

    def marcar_app(self, *_):
        # a página é a mesma do navegador: avisa que está no app instalado ("no seu computador")
        self._js('window.__AVULSO_APP = true; window.avulsoModoApp && window.avulsoModoApp()')

    def avisar(self, titulo, texto):
        self._js(f'window.avulsoAviso && window.avulsoAviso({json.dumps(titulo)}, {json.dumps(texto)})')

    def ao_evento(self, msg):
        if msg.get('evento') == 'nova_versao':
            self.nova_versao(msg)

    def ao_desistir(self):
        self.janela.load_html(error_page('O Avulso IA parou de responder',
                                         f'A parte que busca atualizações caiu várias vezes. Feche e abra o app.\nLog: {LOG_FILE}'))

    def _perguntar(self, info):
        """Sem o botão na página (a ponte não funcionou): pergunta numa janela do Windows, como antes."""
        novidades = '\n'.join('• ' + n for n in info.get('novidades', []))
        reabrir = '\n\nPara concluir, o Avulso IA vai fechar e abrir sozinho uma vez.' if info.get('reabrir') else ''
        return self.janela.create_confirmation_dialog(
            'Avulso IA - atualização disponível',
            f'A versão {info["versao"]} está disponível (você usa a {info["atual"]}).\n\n{novidades}\n\n'
            f'Atualizar agora? O Avulso IA vai recarregar a tela; termine antes o que estiver fazendo.{reabrir}')

    def nova_versao(self, info):
        # padrão RLA.dev: a consulta automática não abre nada, só troca o botão para "Nova versão X"
        if self.botao_na_pagina():
            self._js(f'window.avulsoNovaVersao({json.dumps({k: info[k] for k in ("versao", "atual", "novidades", "reabrir")})})')
            return
        if self.adiada == info['versao'] or self.ocupada():
            return
        if self._perguntar(info):
            self.aplicar(self.trabalhador.pedir('instalar'))
        else:
            self.adiada = info['versao']

    def verificar(self, manual=True):
        r = self.trabalhador.pedir('verificar')
        if r.get('estado') != 'disponivel' or self.botao_na_pagina():
            return r   # a página mostra o resultado (ou o popup de novidades)
        if not self._perguntar(r):
            self.adiada = r['versao']
            return {'estado': 'adiada', 'versao': r['versao']}
        return self.aplicar(self.trabalhador.pedir('instalar'))

    def atualizar_agora(self):
        return self.aplicar(self.trabalhador.pedir('instalar'))

    def aplicar(self, r):
        """Depois que o trabalhador instalou: recarrega a página e, se mudou código Python, reinicia só o
        trabalhador (com a página de espera na mesma janela). A janela nunca fecha."""
        if r.get('estado') != 'instalada':
            return r
        recarregar_icones_do_windows()
        if r.get('programa'):
            self.janela.load_html(pagina_espera('Aplicando a atualização…', 'Isso leva só alguns segundos.'))
            if not self.trabalhador.reiniciar():
                log.error('O trabalhador novo não respondeu depois da atualização')
        # ?t= novo a cada vez: o WebView2 ignora load_url para o endereço que já está aberto (na 1.5.0 a página não
        # recarregava e o botão ficava esperando)
        self.janela.load_url(f'{PAGE.as_uri()}?t={int(time.time() * 1000)}')
        if r.get('reabrir'):
            threading.Timer(2.0, self.avisar, ('Feche e abra o Avulso IA uma vez',
                            'A atualização foi instalada. Para concluir, feche o Avulso IA e abra de novo quando puder.')).start()
        return r

    def rodar(self, janela):
        self.janela = janela
        eventos = getattr(janela, 'events', None)
        if eventos is not None:
            eventos.loaded += self.marcar_app   # também depois de recarregar a página
            eventos.closed += self.trabalhador.parar
        self.marcar_app()
        self.trabalhador.iniciar()


class Api:
    """Funções que a página pode chamar: só repassam ao trabalhador (pela Janela) e devolvem a resposta."""

    def __init__(self, janela):
        self._janela = janela

    def buscar_atualizacao(self):
        r = self._janela.verificar()
        log.info('Busca de atualização pelo botão: %s', r.get('estado'))   # ajuda a entender relatos de "não aconteceu nada"
        return r

    def atualizar_agora(self):
        return self._janela.atualizar_agora()

    def adiar(self, versao):
        self._janela.adiada = str(versao)
        return True


def main():
    setup_logging()
    log.info('Iniciando o Avulso IA (%s)', ' '.join(sys.argv[1:]) or 'janela')

    if '--instalar' in sys.argv:
        sys.exit(instalar_app())

    if '--trabalhador' in sys.argv:
        trabalhador()
        return

    if '--navegador' in sys.argv:
        open_in_browser()
        return

    if GERENCIA_REQUISITOS:
        # instalação de antes deste atalho (ou do nome atual dele) existir: cria só o da pasta
        try:
            if not (ROOT / ATALHO_NA_PASTA).exists():
                criar_atalhos(so_pasta=True)
            apagar_atalhos_antigos()
        except Exception:
            log.exception('Não foi possível criar o atalho na pasta do app')

    if GERENCIA_REQUISITOS and not requisitos_ok():
        # primeira abertura depois de uma atualização que mudou os componentes da janela
        try:
            instalar_requisitos()
        except Exception:
            log.exception('Não foi possível instalar os componentes da janela')

    try:
        import webview
    except ImportError:
        log.warning('pywebview não está instalado; usando o navegador')
        open_in_browser()
        return

    webview.settings['ALLOW_DOWNLOADS'] = True  # botão "Baixar" abre a janela "Salvar arquivo"
    webview.settings['OPEN_EXTERNAL_LINKS_IN_BROWSER'] = True  # ex.: link de doação

    identidade_windows()
    atualizador = Janela()
    if PAGE.exists():
        # file:// em vez de caminho simples: assim o pywebview não sobe o servidor interno
        janela = webview.create_window(TITLE, url=PAGE.as_uri(), text_select=True, js_api=Api(atualizador), **WINDOW)
    else:
        janela = None
        log.error('Página não encontrada: %s', PAGE)
        webview.create_window(
            TITLE,
            html=error_page('Não encontrei a página do Avulso IA', f'Arquivo esperado:\n{PAGE}'),
            **WINDOW,
        )

    STORAGE_DIR.mkdir(exist_ok=True)
    try:
        webview.start(
            atualizador.rodar if janela else None,
            (janela,) if janela else None,
            private_mode=False,
            storage_path=str(STORAGE_DIR),
            icon=str(ICON) if ICON.exists() else None,
            localization=LOCALIZATION,
        )
    except Exception:
        # ex.: WebView2 ausente ou danificado; o navegador ainda funciona
        log.exception('Não foi possível abrir a janela; usando o navegador')
        open_in_browser()
    finally:
        atualizador.trabalhador.parar()   # janela fechada: nenhum processo fica rodando


if __name__ == '__main__':
    try:
        main()
    except Exception:
        log.critical('Erro inesperado:\n%s', traceback.format_exc())
        raise
