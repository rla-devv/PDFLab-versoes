# PDF Lab — versões

Páginas prontas do PDF Lab (antes chamado Avulso IA): edição, organização e conversão de arquivos PDF que roda no
computador, sem enviar nada para a internet.

- `PDFLab.zip` — o PDF Lab no Windows, para instalar pela primeira vez: tem o `Instalar PDF Lab.bat`, que
  instala sempre numa pasta “PDF Lab” (mesmo aberto de dentro do zip), baixa um Python portátil (fica só na pasta do app) e a versão mais nova do PDF Lab, confere cada arquivo, cria o
  atalho “PDF Lab” na Área de Trabalho e no Menu Iniciar e abre o app. (`AvulsoIA.zip` e `AvulsoIA-janela.zip` são o
  mesmo pacote, nos links antigos.)
- `versoes/PDFLab-X.Y.Z.html` (até a 1.17.4, `versoes/AvulsoIA-X.Y.Z.html`) — cada versão publicada. Para usar sem
  instalar, baixe o arquivo e abra no navegador.
- `programa/X.Y.Z/` — os arquivos do programa (`pdflab.pyw`, `pdflab.ico`; antes `avulsoia.*`) que mudaram naquela versão.
- `atualizacao.json` — a versão mais recente: número, novidades e, para cada arquivo do app, caminho, origem,
  SHA-256 e tamanho (o instalador e o próprio app conferem tudo antes de gravar).

Nenhum PDF é enviado para a internet: tudo roda no seu computador.

**Apoie o projeto:** https://link.mercadopago.com.br/rladevapps

Este repositório guarda só as versões prontas, geradas pelo `publicar.py` do código-fonte.
