import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import '@/index.css';
import { App } from '@/App';
import { InstanceBanner } from '@/components/layout/instance-banner';

const container = document.getElementById('root');
if (!container) {
  throw new Error('root element missing');
}
createRoot(container).render(
  <StrictMode>
    <InstanceBanner />
    <App />
  </StrictMode>,
);
