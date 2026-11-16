# Requisitos operacionais herdados do Editor de Ensaios

Este documento registra os requisitos do projeto `editor-ensaio` que também se aplicam ao Editor de Concertos. Regras específicas de reconhecimento e segmentação de ensaios não foram transportadas porque não pertencem a este fluxo.

## Execução no Windows

1. O atalho da Área de Trabalho aponta para `Editor de Concertos.vbs`.
2. O lançador usa `pythonw.exe`, sem manter uma janela de terminal aberta.
3. Se o ambiente `.venv` ainda não existir, o instalador é executado de forma visível para que erros não fiquem ocultos.
4. O atalho usa `assets/Editor_Concertos.ico`, derivado do logo oficial fornecido do Clube Paineiras do Morumby.
5. Ao abrir pelo atalho, o usuário escolhe a pasta do concerto em uma janela do Windows.
6. O seletor usa `D:\OFFline\Videos` como pasta inicial quando ela existe; caso contrário, apresenta a raiz de unidades.
7. Uma falha inesperada de inicialização exibe mensagem e grava `editor_erro.log` na pasta do aplicativo.

## FFmpeg e FFprobe sem janelas

Todo subprocesso de mídia deve receber simultaneamente:

- `stdin=subprocess.DEVNULL`;
- `creationflags=CREATE_NO_WINDOW`, quando disponível;
- `STARTUPINFO` com `STARTF_USESHOWWINDOW` e janela oculta no Windows;
- `-nostdin` nos comandos FFmpeg.

Isso evita janelas intermitentes e impede que teclas digitadas pelo usuário sejam capturadas pelo FFmpeg. `stderr` permanece registrado para diagnóstico.

## Instância única e encerramento

- O servidor usa somente `127.0.0.1:8765`; não procura portas alternativas.
- Um segundo lançamento para o mesmo concerto apenas reabre a interface existente.
- Um segundo lançamento para outra pasta é recusado até que o editor atual seja encerrado.
- Fechar a aba não encerra o servidor. A interface oferece o botão **Encerrar editor**.
- O encerramento é bloqueado durante uma renderização.

## Preservação e recuperação

- Arquivos MTS/M2TS e WAV originais são somente lidos.
- Saídas são produzidas primeiro com sufixo `.parcial` e publicadas apenas após sucesso.
- Falha de renderização mantém projeto, log, prévia anterior e originais.
- Uma regeneração com sincronismo incompatível não encerra o editor quando existe uma prévia anterior válida.
- Uma prévia só substitui a anterior depois que sua duração é medida e validada.
- O reparo de linha do tempo cria uma cópia datada do JSON anterior antes de alterar marcadores.
- O ZIP externo de projeto não contém mídia e não substitui um pacote anterior com o mesmo nome.
- A validação de duração gera alerta, mas não exclui automaticamente o MP4.

## Compatibilidade e releases

- O esquema do projeto é versionado e projetos da versão 1 são migrados.
- Mudanças de formato exigem migração e teste com fixture antiga.
- Testes automatizados nunca apontam para pastas de produção.
- A homologação final continua exigindo um concerto real no Windows.
