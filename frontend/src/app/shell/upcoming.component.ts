import { ChangeDetectionStrategy, Component, input } from '@angular/core';

/** Rubrique dont l'écran n'est pas encore écrit. Disparaîtra avec le dernier écran. */
@Component({
  selector: 'app-upcoming',
  template: `
    <section>
      <span class="badge">Bientôt</span>
      <h2>{{ title() }}</h2>
      <p>{{ text() }}</p>
    </section>
  `,
  styleUrl: './upcoming.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class UpcomingComponent {
  // Renseignés par la route (withComponentInputBinding)
  readonly title = input('');
  readonly text = input('');
}
