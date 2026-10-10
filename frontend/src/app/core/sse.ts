/**
 * Lit un flux d'événements du serveur (Server-Sent Events) reçu par `fetch`, et rend chaque événement à
 * mesure : son nom, et ses données déjà lues en JSON. Un événement illisible est ignoré, pour ne pas perdre
 * les suivants.
 */
export async function readServerSentEvents(
  body: ReadableStream<Uint8Array>,
  onEvent: (name: string, payload: unknown) => void,
): Promise<void> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  for (;;) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value, { stream: !done });
    // Un événement se termine par une ligne vide ; le dernier morceau peut être incomplet
    const blocks = buffer.split('\n\n');
    buffer = blocks.pop() ?? '';
    for (const block of blocks) {
      const event = parse(block);
      if (event) {
        onEvent(event.name, event.payload);
      }
    }
    if (done) {
      return;
    }
  }
}

function parse(block: string): { name: string; payload: unknown } | null {
  let name = '';
  let data = '';
  for (const line of block.split('\n')) {
    if (line.startsWith('event:')) {
      name = line.slice(6).trim();
    } else if (line.startsWith('data:')) {
      data += line.slice(5).trim();
    }
  }
  if (!name || !data) {
    return null;
  }
  try {
    return { name, payload: JSON.parse(data) };
  } catch {
    return null;
  }
}
