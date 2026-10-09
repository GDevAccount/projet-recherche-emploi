import { Pipe, PipeTransform } from '@angular/core';

/** Affiché à la place d'une valeur que l'API ne connaît pas. */
export const UNKNOWN = '—';

const NUMBER = new Intl.NumberFormat('fr-FR');
// Une décimale au plus : les secondes d'une durée, les points d'un pourcentage
const SECONDS = new Intl.NumberFormat('fr-FR', { maximumFractionDigits: 1 });

function decimals(digits: number): Intl.NumberFormat {
  return new Intl.NumberFormat('fr-FR', { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

const CENTS = decimals(2);
const MILLS = decimals(3);
const TENTHS_OF_MILLS = decimals(4);

/**
 * Coût en dollars : « 12,40 $ », « 0,055 $ », « 0,0072 $ ». Une recherche coûte quelques centimes et une page
 * une fraction de centime : plus le montant est petit, plus il garde de décimales.
 */
@Pipe({ name: 'usd' })
export class UsdPipe implements PipeTransform {
  transform(value: number | null | undefined): string {
    if (value === null || value === undefined) {
      return UNKNOWN;
    }
    const amount = Math.abs(value);
    const format = amount === 0 || amount >= 1 ? CENTS : amount >= 0.01 ? MILLS : TENTHS_OF_MILLS;
    return `${format.format(value)} $`;
  }
}

/** Durée en millisecondes : « 26 ms », « 16,9 s », « 1 min 12 s ». */
@Pipe({ name: 'duration' })
export class DurationPipe implements PipeTransform {
  transform(value: number | null | undefined): string {
    if (value === null || value === undefined) {
      return UNKNOWN;
    }
    if (value < 1000) {
      return `${Math.round(value)} ms`;
    }
    const seconds = value / 1000;
    if (seconds < 60) {
      return `${SECONDS.format(seconds)} s`;
    }
    const rounded = Math.round(seconds);
    return `${Math.floor(rounded / 60)} min ${rounded % 60} s`;
  }
}

/** Part entre 0 et 1, en pourcentage : « 12,5 % ». */
@Pipe({ name: 'share' })
export class SharePipe implements PipeTransform {
  transform(value: number | null | undefined): string {
    return value === null || value === undefined ? UNKNOWN : `${SECONDS.format(value * 100)} %`;
  }
}

/** Nombre entier avec ses séparateurs de milliers : « 69 819 ». */
@Pipe({ name: 'count' })
export class CountPipe implements PipeTransform {
  transform(value: number | null | undefined): string {
    return value === null || value === undefined ? UNKNOWN : NUMBER.format(value);
  }
}
