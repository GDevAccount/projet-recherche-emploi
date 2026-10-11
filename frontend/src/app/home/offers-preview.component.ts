import { ChangeDetectionStrategy, Component } from '@angular/core';

import { Job } from '../core/api.models';
import { JobCardComponent } from '../jobs/job-card.component';

/** Offre inventée : seuls les champs qui changent d'une carte à l'autre sont à donner. */
function sampleJob(id: number, fields: Partial<Job> & Pick<Job, 'url' | 'title'>): Job {
  return {
    id,
    content: null,
    score: null,
    contract_type: 'CDI',
    work_location: 'Lyon',
    query: 'Développeur Python',
    match_reason: null,
    status: 'todo',
    applied_at: null,
    interview_at: null,
    rejected_at: null,
    created_at: '2026-10-06T08:12:00Z',
    next_statuses: ['applied'],
    ...fields,
  };
}

// Les adresses sont celles des sites, pas d'annonces : rien ici ne mène à une page inventée
const TODO: Job[] = [
  sampleJob(1, {
    url: 'https://www.welcometothejungle.com/',
    title: 'Développeur Python / Django (H/F)',
    match_reason:
      'Cinq ans de Python et de Django sur votre CV, le niveau demandé par l’annonce. Le poste est à Lyon, en CDI.',
  }),
  sampleJob(2, {
    url: 'https://www.apec.fr/',
    title: 'Ingénieur backend Python — éditeur de logiciels',
    work_location: 'Villeurbanne',
    created_at: '2026-10-05T16:40:00Z',
    match_reason:
      'L’annonce demande Python, PostgreSQL et des API REST : trois compétences de votre CV. Villeurbanne est dans votre zone.',
  }),
];

const APPLIED: Job[] = [
  sampleJob(3, {
    url: 'https://www.hellowork.com/',
    title: 'Développeur Python confirmé (H/F)',
    status: 'interview',
    applied_at: '2026-10-01T09:00:00Z',
    interview_at: '2026-10-07T09:00:00Z',
    next_statuses: ['applied'],
  }),
  sampleJob(4, {
    url: 'https://www.free-work.com/',
    title: 'Développeur full stack Python / Angular',
    contract_type: 'Freelance',
    work_location: 'Remote',
    status: 'applied',
    applied_at: '2026-10-03T09:00:00Z',
    next_statuses: ['interview', 'todo', 'rejected'],
  }),
];

/**
 * Aperçu de l'écran Offres, pour la page d'accueil : les vraies cartes de l'application, avec des offres
 * inventées. Tout y est inerte : c'est une image, pas un écran.
 */
@Component({
  selector: 'app-offers-preview',
  imports: [JobCardComponent],
  templateUrl: './offers-preview.component.html',
  styleUrl: './offers-preview.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class OffersPreviewComponent {
  protected readonly todo = TODO;
  protected readonly applied = APPLIED;
}
