import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { Card } from 'primeng/card';
import { Tag } from 'primeng/tag';

import { HealthService } from '../core/health.service';

type ApiState = 'pending' | 'ok' | 'error';

@Component({
  selector: 'app-health',
  imports: [Card, Tag],
  templateUrl: './health.component.html',
  styleUrl: './health.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class HealthComponent {
  private readonly healthService = inject(HealthService);

  protected readonly state = signal<ApiState>('pending');

  constructor() {
    this.healthService.getHealth().subscribe({
      next: (health) => this.state.set(health.status === 'ok' ? 'ok' : 'error'),
      error: () => this.state.set('error'),
    });
  }
}
