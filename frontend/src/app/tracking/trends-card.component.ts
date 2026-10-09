import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

import { WeekStats } from '../core/api.models';
import { CountPipe, SharePipe, UNKNOWN, UsdPipe } from '../core/format.pipe';
import { ParisDatePipe } from '../core/paris-date.pipe';

const usd = new UsdPipe();
const count = new CountPipe();
const share = new SharePipe();
const date = new ParisDatePipe();

/** Ce que la carte suit d'une semaine à l'autre, et comment l'écrire. */
const METRICS: {
  label: string;
  value: (week: WeekStats) => number | null;
  format: (value: number | null) => string;
  /** Une part se lit sur une échelle fixe, de 0 à 100 % */
  isShare?: boolean;
}[] = [
  { label: 'Coût', value: (week) => week.cost_usd, format: (value) => usd.transform(value) },
  { label: 'Recherches', value: (week) => week.runs, format: (value) => count.transform(value) },
  {
    label: 'Pages évaluées',
    value: (week) => week.evaluated,
    format: (value) => count.transform(value),
  },
  {
    label: 'Pages déjà connues',
    value: (week) => week.known_rate,
    format: (value) => share.transform(value),
    isShare: true,
  },
  {
    label: 'Offres retenues',
    value: (week) => week.kept,
    format: (value) => count.transform(value),
  },
  {
    label: 'Candidatures',
    value: (week) => week.applications,
    format: (value) => count.transform(value),
  },
];

/**
 * Les dernières semaines, mesure par mesure : un poste qui s'épuise ou un coût qui monte se voient ici.
 * Les chiffres viennent de l'API ; l'écran ne fait que les dessiner, chaque barre à l'échelle de la plus haute.
 */
@Component({
  selector: 'app-trends-card',
  templateUrl: './trends-card.component.html',
  styleUrl: './trends-card.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class TrendsCardComponent {
  readonly weeks = input.required<WeekStats[]>();

  protected readonly unknown = UNKNOWN;
  protected readonly since = computed(() => date.transform(this.weeks()[0]?.start, 'day'));

  protected readonly charts = computed(() => {
    const weeks = this.weeks();
    return METRICS.map((metric) => {
      const values = weeks.map((week) => metric.value(week));
      const highest = metric.isShare ? 1 : Math.max(0, ...values.map((value) => value ?? 0));
      return {
        label: metric.label,
        current: metric.format(values.at(-1) ?? null),
        previous: metric.format(values.at(-2) ?? null),
        bars: weeks.map((week, index) => {
          const value = values[index];
          const text = metric.format(value);
          return {
            start: week.start,
            unknown: value === null,
            height: highest && value ? (value / highest) * 100 : 0,
            title: `Semaine du ${date.transform(week.start, 'day')} : ${text}`,
          };
        }),
      };
    });
  });
}
