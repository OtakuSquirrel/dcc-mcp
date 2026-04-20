import {
  createContext,
  useContext,
  useState,
  useCallback,
  useRef,
  useEffect,
  type ReactNode,
} from "react";

interface ToastState {
  id: number;
  msg: string;
}

interface ToastContextValue {
  show: (msg: string, duration?: number) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

/**
 * Toast provider. One toast at a time — new show() call replaces any
 * pending toast and resets the auto-hide timer.
 */
export function ToastProvider({ children }: { children: ReactNode }) {
  const [toast, setToast] = useState<ToastState | null>(null);
  const timerRef = useRef<number | undefined>(undefined);

  const show = useCallback((msg: string, duration = 2800) => {
    window.clearTimeout(timerRef.current);
    setToast({ id: Date.now(), msg });
    timerRef.current = window.setTimeout(
      () => setToast(null),
      duration
    );
  }, []);

  useEffect(() => () => window.clearTimeout(timerRef.current), []);

  return (
    <ToastContext.Provider value={{ show }}>
      {children}
      {toast && (
        <div key={toast.id} className="toast show">
          {toast.msg}
        </div>
      )}
    </ToastContext.Provider>
  );
}

export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) {
    throw new Error("useToast must be used within <ToastProvider>");
  }
  return ctx;
}
