import React from 'react';

export interface BadgeProps {
  children: React.ReactNode;
  variant?: 'default' | 'success' | 'warning' | 'danger' | 'accent' | 'neutral';
  className?: string;
  style?: React.CSSProperties;
}

export const Badge: React.FC<BadgeProps> = ({
  children,
  variant = 'default',
  className = '',
  style = {},
}) => {
  const getVariantStyles = (): React.CSSProperties => {
    switch (variant) {
      case 'success':
        return {
          backgroundColor: 'rgba(16, 185, 129, 0.15)',
          color: 'var(--color-success)',
          borderColor: 'rgba(16, 185, 129, 0.3)',
        };
      case 'warning':
        return {
          backgroundColor: 'rgba(245, 158, 11, 0.15)',
          color: 'var(--color-energy)',
          borderColor: 'rgba(245, 158, 11, 0.3)',
        };
      case 'danger':
        return {
          backgroundColor: 'rgba(239, 68, 68, 0.15)',
          color: 'var(--color-danger)',
          borderColor: 'rgba(239, 68, 68, 0.3)',
        };
      case 'accent':
        return {
          backgroundColor: 'rgba(6, 182, 212, 0.15)',
          color: 'var(--color-signal)',
          borderColor: 'rgba(6, 182, 212, 0.3)',
        };
      case 'neutral':
        return {
          backgroundColor: 'var(--bg-surface-hover)',
          color: 'var(--text-muted)',
          borderColor: 'var(--border-subtle)',
        };
      default:
        return {
          backgroundColor: 'rgba(59, 130, 246, 0.15)',
          color: 'var(--color-voice)',
          borderColor: 'rgba(59, 130, 246, 0.3)',
        };
    }
  };

  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium border ${className}`}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        padding: '0.2rem 0.6rem',
        borderRadius: 'var(--radius-full)',
        fontSize: '0.75rem',
        fontWeight: 600,
        borderWidth: '1px',
        borderStyle: 'solid',
        lineHeight: 1.3,
        ...getVariantStyles(),
        ...style,
      }}
    >
      {children}
    </span>
  );
};
