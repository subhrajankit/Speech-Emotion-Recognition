import React from 'react';
import { AlertCircle, AlertTriangle, CheckCircle, Info, X } from 'lucide-react';

export interface AlertProps {
  variant?: 'danger' | 'warning' | 'info' | 'success';
  title?: string;
  children: React.ReactNode;
  onDismiss?: () => void;
  className?: string;
}

export const Alert: React.FC<AlertProps> = ({
  variant = 'danger',
  title,
  children,
  onDismiss,
  className = '',
}) => {
  const getIcon = () => {
    switch (variant) {
      case 'warning':
        return <AlertTriangle size={18} style={{ color: 'var(--color-energy)' }} />;
      case 'success':
        return <CheckCircle size={18} style={{ color: 'var(--color-success)' }} />;
      case 'info':
        return <Info size={18} style={{ color: 'var(--color-signal)' }} />;
      case 'danger':
      default:
        return <AlertCircle size={18} style={{ color: 'var(--color-danger)' }} />;
    }
  };

  const getBorderAndBg = () => {
    switch (variant) {
      case 'warning':
        return {
          backgroundColor: 'rgba(245, 158, 11, 0.1)',
          borderColor: 'rgba(245, 158, 11, 0.3)',
        };
      case 'success':
        return {
          backgroundColor: 'rgba(16, 185, 129, 0.1)',
          borderColor: 'rgba(16, 185, 129, 0.3)',
        };
      case 'info':
        return {
          backgroundColor: 'rgba(6, 182, 212, 0.1)',
          borderColor: 'rgba(6, 182, 212, 0.3)',
        };
      case 'danger':
      default:
        return {
          backgroundColor: 'rgba(239, 68, 68, 0.1)',
          borderColor: 'rgba(239, 68, 68, 0.3)',
        };
    }
  };

  return (
    <div
      role="alert"
      className={`alert ${className}`}
      style={{
        display: 'flex',
        alignItems: 'flex-start',
        justifyContent: 'space-between',
        padding: '0.85rem 1.1rem',
        borderRadius: 'var(--radius-sm)',
        borderWidth: '1px',
        borderStyle: 'solid',
        gap: '0.75rem',
        fontSize: '0.875rem',
        ...getBorderAndBg(),
      }}
    >
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: '0.75rem', flex: 1 }}>
        <span style={{ marginTop: '2px', flexShrink: 0 }}>{getIcon()}</span>
        <div>
          {title && (
            <div style={{ fontWeight: 600, marginBottom: '0.2rem', color: 'var(--text-primary)' }}>
              {title}
            </div>
          )}
          <div style={{ color: 'var(--text-secondary)' }}>{children}</div>
        </div>
      </div>
      {onDismiss && (
        <button
          onClick={onDismiss}
          aria-label="Dismiss alert"
          style={{
            background: 'transparent',
            border: 'none',
            color: 'var(--text-muted)',
            cursor: 'pointer',
            padding: '2px',
          }}
        >
          <X size={16} />
        </button>
      )}
    </div>
  );
};
