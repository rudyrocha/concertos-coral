# Editor de Concertos Corais

Aplicativo local para preparar gravações feitas com câmera Sony Handycam e áudio externo Tascam. O editor sincroniza as fontes, permite revisar repertório, enquadramento e cortes, gera capítulos para o YouTube, aplica cartelas de identificação e exporta um único vídeo.

O sistema preserva os arquivos originais. Todo o processamento ocorre no computador do usuário.

## Principais recursos da versão 2.2

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

## Instalação e atalho no Windows

1. Baixe o ZIP do repositório e extraia-o em uma pasta permanente.
2. Execute `instalar.bat`.
3. O instalador valida Python e FFmpeg, cria um ambiente isolado e instala na Área de Trabalho o atalho **Editor de Concertos**.
4. Ao abrir o atalho, selecione a pasta do concerto.

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

Consulte [Especificação da versão 2](docs/ESPECIFICACAO_V2.md), [Arquitetura](docs/ARQUITETURA.md), [Procedimento por concerto](docs/PROCEDIMENTO_CONCERTO.md) e [Requisitos operacionais](docs/REQUISITOS_OPERACIONAIS.md).
