import { BrowserRouter } from 'react-router-dom';
import { AuthProvider } from '@/features/auth/auth-context';
import { ThemeProvider } from '@/features/settings/theme-context';
import { ToasterProvider } from '@/components/common/toaster';
import { AppRoutes } from '@/routes';
import { ROUTER_BASENAME } from '@/lib/app-path';

export function App() {
  return (
    <BrowserRouter basename={ROUTER_BASENAME}>
      <ThemeProvider>
        <AuthProvider>
          <ToasterProvider>
            <AppRoutes />
          </ToasterProvider>
        </AuthProvider>
      </ThemeProvider>
    </BrowserRouter>
  );
}
