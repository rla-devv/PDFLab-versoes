# Avulso IA — versões

Páginas prontas do Avulso IA (edição, organização e conversão de arquivos PDF que roda no computador,
sem internet). Desenvolvido por RLA.dev.

- `AvulsoIA.zip` — o Avulso IA em janela própria no Windows, para instalar pela primeira vez: tem um
  arquivo só. Descompacte e dê dois cliques em `instalar.bat`. Não precisa de Python no computador: ele baixa
  um Python portátil (fica só na pasta do app) e a versão mais nova do Avulso IA, confere cada arquivo, cria o
  atalho “Avulso IA” na Área de Trabalho e no Menu Iniciar e abre o app. (`AvulsoIA-janela.zip` é o mesmo
  pacote, no link antigo.)
- `versoes/AvulsoIA-X.Y.Z.html` — cada versão publicada. Para usar sem instalar, baixe o arquivo e abra
  no Google Chrome ou no Microsoft Edge. Para voltar a uma versão anterior, é só abrir o arquivo dela.
- `programa/X.Y.Z/` — os arquivos do programa da janela (`avulsoia.pyw`, `avulsoia.ico`) que mudaram naquela versão.
- `atualizacao.json` — a versão mais recente: número, novidades e, para cada arquivo do app, caminho, origem,
  SHA-256 e tamanho (o instalador e o próprio app conferem tudo antes de gravar).

Nenhum PDF é enviado para a internet: tudo roda no seu computador.

**Apoie o projeto:** https://link.mercadopago.com.br/rladevapps

Este repositório guarda só as versões prontas, geradas pelo `publicar.py` do código-fonte.
