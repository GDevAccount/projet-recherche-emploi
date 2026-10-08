// jsdom n'a pas ResizeObserver, dont les onglets de PrimeNG ont besoin
class ResizeObserverStub {
  observe = (): void => undefined;
  unobserve = (): void => undefined;
  disconnect = (): void => undefined;
}

globalThis.ResizeObserver ??= ResizeObserverStub;
