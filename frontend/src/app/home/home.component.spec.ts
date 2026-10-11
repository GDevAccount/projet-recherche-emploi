import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';

import { HomeComponent } from './home.component';

describe('HomeComponent', () => {
  let fixture: ComponentFixture<HomeComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [HomeComponent],
      providers: [provideRouter([])],
    }).compileComponents();
    fixture = TestBed.createComponent(HomeComponent);
    fixture.detectChanges();
  });

  const element = () => fixture.nativeElement as HTMLElement;
  const links = (text: string) =>
    Array.from(element().querySelectorAll('a')).filter((link) => link.textContent.trim().startsWith(text));

  it('should start with the profile, open without an account, and keep the login screen for logging in', () => {
    const starts = links('Commencer');
    const logins = links('Se connecter');

    expect(starts.length).toBeGreaterThanOrEqual(3);
    expect(starts.map((link) => link.getAttribute('href'))).toEqual(starts.map(() => '/profil'));
    expect(logins.length).toBeGreaterThanOrEqual(2);
    expect(logins.map((link) => link.getAttribute('href'))).toEqual(logins.map(() => '/connexion'));
  });

  it('should link to the legal pages served outside the application', () => {
    const hrefs = Array.from(element().querySelectorAll('footer a')).map((link) => link.getAttribute('href'));

    expect(hrefs).toEqual(expect.arrayContaining(['/fonctionnement', '/confidentialite', '/conditions']));
  });

  it('should have one main heading and a section for every link of the navigation', () => {
    expect(element().querySelectorAll('h1').length).toBe(1);
    const targets = Array.from(element().querySelectorAll('header nav a[href^="/#"]')).map((link) =>
      link.getAttribute('href')!.slice(2),
    );

    expect(targets.length).toBeGreaterThan(0);
    for (const id of targets) {
      expect(element().querySelector(`section#${id}`)).toBeTruthy();
    }
  });

  it('should scroll to a section and move the focus there', () => {
    const section = element().querySelector<HTMLElement>('#questions')!;
    section.scrollIntoView = vi.fn();
    // Le focus ne se porte que sur un élément de la page
    document.body.appendChild(element());

    element().querySelector<HTMLElement>('header nav a[href="/#questions"]')!.click();

    expect(section.scrollIntoView).toHaveBeenCalled();
    expect(document.activeElement).toBe(section);
    element().remove();
  });

  it('should show the preview as a picture: nothing in it can be reached or clicked', () => {
    const preview = element().querySelector('app-offers-preview .window')!;

    expect(preview.hasAttribute('inert')).toBe(true);
    expect(preview.getAttribute('aria-hidden')).toBe('true');
    expect(preview.querySelectorAll('app-job-card').length).toBeGreaterThan(0);
    expect(element().querySelector('app-offers-preview figcaption')!.textContent).toContain('données fictives');
  });

  it('should show one screen of the demonstration at a time', () => {
    const tabs = Array.from(element().querySelectorAll<HTMLElement>('[role="tab"]'));
    const shown = () =>
      Array.from(element().querySelectorAll<HTMLElement>('[role="tabpanel"]'))
        .filter((panel) => !panel.hidden)
        .map((panel) => panel.id);

    expect(shown()).toEqual(['demo-panel-search']);

    tabs[1].click();
    fixture.detectChanges();
    expect(shown()).toEqual(['demo-panel-rejections']);
    expect(tabs[1].getAttribute('aria-selected')).toBe('true');

    tabs[1].dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowRight' }));
    fixture.detectChanges();
    expect(shown()).toEqual(['demo-panel-profile']);
  });

  it('should fold the navigation behind a button that says whether it is open', () => {
    const button = element().querySelector<HTMLElement>('button.menu')!;
    expect(button.getAttribute('aria-expanded')).toBe('false');

    button.click();
    fixture.detectChanges();

    expect(button.getAttribute('aria-expanded')).toBe('true');
    expect(element().querySelector('header nav')!.classList).toContain('open');
  });
});
