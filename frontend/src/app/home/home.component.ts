import { DOCUMENT } from '@angular/common';
import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { RouterLink } from '@angular/router';

import { LOGIN_PATH } from '../core/paths';
import { HomeNavComponent } from './home-nav.component';
import { OffersPreviewComponent } from './offers-preview.component';
import { ProductDemoComponent } from './product-demo.component';
import { SECTIONS, scrollToSection } from './sections';

/**
 * Quelques-uns des sites interrogés par une recherche. Ils doivent figurer dans JOB_SITES de config.py :
 * tests/test_frontend.py le vérifie.
 */
export const SITES = [
  'welcometothejungle.com',
  'linkedin.com',
  'indeed.com',
  'apec.fr',
  'francetravail.fr',
  'hellowork.com',
  'free-work.com',
  'malt.fr',
  'cadremploi.fr',
  'jobteaser.com',
];

/** Ce que l'application fait réellement. Le dessin est le tracé d'une icône, sur une grille de 24. */
const FEATURES = [
  {
    icon: 'M11 17.5a6.5 6.5 0 1 0 0-13 6.5 6.5 0 0 0 0 13Zm5-1.5 4.5 4.5',
    title: 'Une recherche, tous les sites',
    text: "JobGrep interroge les principaux sites d'emploi en une fois. Une recherche en télétravail complet est aussi menée en anglais, sur des sites spécialisés.",
    wide: true,
  },
  {
    icon: 'M3 5h18l-7 8v6l-4-2v-4L3 5Z',
    title: 'Un tri fait avec votre CV',
    text: 'Chaque annonce est lue en entier : métier, compétences, niveau, contrat et lieu. Elle n’est retenue que si tout correspond, et vous savez pourquoi.',
    wide: false,
  },
  {
    icon: 'M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8Zm-7 8a7 7 0 0 1 14 0',
    title: 'Vos critères, tirés de votre CV',
    text: 'À son dépôt, vos postes recherchés sont préparés pour vous : métier, compétences, contrat, lieu. Vous les corrigez ou en ajoutez à la main.',
    wide: false,
  },
  {
    icon: 'M4 6h16M4 12h10M4 18h6m5-3 2 2 4-4',
    title: 'Le suivi de vos candidatures',
    text: 'À traiter, candidature envoyée, entretien obtenu, refus : chaque offre avance d’une étape à l’autre, d’un clic ou en la glissant.',
    wide: false,
  },
  {
    icon: 'M4 12a8 8 0 0 1 14-5l2-2v6h-6l2-2a5 5 0 1 0 1 6',
    title: 'Un tri que vous pouvez corriger',
    text: 'Les pages écartées restent consultables, avec leur motif. Une bonne offre s’y cache ? Vous la remettez dans vos offres.',
    wide: false,
  },
  {
    icon: 'M5 6h14v10H10l-5 4V6Zm4 4h6m-6 3h4',
    title: 'Un assistant qui connaît votre compte',
    text: "Il répond à vos questions sur l'application et, à partir de vos rejets et de vos postes recherchés, dit quoi régler pour trouver plus d'offres.",
    wide: true,
  },
] as const;

const STEPS = [
  {
    title: 'Déposez votre CV',
    text: 'Un PDF suffit. Vos coordonnées en sont retirées, et vos postes recherchés en sont tirés : il ne reste qu’à les relire.',
  },
  {
    title: 'Lancez une recherche',
    text: 'Elle prend environ une minute. Vous voyez chaque annonce passer, retenue ou écartée. La fois suivante, seules les nouvelles sont lues.',
  },
  {
    title: 'Suivez vos candidatures',
    text: 'Les annonces retenues arrivent dans vos offres, avec un lien vers l’annonce d’origine. Vous notez où vous en êtes pour chacune.',
  },
] as const;

/** Engagements écrits dans les règles de confidentialité : ne rien affirmer ici qui n'y figure pas. */
const COMMITMENTS = [
  {
    title: 'Vos coordonnées sont retirées de votre CV',
    text: 'Adresse e-mail, téléphone, liens, adresse postale et date de naissance en sont retirés automatiquement avant toute comparaison.',
  },
  {
    title: 'Le fichier de votre CV n’est pas conservé',
    text: 'Le PDF est lu une fois. Seul son texte, sans vos coordonnées, est enregistré.',
  },
  {
    title: 'Ni publicité, ni mesure d’audience',
    text: 'Un seul cookie, celui de votre connexion. Vos données ne sont ni vendues, ni visibles par les autres utilisateurs.',
  },
  {
    title: 'Vous effacez tout, quand vous voulez',
    text: 'La page Compte supprime votre compte et tout ce qu’il contient, immédiatement et sans retour possible.',
  },
] as const;

const QUESTIONS = [
  {
    question: 'Qu’est-ce que JobGrep ?',
    answer: [
      'Un agent de recherche d’emploi. Il cherche des offres sur les principaux sites, lit chaque annonce à votre place, la compare à votre CV et ne garde que celles qui vous correspondent, avec la raison de son verdict. Vous y suivez ensuite vos candidatures.',
    ],
  },
  {
    question: 'À qui s’adresse JobGrep ?',
    answer: [
      'À toute personne qui cherche un emploi en France ou en télétravail complet, et qui préfère lire dix annonces pertinentes plutôt que cent. Les contrats pris en charge : CDI, CDD, freelance, alternance et stage.',
    ],
  },
  {
    question: 'Comment commencer ?',
    answer: [
      'Connectez-vous, déposez votre CV en PDF, relisez les postes recherchés qui en sont tirés, puis lancez votre première recherche. Une visite guidée vous accompagne à la première connexion.',
    ],
  },
  {
    question: 'Faut-il créer un compte ?',
    answer: [
      'Il n’y a pas de formulaire d’inscription : la connexion se fait avec votre compte Google, qui ne transmet que votre adresse e-mail et votre profil de base. Votre compte JobGrep est créé à la première connexion.',
      'L’exploitant peut réserver l’accès à certaines personnes. Quand il est proposé, un essai sans compte permet de lancer une recherche avec votre CV.',
    ],
  },
  {
    question: 'Est-ce gratuit ?',
    answer: [
      'Oui. JobGrep est un projet personnel, mis à disposition gratuitement. Chaque recherche a un coût, pris en charge par l’exploitant : le nombre de recherches par jour est donc limité.',
    ],
  },
  {
    question: 'Quelles sont les fonctionnalités disponibles ?',
    answer: [
      'La recherche d’offres sur les sites d’emploi, le tri de chaque annonce selon votre CV et vos postes recherchés, le suivi de vos candidatures, la consultation et la correction des pages écartées, et un assistant qui répond à vos questions sur l’application.',
      'JobGrep ne postule pas à votre place et ne rédige ni CV ni lettre de motivation.',
    ],
  },
  {
    question: 'Le tri peut-il se tromper ?',
    answer: [
      'Oui : il est fait par un modèle d’intelligence artificielle. Il peut écarter une offre qui vous aurait convenu, ou en retenir une qui a expiré. C’est pourquoi chaque verdict est expliqué, et chaque rejet consultable. Vérifiez toujours une offre sur le site d’origine avant de postuler.',
    ],
  },
  {
    question: 'Comment mes données sont-elles utilisées ?',
    answer: [
      'Uniquement pour faire fonctionner le service. Le texte de votre CV, sans vos coordonnées, est envoyé à OpenAI, dont le modèle prépare vos postes recherchés et lit les annonces. Seuls vos postes recherchés sont envoyés à Tavily, le moteur qui interroge les sites. L’application est hébergée par Fly.io, dans la région de Paris.',
    ],
    privacy: true,
  },
];

/** Page d'accueil publique : ce que fait JobGrep, pour qui n'a pas de session. */
@Component({
  selector: 'app-home',
  imports: [RouterLink, HomeNavComponent, OffersPreviewComponent, ProductDemoComponent],
  templateUrl: './home.component.html',
  styleUrl: './home.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class HomeComponent {
  private readonly document = inject(DOCUMENT);

  protected readonly loginPath = `/${LOGIN_PATH}`;
  protected readonly sections = SECTIONS;
  protected readonly sites = SITES;
  protected readonly features = FEATURES;
  protected readonly steps = STEPS;
  protected readonly commitments = COMMITMENTS;
  protected readonly questions = QUESTIONS;

  protected goTo(event: Event, id: string): void {
    scrollToSection(this.document, event, id);
  }
}
