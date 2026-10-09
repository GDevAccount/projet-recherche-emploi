import { ComponentFixture, TestBed } from '@angular/core/testing';

import { Account } from '../core/api.models';
import { AvatarComponent } from './avatar.component';

const ALICE: Account = {
  user_id: 2,
  is_owner: false, is_admin: false,
  email: 'alice@exemple.fr',
  name: 'Alice Martin',
  picture: 'https://lh3.googleusercontent.com/alice',
  can_search: false,
  search_running: false,
  remaining_searches: 2,
  max_searches_per_day: 2,
};

describe('AvatarComponent', () => {
  let fixture: ComponentFixture<AvatarComponent>;

  async function show(account: Account): Promise<HTMLElement> {
    await TestBed.configureTestingModule({ imports: [AvatarComponent] }).compileComponents();
    fixture = TestBed.createComponent(AvatarComponent);
    fixture.componentRef.setInput('account', account);
    await fixture.whenStable();
    return fixture.nativeElement as HTMLElement;
  }

  it('should show the Google picture, without telling Google where it is displayed', async () => {
    const element = await show(ALICE);

    const image = element.querySelector('img')!;
    expect(image.getAttribute('src')).toBe('https://lh3.googleusercontent.com/alice');
    expect(image.getAttribute('referrerpolicy')).toBe('no-referrer');
  });

  it('should fall back to the initial when the picture cannot be loaded', async () => {
    const element = await show(ALICE);

    element.querySelector('img')!.dispatchEvent(new Event('error'));
    await fixture.whenStable();

    expect(element.querySelector('img')).toBeNull();
    expect(element.textContent?.trim()).toBe('A');
  });

  it('should use the address when Google gave no name', async () => {
    const element = await show({ ...ALICE, name: null, picture: null });

    expect(element.textContent?.trim()).toBe('A');
  });

  it('should show a silhouette for a session opened with the password', async () => {
    const element = await show({ ...ALICE, email: null, name: null, picture: null });

    expect(element.querySelector('svg')).toBeTruthy();
    expect(element.textContent?.trim()).toBe('');
  });
});
