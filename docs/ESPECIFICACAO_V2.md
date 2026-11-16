# Especificação funcional — versão 2

## Objetivo

Transformar o editor específico do concerto *Estação Pais* em uma ferramenta reutilizável para apresentações futuras do Coral Paineiras, mantendo uma etapa humana de revisão antes da exportação.

## Entradas

- uma sequência contínua de arquivos MTS ou M2TS da câmera;
- exatamente um WAV principal do Tascam;
- um arquivo Markdown ou TXT com as músicas na ordem, recomendado;
- opcionalmente, `projeto_inicial.json` com dados previamente analisados.

O PDF do programa não é interpretado diretamente. O editor lê listas numeradas, listas com marcadores e tabelas simples em Markdown/TXT. A leitura preserva a ordem, mas não identifica automaticamente o ponto musical no áudio.

## Requisitos implementados

### Repertório

- editar título, créditos e timecode;
- habilitar ou desabilitar itens;
- adicionar música no ponto atual;
- adicionar BIS no ponto atual;
- excluir e reordenar itens;
- ordenar todo o repertório pelo timecode;
- gerar capítulos e cartelas a partir da lista aprovada.
- importar automaticamente o primeiro Markdown/TXT reconhecido na pasta do concerto;
- marcar todos os timecodes estimados como pendentes até revisão humana.

### Preparação automática

- medir a duração total da sequência MTS/M2TS e do WAV;
- analisar largura, altura, frame rate e entrelaçamento da câmera;
- estimar o deslocamento inicial por correlação dos envelopes de áudio;
- gerar a primeira prévia com a extensão real da gravação;
- reaproveitar e corrigir automaticamente projetos ainda intactos da versão 2.1;
- bloquear a exportação final enquanto houver início ou fim musical pendente.

### Enquadramento

- exibir a prévia sem recorte;
- simular o enquadramento final em tempo real no navegador;
- controlar zoom, posição horizontal e posição vertical;
- alternar entre quadro original com máscara e resultado final;
- manter a proporção da exportação e valores pares exigidos pelo codec.

### Cortes

- separar o marcador de início da primeira música do corte inicial;
- separar o marcador de fim musical do corte final;
- permitir margens entre 0 e 120 segundos;
- mostrar a duração final prevista antes de renderizar.

### Exportação e arquivo

- usar apenas o áudio do Tascam;
- aplicar correção linear de relógio e ganho global;
- aplicar recorte somente na renderização final;
- medir a duração do MP4 final com FFprobe;
- comparar duração real e prevista com tolerância configurável;
- registrar o resultado em `relatorio_exportacao.json`;
- gerar ZIP externo sem arquivos de mídia.

### Operação no Windows

- abrir por atalho na Área de Trabalho com o logo do Clube Paineiras;
- selecionar a pasta do concerto em uma janela nativa;
- não exibir consoles do Python, FFmpeg ou FFprobe durante o uso normal;
- manter uma única instância na porta local 8765;
- oferecer encerramento explícito pela interface.

## Regras de validação

- pelo menos uma música habilitada;
- músicas habilitadas em ordem cronológica e sem timecodes repetidos;
- fim musical posterior ao início da última música;
- margem anterior disponível no WAV;
- ganho entre −24 e +24 dB;
- correção de relógio entre 0,95 e 1,05;
- recorte contido no quadro original, com valores pares e proporção da exportação.

## Critérios de aceite

1. Um projeto da versão 1 abre sem perda de repertório, sincronismo ou enquadramento.
2. Uma música extra e um BIS podem ser adicionados, editados e refletidos nos capítulos e cartelas.
3. O enquadramento pode ser ajustado visualmente antes da renderização final.
4. Alterações de enquadramento não exigem nova prévia.
5. Alterações de limites temporais indicam que a prévia precisa ser regenerada.
6. Ao final da exportação, a diferença de duração é exibida e registrada.
7. O ZIP externo é criado sem conter MP4, MTS, M2TS ou WAV.
8. Abrir novamente o mesmo concerto reutiliza a instância existente; outro concerto é recusado até o encerramento.
9. FFmpeg e FFprobe não abrem janelas nem recebem teclas do usuário no Windows.
10. Sem `projeto_inicial.json`, um concerto de dez minutos ou mais gera uma prévia próxima da duração real, e não a prévia de 80 segundos do modelo antigo.
11. Um repertório Markdown é carregado na ordem e suas marcações ficam pendentes até confirmação.

## Limitações conhecidas

- o deslocamento inicial é estimado automaticamente, mas precisa ser conferido; a deriva não é estimada;
- PDF não é lido automaticamente;
- não há reconhecimento automático dos inícios das músicas;
- saltos não lineares entre câmera e gravador exigem tratamento manual;
- a validação de duração não substitui a conferência audiovisual do arquivo final.
