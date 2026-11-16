# Editor de Concertos Corais

Aplicativo local para preparar gravações feitas com câmera Sony Handycam e áudio externo Tascam. O editor sincroniza as fontes, permite revisar repertório, enquadramento e cortes, gera capítulos para o YouTube, aplica cartelas de identificação e exporta um único vídeo.

O sistema preserva os arquivos originais. Todo o processamento ocorre no computador do usuário.

## Principais recursos da versão 2

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

## Requisitos

- Windows 10 ou 11;
- Python 3.10 ou posterior;
- FFmpeg e FFprobe com `libx264` e `libass` disponíveis no `PATH`, ou os executáveis na pasta do editor;
- navegador moderno.

## Uso em um novo concerto

1. Reúna em uma única pasta todos os arquivos MTS/M2TS, um único WAV do Tascam, o programa em PDF e, se necessário, `observacoes.txt`.
2. Gere e analise o pacote diagnóstico para obter sincronismo, deriva, repertório inicial e características da câmera.
3. Coloque na pasta do concerto o arquivo analisado com o nome `projeto_inicial.json`.
4. Arraste a pasta do concerto sobre `Iniciar_Editor.bat`.
5. Aguarde a geração da primeira prévia.
6. Revise, nesta ordem:
   - enquadramento;
   - sincronismo por amostragem no início, meio e fim;
   - músicas, músicas extras e BIS;
   - início da primeira música e fim musical da última;
   - margens de corte;
   - cartelas e capítulos.
7. Salve e renderize o vídeo final.
8. Confira no painel a validação de duração e os caminhos do vídeo e do ZIP do projeto.

Se não existir `projeto_inicial.json`, o editor usa `projeto_modelo.json`. Nesse caso, os valores de sincronismo e os marcadores são apenas provisórios e precisam ser substituídos antes da exportação.

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

Consulte [Especificação da versão 2](docs/ESPECIFICACAO_V2.md), [Arquitetura](docs/ARQUITETURA.md) e [Procedimento por concerto](docs/PROCEDIMENTO_CONCERTO.md).
