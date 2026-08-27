import { render, screen } from '@testing-library/react';
import { App } from '@/App';

it('lands an anonymous visitor on the login screen', async () => {
  render(<App />);
  expect(await screen.findByRole('button', { name: '로그인' })).toBeInTheDocument();
});
