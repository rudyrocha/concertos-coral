# Histórico de versões

## 2.3.3

- detecta quando a interface atualizada ainda está conectada a um processo antigo;
- encerra automaticamente a instância anterior ao abrir a nova versão;
- substitui o erro técnico de JSON por uma orientação para encerrar e reabrir o editor.

## 2.3.2

- detecta marcadores gravados além da duração real de vídeo e áudio;
- oferece reparo assistido com cópia automática do projeto anterior;
- preserva as músicas habilitadas e redistribui apenas seus timecodes;
- valida a duração da saída antes de publicar uma nova prévia;
- impede que uma saída vazia substitua uma prévia válida.

## 2.3.1

- permite abrir e corrigir projetos que tenham sincronismo incompatível salvo;
- impede encerramento silencioso antes da abertura do navegador;
- mostra falhas inesperadas e grava `editor_erro.log`;
- inicia o seletor em `D:\OFFline\Videos` quando a pasta existe.

## 2.3.0

- corrige prévia vazia após alteração do deslocamento de sincronismo;
- limita os cortes ao trecho realmente comum entre câmera e Tascam;
- preserva a prévia anterior quando a regeneração falha;
- distingue na interface deslocamento constante e deriva de relógio;
- adiciona modo de áudio equilibrado com compressão moderada e normalização EBU R128;
- mantém modo natural, sem processamento dinâmico.

## 2.2.0

- importa repertório em Markdown ou TXT;
- mede a duração real das fontes para gerar a primeira prévia;
- estima o deslocamento inicial entre câmera e Tascam;
- bloqueia a exportação final até a confirmação dos marcadores.

## 2.1.0

- executa Python, FFmpeg e FFprobe sem janelas no Windows;
- cria atalho na Área de Trabalho com a identidade do Clube;
- mantém uma única instância e oferece encerramento pela interface.
