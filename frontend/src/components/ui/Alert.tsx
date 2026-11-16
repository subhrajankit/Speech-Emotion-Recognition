import React from 'react';
import { AlertCircle, AlertTriangle, CheckCircle, Info, X } from 'lucide-react';

export interface AlertProps {
  variant?: 'danger' | 'warning' | 'info' | 'success';
  title?: string;
  children: React.ReactNode;
  onDismiss?: () => void;
  className?: string;
  /** Accessible name for the dismiss button; distinguishes coexisting alerts. */
  dismissLabel?: string;
}

export const Alert: React.FC<AlertProps> = ({
  variant = 'danger',
  title,
  children,
  onDismiss,
  className = '',
  dismissLabel = 'Dismiss alert',
}) => {
  // ARIA semantics follow severity: routine info/success are polite status
  // updates; warning/danger are assertive alerts. The roles already imply
  // the correct aria-live behavior, so no redundant live-region attributes.
  const role = variant === 'info' || variant === 'success' ? 'status' : 'alert';
  const getIcon = () => {
    switch (variant) {
      case 'warning':
        return <AlertTriangle size={18} className="alert-icon" style={{ color: 'var(--color-energy)' }} aria-hidden="true" />;
      case 'success':
        return <CheckCircle size={18} className="alert-icon" style={{ color: 'var(--color-success)' }} aria-hidden="true" />;
      case 'info':
        return <Info size={18} className="alert-icon" style={{ color: 'var(--color-signal)' }} aria-hidden="true" />;
      case 'danger':
      default:
        return <AlertCircle size={18} className="alert-icon" style={{ color: 'var(--color-danger)' }} aria-hidden="true" />;
    }
  };

  return (
    <div
      role={role}
      className={`alert alert-${variant} ${className}`}
    >
      <div className="alert-body">
        {getIcon()}
        <div>
          {title && (
            <div className="alert-title">
              {title}
            </div>
          )}
          <div className="alert-text">{children}</div>
        </div>
      </div>
      {onDismiss && (
        <button
          onClick={onDismiss}
          aria-label={dismissLabel}
          className="alert-dismiss"
        >
          <X size={16} aria-hidden="true" />
        </button>
      )}
    </div>
  );
};
