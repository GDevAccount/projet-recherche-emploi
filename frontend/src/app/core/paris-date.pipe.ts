import { Pipe, PipeTransform } from '@angular/core';

// L'API renvoie des dates UTC : l'heure affichée est celle de Paris, où que soit le navigateur.
// Le DatePipe d'Angular n'accepte qu'un décalage fixe, qui serait faux la moitié de l'année.
const TIME_ZONE = 'Europe/Paris';
const FORMATS = {
  full: new Intl.DateTimeFormat('fr-FR', {
    timeZone: TIME_ZONE,
    day: 'numeric',
    month: 'long',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }),
  day: new Intl.DateTimeFormat('fr-FR', { timeZone: TIME_ZONE, day: 'numeric', month: 'short' }),
};

/** Date UTC de l'API à l'heure de Paris : « 8 octobre 2026 à 14:05 », ou « 8 oct. » avec le format 'day'. */
@Pipe({ name: 'parisDate' })
export class ParisDatePipe implements PipeTransform {
  transform(value: string | null | undefined, format: keyof typeof FORMATS = 'full'): string {
    if (!value) {
      return '';
    }
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? '' : FORMATS[format].format(date);
  }
}
