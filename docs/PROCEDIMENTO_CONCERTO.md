# Procedimento por concerto

## 1. Organizar as fontes

Crie uma pasta com data e nome corretos. Copie a estrutura do cartão da câmera sempre que possível. Coloque também o WAV do Tascam, o programa e `observacoes.txt` com alterações conhecidas, músicas extras ou BIS.

Não renomeie os MTS antes da análise. O nome e a sequência ajudam a detectar divisões automáticas da câmera.

## 2. Preparar o projeto inicial

Gere o diagnóstico e analise:

- ordem e continuidade dos arquivos da câmera;
- formato, frame rate e entrelaçamento;
- deslocamento inicial entre câmera e Tascam;
- deriva no início, meio e fim;
- repertório e créditos;
- sugestões de início de cada música e fim musical.

Salve o resultado como `projeto_inicial.json` na pasta do concerto.

## 3. Revisar no editor

Abra o editor arrastando a pasta sobre `Iniciar_Editor.bat`.

Revise primeiro o enquadramento. Use “Ver quadro original” para enxergar a área descartada e “Ver resultado final” para avaliar a composição.

Depois confira três pontos de sincronismo: início, meio e fim. O editor não altera automaticamente os parâmetros de sincronismo pela interface.

Revise o repertório. Para música não prevista ou BIS:

1. posicione o vídeo no início exato;
2. clique em “+ Música neste ponto” ou “+ BIS neste ponto”;
3. preencha título e créditos;
4. ordene por timecode, se necessário.

Marque o fim musical da última apresentação e confira as margens. Alterações de corte exigem regenerar a prévia; alterações de enquadramento, não.

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
