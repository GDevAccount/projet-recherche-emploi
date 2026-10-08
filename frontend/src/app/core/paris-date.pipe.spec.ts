import { ParisDatePipe } from './paris-date.pipe';

describe('ParisDatePipe', () => {
  const pipe = new ParisDatePipe();

  it('should show a UTC date in Paris summer time', () => {
    expect(pipe.transform('2026-07-14T12:05:00Z')).toBe('14 juillet 2026 à 14:05');
  });

  it('should show a UTC date in Paris winter time, even across midnight', () => {
    expect(pipe.transform('2026-12-31T23:30:00Z')).toBe('1 janvier 2027 à 00:30');
  });

  it('should show nothing for a missing or unreadable date', () => {
    expect(pipe.transform(null)).toBe('');
    expect(pipe.transform('pas une date')).toBe('');
  });
});
