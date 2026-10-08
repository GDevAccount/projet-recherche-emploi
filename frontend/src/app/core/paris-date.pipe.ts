import { Pipe, PipeTransform } from '@angular/core';

// L'API renvoie des dates UTC : l'heure affichée est celle de Paris, où que soit le navigateur.
// Le DatePipe d'Angular n'accepte qu'un décalage fixe, qui serait faux la moitié de l'année.
const FORMAT = new Intl.DateTimeFormat('fr-FR', {
  timeZone: 'Europe/Paris',
  day: 'numeric',
  month: 'long',
  year: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
});

/** « 8 octobre 2026 à 14:05 », heure de Paris, à partir d'une date UTC de l'API. */
@Pipe({ name: 'parisDate' })
export class ParisDatePipe implements PipeTransform {
  transform(value: string | null | undefined): string {
    if (!value) {
      return '';
    }
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? '' : FORMAT.format(date);
  }
}
