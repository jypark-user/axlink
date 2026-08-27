export interface SseEvent {
  event: string;
  data: string;
  id?: string;
}

export async function* parseSseStream(
  body: ReadableStream<Uint8Array>,
  signal?: AbortSignal,
): AsyncGenerator<SseEvent> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let currentEvent = 'message';
  let currentId: string | undefined;
  let dataLines: string[] = [];

  const flush = function* (): Generator<SseEvent> {
    if (dataLines.length === 0 && currentEvent === 'message') {
      currentEvent = 'message';
      return;
    }
    const data = dataLines.join('\n');
    dataLines = [];
    const event = currentEvent;
    const id = currentId;
    currentEvent = 'message';
    currentId = undefined;
    if (data !== '' || event !== 'message' || id !== undefined) {
      yield { event, data, id };
    }
  };

  try {
    while (true) {
      if (signal?.aborted) break;
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let idx: number;
      while ((idx = buffer.indexOf('\n\n')) !== -1) {
        const chunk = buffer.slice(0, idx);
        buffer = buffer.slice(idx + 2);
        for (const line of chunk.split('\n')) {
          if (line === '' || line.startsWith(':')) continue;
          const colon = line.indexOf(':');
          const field = colon === -1 ? line : line.slice(0, colon);
          let val = colon === -1 ? '' : line.slice(colon + 1);
          if (val.startsWith(' ')) val = val.slice(1);
          if (field === 'event') currentEvent = val;
          else if (field === 'data') dataLines.push(val);
          else if (field === 'id') currentId = val;
        }
        yield* flush();
      }
    }
    if (buffer.trim() !== '') {
      for (const line of buffer.split('\n')) {
        if (line === '' || line.startsWith(':')) continue;
        const colon = line.indexOf(':');
        const field = colon === -1 ? line : line.slice(0, colon);
        let val = colon === -1 ? '' : line.slice(colon + 1);
        if (val.startsWith(' ')) val = val.slice(1);
        if (field === 'event') currentEvent = val;
        else if (field === 'data') dataLines.push(val);
        else if (field === 'id') currentId = val;
      }
      yield* flush();
    }
  } finally {
    reader.cancel().catch(() => {});
  }
}
