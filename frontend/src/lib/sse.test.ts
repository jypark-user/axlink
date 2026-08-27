import { describe, expect, it } from 'vitest';
import { parseSseStream, type SseEvent } from '@/lib/sse';

const streamOf = (...chunks: string[]): ReadableStream<Uint8Array> => {
  const encoder = new TextEncoder();
  return new ReadableStream({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(encoder.encode(chunk));
      controller.close();
    },
  });
};

const collect = async (stream: ReadableStream<Uint8Array>): Promise<SseEvent[]> => {
  const out: SseEvent[] = [];
  for await (const event of parseSseStream(stream)) out.push(event);
  return out;
};

describe('parseSseStream', () => {
  it('parses event and data fields', async () => {
    const events = await collect(streamOf('event: delta\ndata: {"text":"안녕"}\n\n'));
    expect(events).toEqual([{ event: 'delta', data: '{"text":"안녕"}', id: undefined }]);
  });

  it('joins multi-line data with newlines', async () => {
    const events = await collect(streamOf('event: note\ndata: one\ndata: two\n\n'));
    expect(events[0].data).toBe('one\ntwo');
  });

  it('reassembles one event split across chunks, including a split UTF-8 sequence', async () => {
    const encoder = new TextEncoder();
    const whole = encoder.encode('event: delta\ndata: {"text":"3월 기준 요구사항"}\n\n');
    const cut = 20;
    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(whole.slice(0, cut));
        controller.enqueue(whole.slice(cut));
        controller.close();
      },
    });
    const events = await collect(stream);
    expect(events).toHaveLength(1);
    expect(events[0].data).toBe('{"text":"3월 기준 요구사항"}');
  });

  it('ignores comment lines and strips only one leading space', async () => {
    const events = await collect(streamOf(': keep-alive\nevent: ping\ndata:  padded\n\n'));
    expect(events).toEqual([{ event: 'ping', data: ' padded', id: undefined }]);
  });

  it('stops early when the signal is aborted', async () => {
    const controller = new AbortController();
    const stream = streamOf('event: a\ndata: 1\n\n', 'event: b\ndata: 2\n\n');
    const out: SseEvent[] = [];
    for await (const event of parseSseStream(stream, controller.signal)) {
      out.push(event);
      controller.abort();
    }
    expect(out.map((e) => e.event)).toEqual(['a']);
  });
});
