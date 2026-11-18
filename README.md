# Editor de Concertos Corais

Aplicativo local para preparar gravações feitas com câmera Sony Handycam e áudio externo Tascam. O editor sincroniza as fontes, permite revisar repertório, enquadramento e cortes, gera capítulos para o YouTube, aplica cartelas de identificação e exporta um único vídeo.

O sistema preserva os arquivos originais. Todo o processamento ocorre no computador do usuário.

## Ajustes e tratamento de áudio na versão 2.6.1

**Enquadramento e áudio** começa recolhido. Os blocos de sincronismo e comparação de áudio abrem de forma independente logo abaixo da prévia.

1. Ao atualizar, execute `instalar.bat` para preparar as dependências locais do tratamento.
2. Em **Enquadramento e áudio**, escolha **Câmera tratada com referência do Tascam** para usar esse áudio na prévia e no vídeo final. A seleção é salva no projeto.
3. Em **Comparar ou exportar trechos de áudio**, marque um trecho e clique em **Comparar câmera original e tratada**. Alterne as versões no player com o mesmo volume e na mesma posição.

O editor reaproveita o sincronismo do projeto, busca um ajuste fino para o Tascam e usa essa referência para atenuar interferências na câmera. Projetos anteriores abrem com a seleção Tascam. Com a câmera tratada, o controle de ganho do Tascam fica desativado e o tratamento de volume escolhido continua disponível.

## Recursos da versão 2.5.0

Abra a mesma pasta do concerto para continuar do `_CoralEditor/projeto.json` existente. O botão **Recuperar progresso salvo** recarrega as últimas alterações salvas e retorna o player à posição gravada por esta versão, quando ela está na prévia.

Em **Exportar trechos para análise de áudio**, marque o início e o fim de um ou dois trechos usando o player ou os horários da câmera. O editor usa o sincronismo exibido na tela e gera um ZIP com um WAV por fonte e por trecho, além dos horários exatos. Os WAVs preservam canais e níveis. Baixe o ZIP para compartilhar as amostras.

Em **Cortes e margens**, use **Ir para o início ajustado** para conferir o corte na prévia. Se a nova margem incluir um trecho que ficou fora da prévia atual, regenere a prévia.

Em **Testar sincronismo em dois pontos**, posicione a prévia em um ponto com um som fácil de reconhecer e clique em **Usar posição da prévia**, ou digite o horário na câmera. Faça isso em A e B, perto do começo e do fim. Ajuste o deslocamento e a correção de relógio e gere os testes de 10 s. Os dois clipes ficam em players separados, com os valores usados em cada um. Ao concluir, use **Regenerar prévia** para aplicar os parâmetros ao vídeo inteiro.

Em **Importar programa**, cole a lista numerada, com título e créditos em linhas separadas ou no formato `1) Título | Créditos`. Clique em **Conferir músicas**, revise a ordem e aplique. Os títulos e créditos são atualizados por posição nas músicas habilitadas. Os horários existentes são preservados e as novas músicas precisam ser marcadas.

Para ler uma foto JPG ou PNG, instale o [Tesseract OCR](https://tesseract-ocr.github.io/tessdoc/Installation.html) com o idioma português (`por`). Use **Ler foto** e revise o texto extraído antes de aplicar. A leitura acontece no próprio computador.

- reparo assistido de projetos com timecodes fora da duração das fontes;
- cópia automática do projeto anterior antes de redistribuir marcadores;
- validação da duração e do tamanho da nova prévia antes de substituir a anterior;
- bloqueio de novos marcadores que ultrapassem a duração do Tascam;
- abertura garantida mesmo quando o projeto salvo contém sincronismo incompatível;
- seletor de pasta iniciado em `D:\OFFline\Videos`, quando disponível;
- mensagem visível e `editor_erro.log` para falhas inesperadas de inicialização;
- reinício automático do servidor local quando a interface foi atualizada;
- orientação legível quando tela e servidor estão em versões diferentes;
- margens antes e depois das músicas sem limite arbitrário de 120 segundos;
- indicação separada do trecho removido e da margem preservada;
- abertura imediata da interface enquanto a prévia é gerada em segundo plano;
- tratamento de volume equilibrado com compressão moderada e normalização EBU R128 em −16 LUFS;
- opção de preservar o áudio natural usando somente o ganho global;
- proteção contra prévia vazia ao alterar o deslocamento de sincronismo;
- preservação automática da prévia anterior quando uma regeneração falha;
- leitura automática do repertório em Markdown ou TXT na pasta do concerto;
- primeira prévia baseada na duração real da gravação, nunca nos marcadores do modelo;
- estimativa inicial de sincronismo entre o áudio da câmera e o Tascam;
- marcações importadas claramente identificadas como provisórias;
- bloqueio da exportação final até a confirmação de todos os marcadores;
- inclusão, exclusão e reordenação de músicas;
- inclusão de músicas não previstas e BIS no ponto atual do vídeo;
- ajuste visual de zoom e posição do quadro sobre a prévia;
- edição dos dados do concerto e do nome do arquivo final;
- margens configuráveis antes da primeira música e depois da última;
- capítulos do YouTube e cartelas inferiores gerados automaticamente;
- áudio final exclusivamente do Tascam;
- validação da duração prevista contra a duração efetivamente exportada;
- ZIP pequeno de arquivamento, sem vídeo nem prévia, salvo fora da pasta do concerto;
- migração automática de projetos criados pela versão 1.

O modo **Equilibrado** reduz a diferença excessiva entre músicas e aplausos sem tentar classificar automaticamente cada trecho. Essa abordagem evita que um crescendo do coro seja confundido com aplauso. O modo **Natural** permanece disponível para gravações que já estejam bem controladas.

## Instalação e atalho no Windows

1. Baixe o ZIP do repositório e extraia-o em uma pasta permanente.
2. Execute `instalar.bat`.
3. O instalador valida Python e FFmpeg, cria um ambiente isolado e instala na Área de Trabalho o atalho **Editor de Concertos**.
4. Ao abrir o atalho, selecione a pasta do concerto.

No computador de edição, o seletor começa em `D:\OFFline\Videos`. Se essa pasta não existir, começa na raiz de unidades do Windows.

O atalho usa o logo do Clube Paineiras e inicia o aplicativo sem janela de terminal permanente. FFmpeg e FFprobe também são executados sem janelas e sem acesso ao teclado.

## Requisitos

- Windows 10 ou 11;
- Python 3.10 ou posterior;
- FFmpeg e FFprobe com `libx264` e `libass` disponíveis no `PATH`, ou os executáveis na pasta do editor;
- navegador moderno.

O editor mantém uma única instância na porta local `8765`. Para trocar de concerto, use **Encerrar editor** na interface e abra novamente pelo atalho.

## Uso em um novo concerto

1. Reúna em uma única pasta todos os arquivos MTS/M2TS e um único WAV do Tascam.
2. Salve o repertório ordenado em um arquivo Markdown (`.md`) ou texto (`.txt`). Use uma música por item numerado ou com marcador. Separe os créditos com `—` ou `|`.
3. Abra **Editor de Concertos** pela Área de Trabalho e selecione a pasta.
4. O editor identifica a duração real, importa o repertório, estima o sincronismo e gera uma prévia de toda a apresentação.
5. Revise, nesta ordem:
   - enquadramento;
   - sincronismo por amostragem no início, meio e fim;
   - músicas, músicas extras e BIS;
   - início da primeira música e fim musical da última;
   - margens de corte;
   - cartelas e capítulos.
6. Em cada música, posicione a reprodução no início e clique em **Marcar aqui**. Faça o mesmo em **Marcar fim aqui** ao final da última apresentação.
7. Salve, regenere a prévia se alterou sincronismo ou cortes e renderize o vídeo final.
8. Confira no painel a validação de duração e os caminhos do vídeo e do ZIP do projeto.

No sincronismo, use **Deslocamento Tascam − câmera** quando a diferença for aproximadamente constante durante todo o concerto. Se a diferença aumentar gradualmente do início para o fim, ajuste **Correção de relógio**. Ao informar um valor incompatível com as fontes, o editor recusa a nova prévia e mantém a anterior disponível.

Se um projeto antigo contiver marcações fora das fontes, use **Reparar marcações e prévia**. O editor arquiva o JSON anterior, preserva as músicas habilitadas, redistribui os pontos provisoriamente na duração real e gera novamente a prévia completa.

Um `projeto_inicial.json` analisado externamente continua sendo aceito. Sem ele, a configuração inicial é feita automaticamente. Os marcadores distribuídos pelo editor são sugestões de navegação, não reconhecimento musical; a exportação final só é liberada após confirmação humana.

## Pastas geradas

Na pasta do concerto:

```text
_CoralEditor/
├── projeto.json
├── preview.mp4
├── legendas.ass
├── capitulos_youtube.txt
├── processamento.log
├── relatorio_exportacao.json
└── final/
    └── video_final.mp4
```

Ao lado da pasta do concerto:

```text
_CoralEditor_Arquivos/
└── DATA_Nome_do_concerto_projeto.zip
```

O ZIP externo contém apenas projeto, log, capítulos, cartelas e relatório. Assim, pode ser preservado mesmo quando a pasta de mídia for excluída.

## Execução por linha de comando

```powershell
python coral_editor.py --source "D:\Caminho\Do Concerto"
python coral_editor.py --source "D:\Caminho\Do Concerto" --prepare-only
python coral_editor.py --source "D:\Caminho\Do Concerto" --render-final
```

Para escolher outra pasta de arquivamento:

```powershell
python coral_editor.py --source "D:\Caminho\Do Concerto" --archive-root "D:\Projetos Coral"
```

## Segurança operacional

- o servidor aceita conexões apenas em `127.0.0.1`;
- MTS/M2TS e WAV são somente lidos;
- arquivos parciais usam sufixo `.parcial` e só substituem a saída após sucesso;
- o editor bloqueia projetos sem música, com marcadores fora de ordem ou recorte inválido;
- um alerta de duração não apaga o vídeo: ele registra a divergência para conferência.

Consulte [Especificação da versão 2](docs/ESPECIFICACAO_V2.md), [Arquitetura](docs/ARQUITETURA.md), [Procedimento por concerto](docs/PROCEDIMENTO_CONCERTO.md), [Requisitos operacionais](docs/REQUISITOS_OPERACIONAIS.md) e [Histórico de versões](docs/CHANGELOG.md).
