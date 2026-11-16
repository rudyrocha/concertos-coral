# Procedimento por concerto

## 1. Organizar as fontes

Crie uma pasta com data e nome corretos. Copie a estrutura do cartão da câmera sempre que possível. Coloque também o WAV do Tascam e um arquivo Markdown ou TXT com as músicas na ordem.

Não renomeie os MTS antes da análise. O nome e a sequência ajudam a detectar divisões automáticas da câmera.

## 2. Registrar o repertório

Use uma música por item. Exemplo:

```markdown
1. Primeira música — Compositor
2. Segunda música | Compositor / arranjo
3. BIS
```

O nome pode ser `repertorio.md`, `musicas.md` ou outro nome descritivo. Um `projeto_inicial.json` previamente analisado é opcional.

## 3. Revisar no editor

Abra o atalho **Editor de Concertos** e selecione a pasta. Na primeira abertura, o editor mede a gravação, importa o repertório, estima o sincronismo e gera a prévia. Essa análise pode levar vários minutos, sem abrir janelas do FFmpeg.

Revise primeiro o enquadramento. Use “Ver quadro original” para enxergar a área descartada e “Ver resultado final” para avaliar a composição.

Depois confira três pontos de sincronismo: início, meio e fim.

- Se a diferença for semelhante nos três pontos, ajuste **Deslocamento Tascam − câmera**.
- Se o início estiver correto e a diferença crescer ao longo da apresentação, ajuste **Correção de relógio**.
- Regenere a prévia depois de cada mudança. Se o valor informado for incompatível, a prévia anterior permanece disponível.

Os marcadores iniciais importados são apenas estimativas distribuídas pela gravação. Para cada música:

1. posicione a reprodução no início exato;
2. clique em **Marcar aqui**;
3. confira título e créditos.

Para música não prevista ou BIS:

1. posicione o vídeo no início exato;
2. clique em “+ Música neste ponto” ou “+ BIS neste ponto”;
3. preencha título e créditos;
4. ordene por timecode, se necessário.

Marque o fim musical da última apresentação e confira as margens. A exportação final só é liberada quando não houver marcações pendentes. Alterações de sincronismo ou corte exigem regenerar a prévia; alterações de enquadramento, não.

Use inicialmente o tratamento de volume **Equilibrado**. Ele aproxima o programa de −16 LUFS e contém aplausos muito acima do coro. Escolha **Natural** apenas quando a gravação já estiver nivelada ou quando quiser preservar integralmente a dinâmica captada.

## 4. Exportar e validar

Renderize o vídeo final e aguarde a validação. Se a diferença de duração ultrapassar a tolerância, confira `relatorio_exportacao.json`, o começo e o fim do vídeo e as transições nos pontos de divisão dos MTS.

Faça uma conferência audiovisual final antes do upload:

- sincronismo no início, meio e fim;
- ausência de áudio da câmera;
- enquadramento e cartelas;
- primeiro e último corte;
- ordem e grafia dos capítulos;
- ausência de falhas nas emendas dos arquivos da câmera.

## 5. Arquivar

Preserve o ZIP criado em `_CoralEditor_Arquivos`. Ele permite reconstruir as decisões de edição sem guardar prévia, vídeo final ou fontes brutas.
