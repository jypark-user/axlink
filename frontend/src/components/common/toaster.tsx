import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react';
import { cn } from '@/lib/utils';
import { CheckCircle2, AlertTriangle, Info, X } from 'lucide-react';

type ToastVariant = 'default' | 'success' | 'error' | 'warning';

interface Toast {
  id: number;
  title: string;
  description?: string;
  variant: ToastVariant;
}

interface ToastApi {
  toast: (t: { title: string; description?: string; variant?: ToastVariant }) => void;
  dismiss: (id: number) => void;
}

const ToastContext = createContext<ToastApi | null>(null);

let nextId = 1;

export function ToasterProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const dismiss = useCallback((id: number) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const toast = useCallback(
    (t: { title: string; description?: string; variant?: ToastVariant }) => {
      const id = nextId++;
      setToasts((prev) => [
        ...prev,
        { id, title: t.title, description: t.description, variant: t.variant ?? 'default' },
      ]);
      setTimeout(() => dismiss(id), 5000);
    },
    [dismiss],
  );

  const value = useMemo<ToastApi>(() => ({ toast, dismiss }), [toast, dismiss]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="pointer-events-none fixed bottom-4 right-4 z-[100] flex w-full max-w-sm flex-col gap-2">
        {toasts.map((t) => (
          <ToastCard key={t.id} toast={t} onClose={() => dismiss(t.id)} />
        ))}
      </div>
    </ToastContext.Provider>
  );
}

function ToastCard({ toast, onClose }: { toast: Toast; onClose: () => void }) {
  const icon = {
    default: <Info className="size-4 text-info" />,
    success: <CheckCircle2 className="size-4 text-success" />,
    error: <AlertTriangle className="size-4 text-destructive" />,
    warning: <AlertTriangle className="size-4 text-warning" />,
  }[toast.variant];
  return (
    <div
      className={cn(
        'pointer-events-auto flex items-start gap-2 rounded-md border bg-popover p-3 text-popover-foreground shadow-md',
      )}
    >
      <span className="mt-0.5">{icon}</span>
      <div className="flex-1">
        <p className="text-sm font-medium">{toast.title}</p>
        {toast.description && <p className="text-xs text-muted-foreground">{toast.description}</p>}
      </div>
      <button
        className="text-muted-foreground hover:text-foreground"
        onClick={onClose}
        aria-label="닫기"
      >
        <X className="size-4" />
      </button>
    </div>
  );
}

export const useToast = (): ToastApi => {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error('useToast must be used within ToasterProvider');
  return ctx;
};
