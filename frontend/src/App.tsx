import { BrowserRouter } from 'react-router-dom';
import { AuthProvider } from '@/features/auth/auth-context';
import { ThemeProvider } from '@/features/settings/theme-context';
import { ToasterProvider } from '@/components/common/toaster';
import { AppRoutes } from '@/routes';

export function App() {
  return (
    <BrowserRouter>
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
